from enum import StrEnum
from itertools import pairwise
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shapely.geometry.base import BaseGeometry


class SpatialOperator(StrEnum):
    INTERSECTS = "ST_Intersects"
    CONTAINS = "ST_Contains"
    WITHIN = "ST_Within"
    TOUCHES = "ST_Touches"
    OVERLAPS = "ST_Overlaps"
    COVERS = "ST_Covers"
    COVERED_BY = "ST_CoveredBy"
    DISJOINT = "ST_Disjoint"
    CROSSES = "ST_Crosses"
    EQUALS = "ST_Equals"

    DWITHIN = "ST_DWithin"


class DomainOperator(StrEnum):
    INTERSECT = "geo_intersect"
    CONTAINS = "geo_contains"
    WITHIN = "geo_within"
    TOUCH = "geo_touch"
    EQUAL = "geo_equal"
    OVERLAP = "geo_overlap"
    COVERS = "geo_covers"
    COVERED_BY = "geo_covered_by"
    DISJOINT = "geo_disjoint"
    CROSSES = "geo_crosses"

    DWITHIN = "geo_dwithin"

    def to_spatial_operator(self) -> SpatialOperator:
        return _SPATIAL_OPERATOR_OF[self]


_SPATIAL_OPERATOR_OF: dict[DomainOperator, SpatialOperator] = {
    DomainOperator.INTERSECT: SpatialOperator.INTERSECTS,
    DomainOperator.CONTAINS: SpatialOperator.CONTAINS,
    DomainOperator.WITHIN: SpatialOperator.WITHIN,
    DomainOperator.TOUCH: SpatialOperator.TOUCHES,
    DomainOperator.EQUAL: SpatialOperator.EQUALS,
    DomainOperator.OVERLAP: SpatialOperator.OVERLAPS,
    DomainOperator.COVERS: SpatialOperator.COVERS,
    DomainOperator.COVERED_BY: SpatialOperator.COVERED_BY,
    DomainOperator.DISJOINT: SpatialOperator.DISJOINT,
    DomainOperator.CROSSES: SpatialOperator.CROSSES,
    DomainOperator.DWITHIN: SpatialOperator.DWITHIN,
}


DEFAULT_SRID: int = 3857
DISPLAY_SRID: int = 4326

CLIENT_RENDERABLE_SRIDS: frozenset[int] = frozenset(
    {
        4326,
        3857,
        900913,
        *range(32601, 32661),
        *range(32701, 32761),
    },
)


def is_client_renderable_srid(srid: int) -> bool:
    return srid in CLIENT_RENDERABLE_SRIDS


def parse_epsg_code(raw: str | bool) -> int | None:
    code = str(raw or "").strip()
    digits = code[5:]
    if code[:5].upper() != "EPSG:" or not (digits.isascii() and digits.isdigit()):
        return None
    return int(digits)


GEO_FIELD_TTYPES: tuple[str, ...] = (
    "geo_point",
    "geo_line",
    "geo_polygon",
    "geo_multi_point",
    "geo_multi_line",
    "geo_multi_polygon",
)

POINT_TTYPES: tuple[str, ...] = ("geo_point", "geo_multi_point")


type GeometryValue = BaseGeometry | str | None


def parse_extent(raw: str | bool) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = [part.strip() for part in str(raw).split(",")]
    if len(parts) != 4:
        return None
    try:
        min_x, min_y, max_x, max_y = (float(part) for part in parts)
    except ValueError:
        return None
    if min_x >= max_x or min_y >= max_y:
        return None
    return min_x, min_y, max_x, max_y


def parse_resolutions(raw: str | bool) -> list[float] | None:
    if not raw:
        return None
    parts = [part.strip() for part in str(raw).split(",")]
    try:
        values = [float(part) for part in parts]
    except ValueError:
        return None
    if not values or any(value <= 0 for value in values):
        return None
    if any(later >= earlier for earlier, later in pairwise(values)):
        return None
    return values
