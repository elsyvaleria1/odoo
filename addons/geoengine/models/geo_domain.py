import logging
import math
from ast import literal_eval

from shapely import get_srid, set_srid, to_wkb
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union

from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import (
    Domain,
    DomainCondition,
    OptimizationLevel,
    operator_optimization,
    register_condition_operators,
)
from odoo.models import BaseModel
from odoo.tools import SQL
from odoo.tools.safe_eval import datetime, dateutil, safe_eval, time

from . import fields as geo_fields
from .fields import WGS84_GEOD, _get_transformer, _parse_geometry, reproject
from .geo_types import (
    DISPLAY_SRID,
    DomainOperator,
    GeometryValue,
    SpatialOperator,
)

logger = logging.getLogger(__name__)


_MIN_METRES_PER_DEGREE_LATITUDE = 110_574
_MIN_METRES_PER_DEGREE_LONGITUDE = 111_300

GEO_OPERATORS = register_condition_operators(op.value for op in DomainOperator)

_SHAPELY_PREDICATE = {
    SpatialOperator.INTERSECTS: "intersects",
    SpatialOperator.CONTAINS: "contains",
    SpatialOperator.WITHIN: "within",
    SpatialOperator.TOUCHES: "touches",
    SpatialOperator.OVERLAPS: "overlaps",
    SpatialOperator.COVERS: "covers",
    SpatialOperator.COVERED_BY: "covered_by",
    SpatialOperator.DISJOINT: "disjoint",
    SpatialOperator.CROSSES: "crosses",
    SpatialOperator.EQUALS: "equals",
}


def parse_domain_text(env, text: str | bool) -> list:
    if not text or not (text := str(text).strip()) or text == "[]":
        return []
    try:
        domain = literal_eval(text)
    except ValueError, SyntaxError:
        domain = safe_eval(
            text,
            {
                "datetime": datetime,
                "time": time,
                "relativedelta": dateutil.relativedelta.relativedelta,
                "context_today": lambda: fields.Date.context_today(env.user),
                "uid": env.uid,
                "user": env.user,
            },
        )
    if not isinstance(domain, (list, tuple)):
        raise ValueError("A domain is a list of conditions")
    return list(domain)


def _geodesic_distance(a: BaseGeometry, b: BaseGeometry) -> float:
    pa, pb = nearest_points(a, b)
    _, _, metres = WGS84_GEOD.inv(pa.x, pa.y, pb.x, pb.y)
    return metres


def _geodesic_search_box(
    geom_wgs84: BaseGeometry, distance: float, srid: int
) -> tuple[float, float, float, float] | None:
    min_x, min_y, max_x, max_y = geom_wgs84.bounds
    margin_lat = distance / _MIN_METRES_PER_DEGREE_LATITUDE
    south = max(-90.0, min_y - margin_lat)
    north = min(90.0, max_y + margin_lat)
    widest = max(abs(south), abs(north))
    west, east = -180.0, 180.0
    if widest < 89.9:
        margin_lon = distance / (
            _MIN_METRES_PER_DEGREE_LONGITUDE * math.cos(math.radians(widest))
        )
        if min_x - margin_lon >= -180.0 and max_x + margin_lon <= 180.0:
            west, east = min_x - margin_lon, max_x + margin_lon
    if srid == DISPLAY_SRID:
        return west, south, east, north
    bounds = _get_transformer(DISPLAY_SRID, srid).transform_bounds(
        west, south, east, north, densify_pts=21
    )
    return bounds if all(math.isfinite(value) for value in bounds) else None


def _empty_operand_domain(field_name: str, spatial_op: SpatialOperator) -> Domain:
    if spatial_op is SpatialOperator.DISJOINT:
        return Domain(field_name, "!=", False)
    return Domain(False)


def _resolve_reference_geometry(
    model: BaseModel,
    model_field: str,
    ref_domain,
) -> tuple[BaseGeometry | None, int]:
    ref_model_name, ref_field_name = model_field.rsplit(".", 1)
    ref_model = model.env[ref_model_name]

    ref_field = ref_model._fields.get(ref_field_name)
    if not isinstance(ref_field, geo_fields.GeoField):
        raise UserError(
            model.env._(
                "%(model)s.%(field)s is not a geometry field and cannot be used "
                "as the right operand of a spatial operator.",
                model=ref_model_name,
                field=ref_field_name,
            )
        )

    ref_model._check_field_access(ref_field, "read")

    if ref_field.store:
        query = ref_model._search(ref_domain)
        column = ref_model._field_to_sql(ref_model._table, ref_field_name, query)
        model.env.cr.execute(
            SQL(
                "SELECT %s",
                query.subselect(
                    SQL("ST_AsEWKB(ST_UnaryUnion(ST_Collect(%s)))", column)
                ),
            )
        )
        row = model.env.cr.fetchone()
        geom = _parse_geometry(row[0]) if row and row[0] else None
        return (geom if geom and not geom.is_empty else None), ref_field.srid

    geometries = [
        geom
        for record in ref_model.search(ref_domain)
        if (geom := record[ref_field_name]) and not geom.is_empty
    ]
    if not geometries:
        return None, ref_field.srid

    geom = unary_union(geometries) if len(geometries) > 1 else geometries[0]
    return geom, ref_field.srid


