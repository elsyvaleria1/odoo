"""OGC API - Features (Part 1, core and GeoJSON) over the geometries geoengine
maps draw, for GIS clients such as QGIS.

A collection is one stored geo field of a model a geoengine vector layer
draws, offered only where the caller can read the model and the field; its
features carry the fields of that model's geoengine view as properties.
Everything is read as the caller, through ``_search`` and ``read``, so record
rules and field access apply exactly as in the client."""

import datetime
from dataclasses import dataclass

from lxml import etree

from odoo.exceptions import UserError
from odoo.models import BaseModel
from odoo.tools import SQL

from .fields import GeoField
from .vector_tiles import fetch_within_budget

CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
CONFORMANCE = [
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
]
DEFAULT_LIMIT = 100
LIST_EXTENT_TIMEOUT_MS = 300
MAX_LIMIT = 10_000
WGS84 = 4326
GEOJSON_DIGITS = 8
BBOX_SEGMENTS = 16
PROPERTY_TYPES = frozenset(
    {
        "boolean",
        "char",
        "date",
        "datetime",
        "float",
        "integer",
        "many2one",
        "monetary",
        "selection",
        "text",
    }
)


class OgcRequestError(UserError):
    """A request the API cannot answer as asked (HTTP 400)."""


class TooDense(Exception):
    """The query did not finish within geoengine.tile_timeout_ms (HTTP 503)."""


@dataclass(frozen=True)
class Collection:
    model_name: str
    field_name: str
    title: str

    @property
    def id(self) -> str:
        return f"{self.model_name}.{self.field_name}"


def collections(env) -> list[Collection]:
    found = {}
    for layer in env["geoengine.vector.layer"].search([]):
        model_name = layer._target_model_name()
        if not model_name or model_name not in env:
            continue
        model = env[model_name]
        if not model.has_access("read"):
            continue
        field = model._fields.get(layer.geo_field_id.name)
        if not isinstance(field, GeoField) or not field.store:
            continue
        if not model._has_field_access(field, "read"):
            continue
        key = (model_name, field.name)
        if key not in found:
            found[key] = Collection(
                model_name, field.name, f"{model._description} · {field.string}"
            )
    return sorted(found.values(), key=lambda collection: collection.id)


def find_collection(env, collection_id: str) -> Collection | None:
    return next((c for c in collections(env) if c.id == collection_id), None)


def property_names(env, collection: Collection) -> list[str]:
    model = env[collection.model_name]
    arch = model.get_view(view_type="geoengine")["arch"]
    names = []
    for node in etree.fromstring(arch).iter("field"):
        name = node.get("name")
        field = model._fields.get(name)
        if (
            field is not None
            and name != "id"
            and name not in names
            and field.type in PROPERTY_TYPES
            and model._has_field_access(field, "read")
        ):
            names.append(name)
    return names


