"""Maps for printed documents.

WeasyPrint runs no JavaScript, so a report cannot embed the OpenLayers map.
A static map is an SVG instead: the geometries as vector paths, framed to fit
the page box, over the basemap tiles that frame covers, embedded as PNG. The
tiles come from one XYZ server (``geoengine.static_map_tile_url``) and are kept
on disk, so a report printed again reads none; a map whose tiles cannot be
fetched is still drawn, without a basemap."""

import base64
import hashlib
import logging
import math
import pathlib
import time
from dataclasses import dataclass

import requests
from markupsafe import Markup
from shapely.geometry.base import BaseGeometry

from odoo.tools import config

from .fields import reproject

_logger = logging.getLogger(__name__)

WEB_MERCATOR = 3857
WEB_MERCATOR_WIDTH = 40075016.68557849
TILE_SIZE = 256
MAX_ZOOM = 18
POINT_SPAN_M = 600
DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_ATTRIBUTION = "© OpenStreetMap contributors"
TILE_TIMEOUT_S = 5
MAP_TILE_BUDGET_S = 10
TILE_CACHE_DAYS = 30
MAX_TILES = 30


@dataclass(frozen=True)
class MapStyle:
    stroke: str = "#ff6a0a"
    fill: str = "#ff6a0a"
    fill_opacity: float = 0.25
    stroke_width: float = 3.0
    radius: float = 6.0
    label: str | None = None


@dataclass(frozen=True)
class MapItem:
    shape: BaseGeometry
    srid: int
    style: MapStyle = MapStyle()


@dataclass(frozen=True)
class Frame:

    minx: float
    maxy: float
    zoom: int
    width: int
    height: int

    @property
    def resolution(self) -> float:
        return WEB_MERCATOR_WIDTH / (TILE_SIZE * 2**self.zoom)

    def pixel(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.minx) / self.resolution, (self.maxy - y) / self.resolution

    def tiles(self) -> list[tuple[int, int, float, float]]:
        tile_m = TILE_SIZE * self.resolution
        half = WEB_MERCATOR_WIDTH / 2
        first_x = math.floor((self.minx + half) / tile_m)
        last_x = math.floor((self.minx + self.width * self.resolution + half) / tile_m)
        first_y = math.floor((half - self.maxy) / tile_m)
        last_y = math.floor((half - self.maxy + self.height * self.resolution) / tile_m)
        count = 2**self.zoom
        tiles = []
        for ty in range(max(first_y, 0), min(last_y, count - 1) + 1):
            for tx in range(first_x, last_x + 1):
                left = tx * tile_m - half
                top = half - ty * tile_m
                px, py = self.pixel(left, top)
                tiles.append((tx % count, ty, px, py))
        return tiles


def frame_for(
    shapes: list[BaseGeometry], width: int, height: int, padding: int
) -> Frame:
    minx = min(shape.bounds[0] for shape in shapes)
    miny = min(shape.bounds[1] for shape in shapes)
    maxx = max(shape.bounds[2] for shape in shapes)
    maxy = max(shape.bounds[3] for shape in shapes)
    span_x = max(maxx - minx, POINT_SPAN_M)
    span_y = max(maxy - miny, POINT_SPAN_M)
    inner_w, inner_h = max(width - 2 * padding, 1), max(height - 2 * padding, 1)
    resolution = max(span_x / inner_w, span_y / inner_h)
    zoom = math.floor(math.log2(WEB_MERCATOR_WIDTH / (TILE_SIZE * resolution)))
    zoom = max(0, min(zoom, MAX_ZOOM))
    frame_res = WEB_MERCATOR_WIDTH / (TILE_SIZE * 2**zoom)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    return Frame(
        minx=cx - width / 2 * frame_res,
        maxy=cy + height / 2 * frame_res,
        zoom=zoom,
        width=width,
        height=height,
    )


class TileFetcher:

    def __init__(self, env):
        self._env = env
        settings = env.registry.settings
        self.url = settings.get(env, "geoengine.static_map_tile_url", DEFAULT_TILE_URL)
        self.attribution = settings.get(
            env, "geoengine.static_map_attribution", DEFAULT_ATTRIBUTION
        )
        base_url = settings.get(env, "web.base.url", "") or ""
        self.user_agent = f"Odoo geoengine static map ({base_url})"
        self.cache_dir = pathlib.Path(config["data_dir"]) / "geoengine_tiles"
        self._deadline = time.monotonic() + MAP_TILE_BUDGET_S
        self._session = None

    def tile(self, z: int, x: int, y: int) -> bytes | None:
        url = self.url.format(z=z, x=x, y=y)
        path = self.cache_dir / f"{hashlib.sha1(url.encode()).hexdigest()}.png"
        try:
            if time.time() - path.stat().st_mtime < TILE_CACHE_DAYS * 86400:
                return path.read_bytes()
        except OSError:
            pass
        data = self._download(url)
        if data is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            except OSError as error:
                _logger.info("Static map tile not cached: %s", error)
        return data

    def _download(self, url: str) -> bytes | None:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            return None
        self._session = self._session or self._env["ir.egress"].session(
            purpose="geoengine_static_map"
        )
        try:
            response = self._session.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=min(TILE_TIMEOUT_S, remaining),
            )
        except requests.RequestException as error:
            _logger.info("Static map tile %s not fetched: %s", url, error)
            return None
        if response.status_code != 200 or not response.content.startswith(b"\x89PNG"):
            _logger.info(
                "Static map tile %s refused: HTTP %s", url, response.status_code
            )
            return None
        return response.content


