import functools
import logging

from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError

from odoo.tools import SQL

from .geo_types import is_client_renderable_srid, parse_epsg_code

_logger = logging.getLogger(__name__)

EXTENT_DENSIFY_POINTS = 21


@functools.lru_cache(maxsize=256)
def _area_of_use_extent(srid: int) -> tuple[float, float, float, float] | None:
    try:
        area = CRS.from_epsg(srid).area_of_use
    except CRSError:
        return None
    if area is None:
        return None
    bounds = Transformer.from_crs(4326, srid, always_xy=True).transform_bounds(
        area.west, area.south, area.east, area.north, densify_pts=EXTENT_DENSIFY_POINTS
    )
    return bounds if all(abs(value) != float("inf") for value in bounds) else None


def projection_definition(env, srid: int) -> dict | None:
    """What OpenLayers needs to draw in ``EPSG:<srid>`` when it cannot resolve
    the code itself: PostGIS's proj4 text and the CRS's area of use, as the
    projection's extent. None for a CRS OpenLayers resolves, or one PostGIS
    cannot describe."""
    if is_client_renderable_srid(srid):
        return None
    [row] = env.execute_query(
        SQL("SELECT auth_name, proj4text FROM spatial_ref_sys WHERE srid = %s", srid)
    ) or [(None, None)]
    auth_name, proj4text = row
    if auth_name != "EPSG" or not (proj4text or "").strip():
        return None
    extent = _area_of_use_extent(srid)
    return {
        "code": f"EPSG:{srid}",
        "proj4": proj4text.strip(),
        "extent": list(extent) if extent else None,
    }


def is_drawable_projection(env, srid: int) -> bool:
    return (
        is_client_renderable_srid(srid) or projection_definition(env, srid) is not None
    )


def projection_definitions(env, codes) -> list[dict]:
    definitions = {}
    for code in codes:
        if (srid := parse_epsg_code(code)) is None or srid in definitions:
            continue
        if definition := projection_definition(env, srid):
            definitions[srid] = definition
    return list(definitions.values())
