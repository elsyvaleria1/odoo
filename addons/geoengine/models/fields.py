import functools
import hashlib
import json
import logging
import math
import re
from collections.abc import Callable, Sequence
from operator import attrgetter

import numpy as np
from pyproj import Geod, Transformer
from shapely import (
    force_2d,
    force_3d,
    get_num_coordinates,
    get_srid,
    is_valid_reason,
    make_valid,
    set_srid,
    to_wkb,
    wkb,
    wkt,
)
from shapely.errors import ShapelyError
from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
)
from shapely.geometry import mapping as shapely_mapping
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from odoo import fields
from odoo.db import Cursor
from odoo.db.schema import index_exists
from odoo.exceptions import ValidationError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.models import READ_GROUP_AGGREGATE, BaseModel
from odoo.tools import SQL, str2bool

from .geo_types import (
    DEFAULT_SRID,
    DISPLAY_SRID,
    GeometryValue,
    is_client_renderable_srid,
)

logger = logging.getLogger(__name__)
_schema = logging.getLogger("odoo.schema")

GEO_AGGREGATES: dict[str, Callable[[SQL], SQL]] = {
    "geo_union": lambda expr: SQL("ST_Union(%s)", expr),
    "geo_collect": lambda expr: SQL("ST_Collect(%s)", expr),
    "geo_extent": lambda expr: SQL(
        "ST_SetSRID(ST_Extent(%s)::geometry, MIN(ST_SRID(%s)))", expr, expr
    ),
    "geo_centroid": lambda expr: SQL("ST_Centroid(ST_Collect(%s))", expr),
}


def geo_aggregate_sql(func: str, expr: SQL, srid: int) -> SQL:
    geometry = GEO_AGGREGATES[func](expr)
    if not is_client_renderable_srid(srid):
        geometry = SQL("ST_Transform(%s, %s)", geometry, DISPLAY_SRID)
    return SQL("ST_AsGeoJSON(%s, 15, 2)", geometry)


READ_GROUP_AGGREGATE.update(
    {
        func: lambda _table, expr, func=func: geo_aggregate_sql(
            func, expr, DEFAULT_SRID
        )
        for func in GEO_AGGREGATES
    }
)

_MULTI_OF: dict[str, tuple[str, type[BaseGeometry]]] = {
    "Point": ("MultiPoint", MultiPoint),
    "LineString": ("MultiLineString", MultiLineString),
    "Polygon": ("MultiPolygon", MultiPolygon),
}
_SINGLE_OF: dict[str, str] = {
    multi: single for single, (multi, _cls) in _MULTI_OF.items()
}

DEFAULT_MAX_GEOMETRY_SIZE = 1_000_000

WGS84_GEOD = Geod(ellps="WGS84")

LINE_FIT_DIVISOR = 20_000
LINE_FIT_ATTEMPTS = 6

_HEX_PATTERN = re.compile(r"[0-9A-Fa-f]+")
_EPSG_NAME_PATTERN = re.compile(r"EPSG:{1,2}(?:[0-9.]+:)?(\d+)\s*$", re.IGNORECASE)


def create_geo_column(
    cr: Cursor,
    tablename: str,
    columnname: str,
    geotype: str,
    srid: int,
    dim: str,
    comment: str | None = None,
) -> None:
    cr.execute(
        "SELECT AddGeometryColumn( %s, %s, %s, %s, %s)",
        (tablename, columnname, srid, geotype, dim),
    )
    if comment:
        cr.execute(
            SQL(
                "COMMENT ON COLUMN %s.%s IS %s",
                SQL.identifier(tablename),
                SQL.identifier(columnname),
                comment,
            ),
        )
    _schema.debug(
        "Table %r: added geometry column %r of type %s",
        tablename,
        columnname,
        geotype,
    )


def geo_index_name(tablename: str, columnname: str) -> str:
    name = f"{tablename}_{columnname}_gist_index"
    if len(name) <= 63:
        return name
    digest = hashlib.sha1(name.encode()).hexdigest()[:8]
    return f"{f'{tablename}_{columnname}'[:48]}_{digest}_gist"


def _is_foreign_table(cr: Cursor, tablename: str) -> bool:
    cr.execute(
        "SELECT relkind FROM pg_class WHERE oid = to_regclass(%s)",
        (tablename,),
    )
    row = cr.fetchone()
    return bool(row) and row[0] == "f"