def _number(value: float) -> str:
    return f"{value:.1f}"


def _points(coords, frame: Frame) -> str:
    return " ".join(
        "{},{}".format(*map(_number, frame.pixel(x, y))) for x, y, *_rest in coords
    )


def _ring_path(coords, frame: Frame) -> str:
    pixels = [frame.pixel(x, y) for x, y, *_rest in coords]
    return "M" + " L".join(f"{_number(px)} {_number(py)}" for px, py in pixels) + " Z"


def _svg_shape(shape: BaseGeometry, style: MapStyle, frame: Frame) -> list[Markup]:
    kind = shape.geom_type
    if kind.startswith("Multi") or kind == "GeometryCollection":
        return [
            element
            for part in shape.geoms
            for element in _svg_shape(part, style, frame)
        ]
    if kind == "Point":
        cx, cy = map(_number, frame.pixel(shape.x, shape.y))
        elements = [
            Markup(
                '<circle cx="{}" cy="{}" r="{}" fill="{}" stroke="#ffffff" '
                'stroke-width="1.5"/>'
            ).format(cx, cy, style.radius, style.fill)
        ]
        if style.label:
            elements.append(
                Markup(
                    '<text x="{}" y="{}" dy="0.35em" text-anchor="middle" '
                    'font-size="{}" font-family="sans-serif" font-weight="bold" '
                    'fill="#ffffff">{}</text>'
                ).format(cx, cy, _number(style.radius * 1.2), style.label)
            )
        return elements
    simplified = shape.simplify(frame.resolution / 2, preserve_topology=True)
    if kind == "LineString":
        return [
            Markup(
                '<polyline points="{}" fill="none" stroke="{}" stroke-width="{}" '
                'stroke-linejoin="round" stroke-linecap="round"/>'
            ).format(
                _points(simplified.coords, frame), style.stroke, style.stroke_width
            )
        ]
    if kind == "Polygon":
        path = " ".join(
            _ring_path(ring.coords, frame)
            for ring in (simplified.exterior, *simplified.interiors)
        )
        return [
            Markup(
                '<path d="{}" fill="{}" fill-opacity="{}" fill-rule="evenodd" '
                'stroke="{}" stroke-width="{}"/>'
            ).format(
                path, style.fill, style.fill_opacity, style.stroke, style.stroke_width
            )
        ]
    return []


def render_static_map(
    env,
    items: list[MapItem],
    *,
    width: int = 640,
    height: int = 360,
    padding: int = 24,
    basemap: bool = True,
    fetcher: TileFetcher | None = None,
) -> Markup | None:
    placed = [
        (reproject(item.shape, item.srid, WEB_MERCATOR), item.style)
        for item in items
        if item.shape is not None and not item.shape.is_empty
    ]
    if not placed:
        return None
    frame = frame_for([shape for shape, _style in placed], width, height, padding)
    parts = [
        Markup(
            '<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}" '
            'viewBox="0 0 {0} {1}" class="o_geoengine_static_map">'
            '<rect width="{0}" height="{1}" fill="#eef0f2"/>'
        ).format(width, height)
    ]
    attribution = None
    if basemap:
        fetcher = fetcher or TileFetcher(env)
        tiles = frame.tiles()
        if len(tiles) > MAX_TILES:
            _logger.info(
                "Static map needs %d tiles; drawn without a basemap", len(tiles)
            )
            tiles = []
        for tx, ty, left, top in tiles:
            data = fetcher.tile(frame.zoom, tx, ty)
            if data is None:
                continue
            parts.append(
                Markup(
                    '<image x="{}" y="{}" width="{}" height="{}" '
                    'href="data:image/png;base64,{}"/>'
                ).format(
                    _number(left),
                    _number(top),
                    TILE_SIZE,
                    TILE_SIZE,
                    base64.b64encode(data).decode(),
                )
            )
            attribution = fetcher.attribution
    for points_last in (False, True):
        for shape, style in placed:
            if (shape.geom_type in ("Point", "MultiPoint")) is points_last:
                parts.extend(_svg_shape(shape, style, frame))
    if attribution:
        parts.append(
            Markup(
                '<text x="{}" y="{}" text-anchor="end" font-size="9" '
                'font-family="sans-serif" fill="#333333" stroke="#ffffff" '
                'stroke-width="2.5" paint-order="stroke">{}</text>'
            ).format(width - 4, height - 4, attribution)
        )
    parts.append(Markup("</svg>"))
    return Markup("").join(parts)
