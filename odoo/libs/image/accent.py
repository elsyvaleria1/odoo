import math
import re
from collections import defaultdict
from typing import TYPE_CHECKING

from lxml import etree
from PIL import Image

from odoo.libs.colors.contrast import rgb_to_oklch
from odoo.libs.colors.conversions import hex_to_rgb
from odoo.libs.image.utils import (
    ImageDecodeError,
    _decoding,
    _load_whole,
    binary_to_image,
    is_svg,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

__all__ = ["icon_accent"]

# below this OKLCH chroma a colour reads as grey, and a grey has no hue to lend
MIN_CHROMA = 0.04
HUE_BINS = 24
SAMPLE_SIZE = (64, 64)

_SVG_NS = "{http://www.w3.org/2000/svg}"
_RGB_RE = re.compile(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\Z")
_STYLE_FILL_RE = re.compile(r"(?:^|;)\s*fill\s*:\s*([^;]+)")
_PATH_TOKEN_RE = re.compile(
    r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
)
_PATH_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}

type Rgb = tuple[int, int, int]


def icon_accent(data: bytes) -> Rgb | None:
    if not is_svg(data):
        return _dominant_hue(_raster_pixels(data))
    try:
        return _dominant_hue(_svg_fills(data))
    except etree.XMLSyntaxError as error:
        msg = f"not a readable icon: {error}"
        raise ImageDecodeError(msg) from error


def _dominant_hue(weighted: Iterable[tuple[Rgb, float]]) -> Rgb | None:
    bins: defaultdict[int, list[tuple[Rgb, float]]] = defaultdict(list)
    for rgb, weight in weighted:
        if weight <= 0:
            continue
        _lightness, chroma, hue = rgb_to_oklch(rgb)
        if chroma >= MIN_CHROMA:
            bins[int(hue * HUE_BINS / 360) % HUE_BINS].append((rgb, weight))
    if not bins:
        return None
    members = max(bins.values(), key=lambda entries: sum(w for _, w in entries))
    total = sum(weight for _, weight in members)
    red, green, blue = (
        round(sum(rgb[channel] * weight for rgb, weight in members) / total)
        for channel in range(3)
    )
    return red, green, blue


def _raster_pixels(data: bytes) -> list[tuple[Rgb, float]]:
    image = binary_to_image(data)
    with _decoding("accent", data):
        image.draft(None, SAMPLE_SIZE)
        _load_whole(image)
        image.thumbnail(SAMPLE_SIZE, Image.Resampling.NEAREST, reducing_gap=None)
        colours = image.convert("RGBA").getcolors(SAMPLE_SIZE[0] * SAMPLE_SIZE[1])
    return [
        ((red, green, blue), count)
        for count, (red, green, blue, alpha) in colours
        if alpha >= 128
    ]


def _parse_colour(value: str | None) -> Rgb | None:
    if not value:
        return None
    value = value.strip()
    if value.startswith("#"):
        try:
            return hex_to_rgb(value)
        except ValueError:
            return None
    if match := _RGB_RE.match(value):
        red, green, blue = (min(int(group), 255) for group in match.groups())
        return red, green, blue
    return None


def _own_fill(element: etree._Element) -> str | None:
    if match := _STYLE_FILL_RE.search(element.get("style", "")):
        return match.group(1)
    return element.get("fill")


def _svg_fills(data: bytes) -> Iterator[tuple[Rgb, float]]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(data, parser)
    gradients = {
        gradient.get("id"): _gradient_colour(gradient)
        for gradient in root.iter(
            f"{_SVG_NS}linearGradient", f"{_SVG_NS}radialGradient"
        )
    }

    def walk(element: etree._Element, inherited: str | None) -> Iterator:
        fill = _own_fill(element) or inherited
        tag = etree.QName(element).localname if isinstance(element.tag, str) else ""
        if tag == "defs":
            return
        area = _area(tag, element)
        if area and fill:
            if fill.startswith("url(#"):
                colour = gradients.get(fill[5:].rstrip(") "))
            else:
                colour = _parse_colour(fill)
            if colour:
                yield colour, area
        for child in element:
            yield from walk(child, fill)

    yield from walk(root, "#000000")


def _gradient_colour(gradient: etree._Element) -> Rgb | None:
    colours = [
        colour
        for stop in gradient.iter(f"{_SVG_NS}stop")
        if (
            colour := _parse_colour(
                stop.get("stop-color")
                or next(
                    (
                        part.split(":", 1)[1]
                        for part in stop.get("style", "").split(";")
                        if part.strip().startswith("stop-color")
                    ),
                    None,
                )
            )
        )
    ]
    if not colours:
        return None
    red, green, blue = (
        round(sum(colour[channel] for colour in colours) / len(colours))
        for channel in range(3)
    )
    return red, green, blue


def _length(element: etree._Element, name: str) -> float:
    try:
        return float(re.sub(r"[a-z%]+\Z", "", element.get(name, "0")))
    except ValueError:
        return 0.0


def _area(tag: str, element: etree._Element) -> float:
    match tag:
        case "path":
            return _path_area(element.get("d", ""))
        case "rect":
            return _length(element, "width") * _length(element, "height")
        case "circle":
            return math.pi * _length(element, "r") ** 2
        case "ellipse":
            return math.pi * _length(element, "rx") * _length(element, "ry")
        case "polygon":
            numbers = [
                float(n)
                for n in re.findall(
                    r"[-+]?(?:\d+\.?\d*|\.\d+)", element.get("points", "")
                )
            ]
            return _shoelace(list(zip(numbers[::2], numbers[1::2], strict=False)))
    return 0.0


def _shoelace(points: list[tuple[float, float]]) -> float:
    return (
        abs(
            sum(
                x0 * y1 - x1 * y0
                for (x0, y0), (x1, y1) in zip(
                    points, points[1:] + points[:1], strict=True
                )
            )
        )
        / 2
    )


def _path_numbers(d: str) -> Iterator[str | float]:
    for command, number in _PATH_TOKEN_RE.findall(d):
        yield command or float(number)


def _path_area(d: str) -> float:
    # the polygon through each segment's end points: curves are chords, which
    # ranks shapes by size as well as an icon's dominant fill needs
    area = 0.0
    subpath: list[tuple[float, float]] = []
    x = y = start_x = start_y = 0.0
    tokens = list(_path_numbers(d))
    index = 0
    command = ""
    while index < len(tokens):
        token = tokens[index]
        if isinstance(token, str):
            command = token
            index += 1
            if command in "Zz":
                area += _shoelace(subpath)
                subpath = []
                x, y = start_x, start_y
            continue
        upper = command.upper()
        arity = _PATH_ARITY.get(upper)
        if not arity or index + arity > len(tokens):
            break
        args = [arg for arg in tokens[index : index + arity] if isinstance(arg, float)]
        if len(args) < arity:
            break
        index += arity
        relative = command.islower()
        match upper:
            case "H":
                x = args[0] + (x if relative else 0)
            case "V":
                y = args[0] + (y if relative else 0)
            case _:
                end_x, end_y = args[-2], args[-1]
                x, y = (x + end_x, y + end_y) if relative else (end_x, end_y)
        if upper == "M":
            if subpath:
                area += _shoelace(subpath)
            subpath = []
            start_x, start_y = x, y
            command = "l" if relative else "L"
        subpath.append((x, y))
    return area + _shoelace(subpath)