def create_geo_index(
    cr: Cursor, tablename: str, columnname: str, *, rebuild: bool = False
) -> bool:
    indexname = geo_index_name(tablename, columnname)
    if not rebuild and index_exists(cr, indexname):
        return False

    if _is_foreign_table(cr, tablename):
        _schema.warning(
            "Table %r is a foreign table; not creating spatial index %r on "
            "column %r, it belongs in the remote database",
            tablename,
            indexname,
            columnname,
        )
        return False

    if rebuild:
        cr.execute(SQL("DROP INDEX IF EXISTS %s", SQL.identifier(indexname)))
    cr.execute(
        SQL(
            "CREATE INDEX %s ON %s USING GIST (%s)",
            SQL.identifier(indexname),
            SQL.identifier(tablename),
            SQL.identifier(columnname),
        ),
    )
    _schema.debug("Table %r: created index %r", tablename, indexname)
    return True


def _is_hex(value: str) -> bool:
    return len(value) % 2 == 0 and _HEX_PATTERN.fullmatch(value) is not None


def _parse_geojson(data: object) -> BaseGeometry:
    if not isinstance(data, dict):
        raise ValueError("Invalid GeoJSON geometry: not an object")
    try:
        geometry = shapely_shape(data)
    except Exception as e:
        raise ValueError(f"Invalid GeoJSON geometry: {e}") from e
    if srid := _srid_from_crs_member(data.get("crs")):
        geometry = set_srid(geometry, srid)
    return geometry


def _parse_geometry(value: GeometryValue) -> BaseGeometry | None:
    if not value:
        return None

    if isinstance(value, BaseGeometry):
        return value

    if isinstance(value, dict):
        return _parse_geojson(value)

    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return wkb.loads(bytes(value))
        except ShapelyError as e:
            raise ValueError(f"Invalid WKB geometry: {e}") from e

    if not isinstance(value, str):
        raise TypeError(
            f"Cannot read a geometry from {type(value).__name__}; expected WKT, "
            f"WKB, GeoJSON or a shapely geometry."
        )

    if not (value := value.strip()):
        return None

    srid = 0
    if value.startswith("SRID="):
        prefix, separator, value = value.partition(";")
        if not separator:
            raise ValueError("Invalid SRID format: missing semicolon")
        try:
            srid = int(prefix.removeprefix("SRID="))
        except ValueError as e:
            raise ValueError(f"Invalid SRID {prefix!r}") from e

    if value.startswith("{"):
        try:
            geometry = _parse_geojson(json_loads(value))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid GeoJSON geometry: {e}") from e
    elif _is_hex(value):
        try:
            geometry = wkb.loads(value, hex=True)
        except ShapelyError as e:
            raise ValueError(f"Invalid WKB geometry: {e}") from e
    else:
        try:
            geometry = wkt.loads(value)
        except ShapelyError as e:
            raise ValueError(f"Invalid geometry string: {e}") from e

    return set_srid(geometry, srid) if srid else geometry


def shape_to_geojson(shape: BaseGeometry, srid: int) -> str:
    return json_dumps(
        shapely_mapping(shape)
        | {"crs": {"type": "name", "properties": {"name": f"EPSG:{srid}"}}}
    )


def _srid_from_crs_member(crs: object) -> int | None:
    if not isinstance(crs, dict):
        return None
    name = (crs.get("properties") or {}).get("name")
    if not isinstance(name, str):
        return None
    if match := _EPSG_NAME_PATTERN.search(name.strip()):
        return int(match.group(1))
    return None


@functools.lru_cache(maxsize=64)
def _get_transformer(src_srid: int, dst_srid: int) -> Transformer:
    return Transformer.from_crs(f"EPSG:{src_srid}", f"EPSG:{dst_srid}", always_xy=True)


def reproject(shape: BaseGeometry, src_srid: int, dst_srid: int) -> BaseGeometry:
    if src_srid == dst_srid or shape is None or shape.is_empty:
        return shape
    transformer = _get_transformer(src_srid, dst_srid)
    return shapely_transform(transformer.transform, shape)