def parse_bbox(env, raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    try:
        minx, miny, maxx, maxy = (float(part) for part in raw.split(","))
    except ValueError:
        raise OgcRequestError(
            env._("bbox is four comma-separated CRS84 numbers: minx,miny,maxx,maxy.")
        ) from None
    minx, maxx = max(minx, -180.0), min(maxx, 180.0)
    miny, maxy = max(miny, -90.0), min(maxy, 90.0)
    if not (minx < maxx and miny < maxy):
        raise OgcRequestError(
            env._("bbox must have minx below maxx and miny below maxy.")
        )
    return minx, miny, maxx, maxy


def parse_page(env, limit: str | None, offset: str | None) -> tuple[int, int]:
    try:
        limit_value = DEFAULT_LIMIT if limit in (None, "") else int(limit)
        offset_value = 0 if offset in (None, "") else int(offset)
    except ValueError:
        raise OgcRequestError(env._("limit and offset are whole numbers.")) from None
    if limit_value < 1 or offset_value < 0:
        raise OgcRequestError(env._("limit must be at least 1 and offset at least 0."))
    return min(limit_value, MAX_LIMIT), offset_value


def _bbox_in(bbox: tuple[float, float, float, float], srid: int) -> SQL:
    minx, miny, maxx, maxy = bbox
    envelope = SQL("ST_MakeEnvelope(%s, %s, %s, %s, %s)", minx, miny, maxx, maxy, WGS84)
    if srid == WGS84:
        return envelope
    return SQL(
        "ST_Transform(ST_Segmentize(%s, %s), %s)",
        envelope,
        max(maxx - minx, maxy - miny) / BBOX_SEGMENTS,
        srid,
    )


def _in_wgs84(column: SQL, srid: int) -> SQL:
    return column if srid == WGS84 else SQL("ST_Transform(%s, %s)", column, WGS84)


def _geometries(
    model: BaseModel,
    field: GeoField,
    domain,
    *,
    bbox=None,
    limit: int | None = None,
    offset: int = 0,
) -> list[list]:
    query = model._search(domain, order="id")
    column = model._field_to_sql(query.table, field.name, query)
    if bbox:
        query.add_where(SQL("%s && %s", column, _bbox_in(bbox, field.srid)))
    query.limit = limit
    query.offset = offset
    rows = query.select(
        SQL("%s AS id", SQL.identifier(query.table, "id")),
        SQL(
            "ST_AsGeoJSON(%s, %s)::json AS geometry",
            _in_wgs84(column, field.srid),
            GEOJSON_DIGITS,
        ),
    )
    row = fetch_within_budget(
        model.env,
        SQL(
            "SELECT coalesce(json_agg(json_build_array(r.id, r.geometry) ORDER BY r.id), '[]') FROM (%s) AS r",
            rows,
        ),
    )
    if row is None:
        raise TooDense
    return row[0]


def _property_value(field, value):
    if field.type == "many2one":
        return value[1] if value else None
    if field.type == "boolean":
        return bool(value)
    if value is False:
        return None
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def _features(env, collection: Collection, rows: list[list]) -> list[dict]:
    model = env[collection.model_name]
    names = property_names(env, collection)
    values = {}
    if names and rows:
        for record in model.browse([fid for fid, _geometry in rows]).read(names):
            values[record["id"]] = {
                name: _property_value(model._fields[name], record[name])
                for name in names
            }
    return [
        {
            "type": "Feature",
            "id": fid,
            "geometry": geometry,
            "properties": values.get(fid, {}),
        }
        for fid, geometry in rows
    ]


def collection_extent(
    env, collection: Collection, timeout_ms: int | None = None
) -> list[float] | None:
    model = env[collection.model_name]
    field = model._fields[collection.field_name]
    query = model._search([])
    query.order = None
    column = model._field_to_sql(query.table, field.name, query)
    extent = SQL("ST_SetSRID(ST_Extent(%s)::geometry, %s)", column, field.srid)
    row = fetch_within_budget(
        env,
        SQL(
            """SELECT ST_XMin(b), ST_YMin(b), ST_XMax(b), ST_YMax(b)
                 FROM (SELECT %s AS b
                         FROM (%s) AS x(e)) AS bounds""",
            _in_wgs84(
                SQL(
                    "ST_Segmentize(x.e, greatest(ST_XMax(x.e) - ST_XMin(x.e), "
                    "ST_YMax(x.e) - ST_YMin(x.e), 1e-9) / %s)",
                    BBOX_SEGMENTS,
                ),
                field.srid,
            ),
            query.select(extent),
        ),
        timeout_ms,
    )
    if row is None or row[0] is None:
        return None
    return list(row)


def _link(href: str, rel: str, media_type: str, title: str | None = None) -> dict:
    link = {"href": href, "rel": rel, "type": media_type}
    if title:
        link["title"] = title
    return link


def landing_page(env, base: str) -> dict:
    return {
        "title": env._("Odoo map data"),
        "description": env._(
            "The geometries the geoengine maps of this database draw, as "
            "OGC API - Features collections."
        ),
        "links": [
            _link(f"{base}", "self", "application/json"),
            _link(
                f"{base}/api",
                "service-desc",
                "application/vnd.oai.openapi+json;version=3.0",
            ),
            _link(f"{base}/conformance", "conformance", "application/json"),
            _link(f"{base}/collections", "data", "application/json"),
        ],
    }


def _parameter(name: str, schema: dict, description: str, where: str = "query") -> dict:
    return {
        "name": name,
        "in": where,
        "required": where == "path",
        "description": description,
        "schema": schema,
    }


def api_definition(env, base: str) -> dict:
    json_ok = {"200": {"description": "OK", "content": {"application/json": {}}}}
    geojson_ok = {
        "200": {"description": "OK", "content": {"application/geo+json": {}}},
        "400": {"description": "Invalid parameter"},
        "404": {"description": "No such collection or feature"},
        "503": {"description": "The query did not finish in time"},
    }
    collection_id = _parameter(
        "collectionId", {"type": "string"}, "Collection id", "path"
    )
    return {
        "openapi": "3.0.3",
        "info": {"title": env._("Odoo map data"), "version": "1.0"},
        "servers": [{"url": base}],
        "components": {
            "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}}
        },
        "security": [{"bearer": []}],
        "paths": {
            "/": {"get": {"operationId": "getLandingPage", "responses": json_ok}},
            "/conformance": {
                "get": {"operationId": "getConformance", "responses": json_ok}
            },
            "/collections": {
                "get": {"operationId": "getCollections", "responses": json_ok}
            },
            "/collections/{collectionId}": {
                "get": {
                    "operationId": "describeCollection",
                    "parameters": [collection_id],
                    "responses": json_ok,
                }
            },
            "/collections/{collectionId}/items": {
                "get": {
                    "operationId": "getFeatures",
                    "parameters": [
                        collection_id,
                        _parameter(
                            "limit",
                            {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": MAX_LIMIT,
                                "default": DEFAULT_LIMIT,
                            },
                            "Features per page",
                        ),
                        _parameter(
                            "offset",
                            {"type": "integer", "minimum": 0, "default": 0},
                            "Features to skip",
                        ),
                        _parameter(
                            "bbox",
                            {
                                "type": "array",
                                "minItems": 4,
                                "maxItems": 4,
                                "items": {"type": "number"},
                            },
                            "minx,miny,maxx,maxy in CRS84",
                        ),
                    ],
                    "responses": geojson_ok,
                }
            },
            "/collections/{collectionId}/items/{featureId}": {
                "get": {
                    "operationId": "getFeature",
                    "parameters": [
                        collection_id,
                        _parameter(
                            "featureId", {"type": "integer"}, "Record id", "path"
                        ),
                    ],
                    "responses": geojson_ok,
                }
            },
        },
    }


def conformance() -> dict:
    return {"conformsTo": CONFORMANCE}


def collection_description(
    env, collection: Collection, base: str, extent_timeout_ms: int | None = None
) -> dict:
    href = f"{base}/collections/{collection.id}"
    description = {
        "id": collection.id,
        "title": collection.title,
        "itemType": "feature",
        "crs": [CRS84],
        "links": [
            _link(href, "self", "application/json"),
            _link(f"{href}/items", "items", "application/geo+json"),
        ],
    }
    if bbox := collection_extent(env, collection, extent_timeout_ms):
        description["extent"] = {"spatial": {"bbox": [bbox], "crs": CRS84}}
    return description


def collections_document(env, base: str) -> dict:
    return {
        "links": [_link(f"{base}/collections", "self", "application/json")],
        "collections": [
            collection_description(env, collection, base, LIST_EXTENT_TIMEOUT_MS)
            for collection in collections(env)
        ],
    }


def items(
    env,
    collection: Collection,
    base: str,
    *,
    bbox=None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    model = env[collection.model_name]
    field = model._fields[collection.field_name]
    rows = _geometries(model, field, [], bbox=bbox, limit=limit + 1, offset=offset)
    more = len(rows) > limit
    rows = rows[:limit]
    href = f"{base}/collections/{collection.id}/items"
    query = f"&bbox={','.join(map(str, bbox))}" if bbox else ""
    links = [
        _link(
            f"{href}?limit={limit}&offset={offset}{query}",
            "self",
            "application/geo+json",
        )
    ]
    if more:
        links.append(
            _link(
                f"{href}?limit={limit}&offset={offset + limit}{query}",
                "next",
                "application/geo+json",
            )
        )
    if offset:
        links.append(
            _link(
                f"{href}?limit={limit}&offset={max(offset - limit, 0)}{query}",
                "prev",
                "application/geo+json",
            )
        )
    return {
        "type": "FeatureCollection",
        "features": _features(env, collection, rows),
        "numberReturned": len(rows),
        "timeStamp": datetime.datetime.now(datetime.UTC)
        .replace(microsecond=0)
        .isoformat(),
        "links": links,
    }


def item(env, collection: Collection, feature_id: int, base: str) -> dict | None:
    model = env[collection.model_name]
    field = model._fields[collection.field_name]
    rows = _geometries(model, field, [("id", "=", feature_id)], limit=1)
    if not rows:
        return None
    [feature] = _features(env, collection, rows)
    href = f"{base}/collections/{collection.id}/items/{feature_id}"
    feature["links"] = [
        _link(href, "self", "application/geo+json"),
        _link(f"{base}/collections/{collection.id}", "collection", "application/json"),
    ]
    return feature
