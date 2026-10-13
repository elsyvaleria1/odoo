import re
from dataclasses import dataclass

from shapely import get_srid, is_valid_reason
from shapely.geometry import Point

from odoo.exceptions import ValidationError
from odoo.models import BaseModel

from .fields import (
    GeoField,
    geometry_size,
    geometry_size_bound,
    max_geometry_size,
    reproject,
)
from .geo_types import GeometryValue

_LOCATED_REASON = re.compile(r"^(?P<kind>[^\[]*)\[(?P<x>\S+) (?P<y>\S+)(?: \S+)?\]$")


@dataclass(frozen=True)
class GeometryProblem:
    message: str
    location: tuple[float, float] | None = None


def _describe(record: BaseModel, kind: str) -> str:
    env = record.env
    match kind:
        case "Self-intersection" | "Ring Self-intersection":
            return env._("The outline crosses itself here.")
        case "Hole lies outside shell":
            return env._("A hole reaches outside the outline here.")
        case "Nested holes" | "Interior is disconnected":
            return env._("The holes cut the area in two here.")
        case "Nested shells" | "Duplicate Rings":
            return env._("Two outlines overlap here.")
        case "Too few points":
            return env._("The shape has too few points to enclose an area.")
        case _:
            return env._("The shape is not valid: %s", kind)


def find_geometry_problem(
    field: GeoField,
    value: GeometryValue,
    record: BaseModel,
) -> GeometryProblem | None:
    try:
        shape = field.entry_to_shape(value, record=record)
    except ValidationError as error:
        return GeometryProblem(str(error.args[0]))
    source_srid = get_srid(shape) or field.srid
    stored = field._coerce_dimension(reproject(shape, source_srid, field.srid))

    if not stored.is_valid:
        reason = is_valid_reason(stored) or ""
        if located := _LOCATED_REASON.match(reason):
            spot = reproject(
                Point(float(located["x"]), float(located["y"])),
                field.srid,
                source_srid,
            )
            return GeometryProblem(_describe(record, located["kind"]), (spot.x, spot.y))
        return GeometryProblem(_describe(record, reason))

    try:
        field._coerce_to_geo_type(stored, record)
    except ValidationError as error:
        return GeometryProblem(str(error.args[0]))

    max_size = max_geometry_size(record.env)
    if geometry_size_bound(stored) > max_size and geometry_size(stored) > max_size:
        return GeometryProblem(
            record.env._(
                "The shape has too many points to store (%(size)d bytes, at most "
                "%(maximum)d).",
                size=geometry_size(stored),
                maximum=max_size,
            )
        )
    return None