@operator_optimization(GEO_OPERATORS, OptimizationLevel.DYNAMIC_VALUES)
def optimize_geo_operators(condition: DomainCondition, model: BaseModel) -> Domain:
    field_name: str = condition.field_expr
    operator: str = condition.operator
    value: GeometryValue = condition.value

    field = model._fields.get(field_name)
    if not isinstance(field, geo_fields.GeoField):
        raise UserError(
            model.env._(
                "Spatial operator '%(operator)s' cannot be used on %(model)s.%(field)s, "
                "which is not a geometry field.",
                operator=operator,
                model=model._name,
                field=field_name,
            )
        )

    spatial_op = DomainOperator(operator).to_spatial_operator()

    distance = None
    use_geography = False
    geom_value = value
    if spatial_op is SpatialOperator.DWITHIN:
        if not isinstance(value, dict) or "geometry" not in value:
            raise UserError(
                model.env._(
                    "geo_dwithin requires a dict with 'geometry' and 'distance' keys, "
                    "e.g. [('%(field)s', 'geo_dwithin', "
                    "{'geometry': geom, 'distance': 1000})].",
                    field=field_name,
                )
            )
        geom_value = value["geometry"]
        try:
            distance = float(value.get("distance", 0))
        except (TypeError, ValueError) as exc:
            raise UserError(
                model.env._("geo_dwithin 'distance' must be a number.")
            ) from exc
        unit = value.get("unit", "srid")
        if unit not in ("srid", "m"):
            raise UserError(
                model.env._(
                    "geo_dwithin 'unit' must be 'm' or 'srid', got '%(unit)s'.",
                    unit=unit,
                )
            )
        use_geography = unit == "m"

    if isinstance(geom_value, dict) and len(geom_value) == 1:
        model_field = next(iter(geom_value))
        if "." not in model_field:
            raise UserError(
                model.env._(
                    "A dict operand must reference another model's geometry field, "
                    "e.g. {'res.partner.location': [('active', '=', True)]}; "
                    "got '%(key)s'.",
                    key=model_field,
                )
            )
        geom, src_srid = _resolve_reference_geometry(
            model, model_field, geom_value[model_field]
        )
        if geom is None:
            return _empty_operand_domain(field_name, spatial_op)
    else:
        try:
            geom = _parse_geometry(geom_value)
        except (ValueError, TypeError) as exc:
            raise UserError(
                model.env._(
                    "Invalid geometry for '%(operator)s' on %(model)s.%(field)s: %(error)s",
                    operator=operator,
                    model=model._name,
                    field=field_name,
                    error=str(exc),
                )
            ) from exc
        src_srid = (get_srid(geom) if geom else 0) or field.srid

    if not geom or geom.is_empty:
        return _empty_operand_domain(field_name, spatial_op)

    geom = reproject(geom, src_srid, field.srid)
    ewkb = to_wkb(set_srid(geom, field.srid), include_srid=True)

    geom_wgs84 = reproject(geom, field.srid, DISPLAY_SRID) if use_geography else None
    ewkb_wgs84 = (
        to_wkb(set_srid(geom_wgs84, DISPLAY_SRID), include_srid=True)
        if use_geography
        else None
    )
    search_box = (
        _geodesic_search_box(geom_wgs84, distance, field.srid)
        if use_geography
        else None
    )

    def to_sql(model: BaseModel, alias: str, query) -> SQL:
        model._check_field_access(field, "read")
        column = model._field_to_sql(alias, field_name, query)
        operand = SQL("ST_GeomFromEWKB(%s)", ewkb)
        if spatial_op is SpatialOperator.DWITHIN:
            if use_geography:
                column_geog = (
                    column
                    if field.srid == DISPLAY_SRID
                    else SQL("ST_Transform(%s, %s)", column, DISPLAY_SRID)
                )
                within = SQL(
                    "ST_DWithin(%s::geography, ST_GeomFromEWKB(%s)::geography, %s)",
                    column_geog,
                    ewkb_wgs84,
                    distance,
                )
                if search_box is None:
                    return within
                return SQL(
                    "(%s && ST_MakeEnvelope(%s, %s, %s, %s, %s) AND %s)",
                    column,
                    *search_box,
                    field.srid,
                    within,
                )
            return SQL("ST_DWithin(%s, %s, %s)", column, operand, distance)
        return SQL(
            "%s(%s, %s)",
            SQL(spatial_op.value),
            column,
            operand,
        )

    def predicate(record: BaseModel) -> bool:
        if not (shape := record[field_name]):
            return False
        if spatial_op is SpatialOperator.DWITHIN:
            if use_geography:
                return (
                    _geodesic_distance(
                        reproject(shape, field.srid, DISPLAY_SRID), geom_wgs84
                    )
                    <= distance
                )
            return shape.dwithin(geom, distance)
        return getattr(shape, _SHAPELY_PREDICATE[spatial_op])(geom)

    return Domain.custom(to_sql=to_sql, predicate=predicate)
