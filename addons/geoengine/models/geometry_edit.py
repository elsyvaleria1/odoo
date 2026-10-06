"""Changing the areas of one record's shape: adding a drawn area to it,
cutting one out of it, removing one of its parts; and the shapes of several
records: splitting one into records, merging several into one.

Area edits come from the map and go back to it, in the map's projection; the
result is written to the record like any reshape, so saving checks it. A split
or a merge writes records itself."""

from shapely import get_srid, unary_union
from shapely.geometry import MultiLineString, MultiPoint, MultiPolygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import split

from odoo.exceptions import UserError
from odoo.models import BaseModel

from .fields import GeoField, reproject, shape_to_geojson
from .geo_types import GeometryValue

SHAPE_EDITS = ("add_area", "cut_area", "remove_part")

_MULTI = {
    "Polygon": MultiPolygon,
    "LineString": MultiLineString,
    "Point": MultiPoint,
}


def _parts(shape: BaseGeometry) -> list[BaseGeometry]:
    return list(shape.geoms) if hasattr(shape, "geoms") else [shape]


def _without_nearest_part(
    record: BaseModel, shape: BaseGeometry, point: BaseGeometry
) -> BaseGeometry:
    parts = _parts(shape)
    if len(parts) < 2:
        raise UserError(
            record.env._(
                "This shape has a single part. To remove it, delete the record or "
                "clear its geometry."
            )
        )
    nearest = min(parts, key=point.distance)
    kept = [part for part in parts if part is not nearest]
    if len(kept) == 1:
        return kept[0]
    return _MULTI[kept[0].geom_type](kept)


def edit_shape(
    field: GeoField,
    value: GeometryValue,
    sketch: GeometryValue,
    edit: str,
    record: BaseModel,
) -> str:
    """The GeoJSON of ``value`` after ``edit`` with ``sketch``, in ``value``'s
    own projection. ``add_area`` joins the drawn area to the shape,
    ``cut_area`` takes it out (a hole when it lies inside), ``remove_part``
    drops the part nearest to the clicked point."""
    if edit not in SHAPE_EDITS:
        raise ValueError(f"{edit!r} is not one of {SHAPE_EDITS}")
    shape = field.entry_to_shape(value, record=record)
    drawn = field.entry_to_shape(sketch, record=record)
    srid = get_srid(shape) or field.srid
    if (get_srid(drawn) or srid) != srid:
        raise ValueError("the sketch and the shape are in different projections")
    if edit == "remove_part":
        result = _without_nearest_part(record, shape, drawn)
    else:
        if "Polygon" not in field.geo_type or drawn.geom_type != "Polygon":
            raise UserError(
                record.env._("Only an area can be added to or cut out of an area.")
            )
        if not drawn.is_valid:
            raise UserError(
                record.env._(
                    "The drawn outline crosses itself; draw it again without crossing."
                )
            )
        result = shape.union(drawn) if edit == "add_area" else shape.difference(drawn)
    if result.is_empty:
        raise UserError(
            record.env._(
                "Nothing of the shape would remain. To remove it, delete the record "
                "or clear its geometry."
            )
        )
    return shape_to_geojson(result, srid)


def _joined(parts: list[BaseGeometry]) -> BaseGeometry:
    return parts[0] if len(parts) == 1 else _MULTI[parts[0].geom_type](parts)


def split_shape(
    field: GeoField,
    shape: BaseGeometry,
    line: GeometryValue,
    record: BaseModel,
) -> tuple[BaseGeometry, list[BaseGeometry]]:
    """``shape`` cut by the drawn ``line``: what the record keeps (the parts the
    line does not cross and the largest piece) and the other pieces."""
    if "Polygon" not in field.geo_type:
        raise UserError(record.env._("Only an area can be split."))
    cut = field.entry_to_shape(line, record=record)
    if cut.geom_type != "LineString":
        raise UserError(record.env._("A shape is split along a drawn line."))
    cut = reproject(cut, get_srid(cut) or field.srid, field.srid)
    untouched, pieces = [], []
    for part in _parts(shape):
        parts = list(split(part, cut).geoms)
        if len(parts) > 1:
            pieces.extend(parts)
        else:
            untouched.append(part)
    if not pieces:
        raise UserError(
            record.env._("The line does not cut the shape: draw it across the shape.")
        )
    largest = max(pieces, key=lambda piece: piece.area)
    others = [piece for piece in pieces if piece is not largest]
    return _joined([*untouched, largest]), others


def merge_shapes(shapes: list[BaseGeometry]) -> BaseGeometry:
    return unary_union(shapes)