def max_geometry_size(env) -> int:
    raw = env.registry.settings.get(
        env, "geoengine.max_geometry_size", str(DEFAULT_MAX_GEOMETRY_SIZE)
    )
    try:
        return int(raw)
    except TypeError, ValueError:
        logger.warning(
            "geoengine.max_geometry_size is %r, not a number of bytes; using %d",
            raw,
            DEFAULT_MAX_GEOMETRY_SIZE,
        )
        return DEFAULT_MAX_GEOMETRY_SIZE


def geodesic_length_km(shape: BaseGeometry | bool) -> float:
    return WGS84_GEOD.geometry_length(shape) / 1000.0 if shape else 0.0


def geometry_size(shape: BaseGeometry) -> int:
    return len(shape.wkt.encode("utf-8"))


def geometry_size_bound(shape: BaseGeometry) -> int:
    dimensions = 3 if shape.has_z else 2
    return 64 + get_num_coordinates(shape) * (dimensions * 26 + 6)


def _douglas_peucker(points: np.ndarray, tolerance: float) -> list[int]:
    keep = np.zeros(len(points), dtype=bool)
    keep[0] = keep[-1] = True
    spans = [(0, len(points) - 1)]
    while spans:
        first, last = spans.pop()
        if last - first < 2:
            continue
        start = points[first]
        dx, dy = points[last] - start
        inner = points[first + 1 : last] - start
        if length := math.hypot(dx, dy):
            distances = np.abs(dx * inner[:, 1] - dy * inner[:, 0]) / length
        else:
            distances = np.hypot(inner[:, 0], inner[:, 1])
        if distances[farthest := int(np.argmax(distances))] > tolerance:
            split = first + 1 + farthest
            keep[split] = True
            spans += [(first, split), (split, last)]
    return np.flatnonzero(keep).tolist()


def fit_line_vertices(
    coords: Sequence[Sequence[float]], max_size: int
) -> list[int] | None:
    line = LineString(coords)
    if geometry_size_bound(line) <= max_size or geometry_size(line) <= max_size:
        return list(range(len(coords)))
    points = np.asarray(coords, dtype=float)[:, :2]
    (min_x, min_y), (max_x, max_y) = points.min(axis=0), points.max(axis=0)
    tolerance = math.hypot(max_x - min_x, max_y - min_y) / LINE_FIT_DIVISOR
    for _attempt in range(LINE_FIT_ATTEMPTS):
        kept = _douglas_peucker(points, tolerance)
        size = geometry_size(LineString([coords[index] for index in kept]))
        logger.debug(
            "Line of %d vertices fitted with tolerance %s: %d vertices, %d bytes",
            len(coords),
            tolerance,
            len(kept),
            size,
        )
        if size <= max_size:
            return kept
        tolerance *= 4
    return None


def _translator(record: BaseModel | None):
    if record is not None:
        return record.env._
    return lambda text, **kw: text % kw if kw else text


class GeoField(fields.Field):
    geo_type: str
    dim: str = "2"
    srid: int = DEFAULT_SRID
    aggregator: str = "geo_collect"
    column_value_is_cache = True

    _description_dim = property(attrgetter("dim"))
    _description_srid = property(attrgetter("srid"))
    _description_geo_type = property(attrgetter("geo_type"))

    _related_dim = property(attrgetter("dim"))
    _related_srid = property(attrgetter("srid"))

    @functools.cached_property
    def column_type(self) -> tuple[str, str]:
        return ("geometry", self._postgis_type())

    def _postgis_type(self) -> str:
        suffix = {"3": "Z", "4": "ZM"}.get(self.dim, "")
        return f"geometry({self.geo_type.upper()}{suffix}, {self.srid})"

    def convert_to_column(
        self,
        value: GeometryValue,
        record: BaseModel,
        values: dict[str, GeometryValue] | None = None,
        validate: bool = True,
    ) -> str | None:
        if not value:
            return None
        if not validate and isinstance(value, str) and _is_hex(value):
            return value
        return self._to_ewkb_hex(self._normalize_for_storage(value, record, validate))

    def _to_ewkb_hex(self, shape: BaseGeometry) -> str:
        return to_wkb(set_srid(shape, self.srid), hex=True, include_srid=True)

    def _normalize_for_storage(
        self,
        value: GeometryValue,
        record: BaseModel | None,
        validate: bool = True,
    ) -> BaseGeometry:
        shape = self.entry_to_shape(value, record=record)

        if (source_srid := get_srid(shape)) and source_srid != self.srid:
            shape = reproject(shape, source_srid, self.srid)

        shape = self._coerce_dimension(shape)

        if validate and record is not None:
            shape = self._check_geometry(shape, record)

        return self._coerce_to_geo_type(shape, record)

    def _coerce_dimension(self, shape: BaseGeometry) -> BaseGeometry:
        match self.dim:
            case "2" if shape.has_z:
                return force_2d(shape)
            case "3" if not shape.has_z:
                return force_3d(shape)
        return shape

    def _coerce_to_geo_type(
        self,
        shape: BaseGeometry,
        record: BaseModel | None = None,
    ) -> BaseGeometry:
        target = self.geo_type
        actual = shape.geom_type
        if actual == target:
            return shape

        translate = _translator(record)
        if actual == "GeometryCollection":
            wanted = {target, _SINGLE_OF.get(target, target)}
            kept = [
                part
                for member in shape.geoms
                if member.geom_type in wanted
                for part in (
                    member.geoms if member.geom_type in _SINGLE_OF else (member,)
                )
            ]
            if not kept:
                raise ValidationError(
                    translate(
                        "Repairing this geometry produced no %(target)s part to "
                        "store (got %(got)s).",
                        target=target,
                        got=", ".join(sorted({g.geom_type for g in shape.geoms})),
                    )
                )
            shape = kept[0] if len(kept) == 1 else _MULTI_OF[kept[0].geom_type][1](kept)
            actual = shape.geom_type
            if actual == target:
                return shape

        if target == _MULTI_OF.get(actual, (None, None))[0]:
            return _MULTI_OF[actual][1]([shape])

        if actual == _MULTI_OF.get(target, (None, None))[0]:
            parts = list(shape.geoms)
            if len(parts) == 1:
                return parts[0]
            raise ValidationError(
                translate(
                    "This geometry is %(count)d separate %(target)s parts, and "
                    "the field stores a single one. Nothing can be written "
                    "without discarding %(lost)d of them -- use a Multi%(target)s "
                    "field, or split the record.",
                    count=len(parts),
                    target=target,
                    lost=len(parts) - 1,
                )
            )

        raise ValidationError(
            translate(
                "Geometry type mismatch: expected %(expected)s, got %(actual)s.",
                expected=target,
                actual=actual,
            )
        )

    def convert_to_cache(
        self,
        value: GeometryValue,
        record: BaseModel,
        validate: bool = True,
    ) -> GeometryValue:
        if not value:
            return value
        if not validate and isinstance(value, str) and _is_hex(value):
            return value
        return self._to_ewkb_hex(self._normalize_for_storage(value, record, validate))

    def convert_to_record(
        self,
        value: GeometryValue,
        record: BaseModel,
    ) -> BaseGeometry | bool:
        return _parse_geometry(value) or False

    def convert_to_read(
        self,
        value: GeometryValue,
        record: BaseModel,
        use_display_name: bool = True,
    ) -> str | bool:
        shape = _parse_geometry(value) if value else None
        if not shape or shape.is_empty:
            return False

        out_srid = self.srid
        if not is_client_renderable_srid(out_srid):
            shape = reproject(shape, out_srid, DISPLAY_SRID)
            out_srid = DISPLAY_SRID

        return shape_to_geojson(shape, out_srid)

    def entry_to_shape(
        self,
        value: GeometryValue,
        record: BaseModel | None = None,
    ) -> BaseGeometry:
        translate = _translator(record)
        try:
            shape = _parse_geometry(value)
        except (ValueError, TypeError) as exc:
            raise ValidationError(
                translate(
                    "This value is not a geometry that can be stored "
                    "(%(error)s): %(value).60s",
                    error=str(exc),
                    value=str(value),
                )
            ) from exc
        if not shape:
            raise ValidationError(
                translate(
                    "This value is not a geometry that can be stored: %(value).60s",
                    value=str(value),
                )
            )
        return shape

    def update_db_column(
        self,
        model: BaseModel,
        column: dict[str, str | int | None] | None,
    ) -> None:
        if not column:
            create_geo_column(
                model.env.cr,
                model._table,
                self.name,
                self.geo_type.upper(),
                self.srid,
                self.dim,
                self.string,
            )
        elif column["udt_name"] == "geometry":
            self._sync_geometry_column(model)
        else:
            logger.warning(
                "Column %s.%s has unexpected type %s (expected geometry); "
                "leaving it alone, and not attempting a spatial index on it",
                model._table,
                self.name,
                column.get("udt_name", "unknown"),
            )
            return

        create_geo_index(model.env.cr, model._table, self.name)

    def _sync_geometry_column(self, model: BaseModel) -> None:
        cr: Cursor = model.env.cr
        cr.execute(
            """
            SELECT srid, type, coord_dimension
            FROM geometry_columns
            WHERE f_table_schema = current_schema()
              AND f_table_name = %s
              AND f_geometry_column = %s
            """,
            (model._table, self.name),
        )
        expected_shape = (self.geo_type.upper(), int(self.dim))
        if not (row := cr.fetchone()):
            reason = "the column is missing from geometry_columns"
        elif row == (self.srid, *expected_shape):
            return
        elif tuple(row[1:]) != expected_shape:
            reason = f"type {row[1]} {row[2]}D -> {expected_shape[0]} {self.dim}D"
        elif row[0] <= 0:
            reason = f"SRID {row[0]} is unknown, so it cannot be transformed"
        else:
            cr.execute(
                SQL(
                    "ALTER TABLE %s ALTER COLUMN %s TYPE %s USING ST_Transform(%s, %s)",
                    SQL.identifier(model._table),
                    SQL.identifier(self.name),
                    SQL(self._postgis_type()),  # noqa: E8501 -- the type the field declares
                    SQL.identifier(self.name),
                    self.srid,
                ),
            )
            _schema.info(
                "Migrated geometry column %s.%s SRID %s -> %s",
                model._table,
                self.name,
                row[0],
                self.srid,
            )
            return

        logger.warning(
            "Geometry column %s.%s no longer matches the field and cannot be "
            "auto-migrated (%s). Continuing without migration.",
            model._table,
            self.name,
            reason,
        )

    def _check_geometry(
        self,
        shape: BaseGeometry,
        record: BaseModel,
    ) -> BaseGeometry:
        env = record.env
        config = env.registry.settings

        if not str2bool(config.get(env, "geoengine.validate_geometry", "True"), True):
            return shape

        if not shape.is_valid:
            reason = is_valid_reason(shape) or "Unknown error"
            if not str2bool(
                config.get(env, "geoengine.auto_repair_geometry", "True"), True
            ):
                raise ValidationError(env._("Invalid geometry: %s", reason))
            repaired = make_valid(shape)
            if not repaired.is_valid or repaired.is_empty:
                raise ValidationError(
                    env._("Geometry could not be repaired: %s") % reason,
                )
            logger.info("Auto-repaired invalid %s geometry (%s)", self.geo_type, reason)
            shape = repaired

        max_size = max_geometry_size(env)
        if (
            geometry_size_bound(shape) > max_size
            and (wkt_size := geometry_size(shape)) > max_size
        ):
            raise ValidationError(
                env._(
                    "Geometry size (%(actual)d bytes) exceeds maximum allowed (%(maximum)d bytes)",
                    actual=wkt_size,
                    maximum=max_size,
                ),
            )

        return shape


class GeoPoint(GeoField):
    type: str = "geo_point"
    geo_type: str = "Point"


class GeoLine(GeoField):
    type: str = "geo_line"
    geo_type: str = "LineString"


class GeoPolygon(GeoField):
    type: str = "geo_polygon"
    geo_type: str = "Polygon"


class GeoMultiPoint(GeoField):
    type: str = "geo_multi_point"
    geo_type: str = "MultiPoint"


class GeoMultiLine(GeoField):
    type: str = "geo_multi_line"
    geo_type: str = "MultiLineString"


class GeoMultiPolygon(GeoField):
    type: str = "geo_multi_polygon"
    geo_type: str = "MultiPolygon"


fields.GeoPoint = GeoPoint
fields.GeoLine = GeoLine
fields.GeoPolygon = GeoPolygon
fields.GeoMultiPoint = GeoMultiPoint
fields.GeoMultiLine = GeoMultiLine
fields.GeoMultiPolygon = GeoMultiPolygon
