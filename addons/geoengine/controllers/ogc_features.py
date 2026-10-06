from http import HTTPStatus

from odoo import http
from odoo.http import Response, request

from ..models import ogc_features as ogc

ROUTE = {
    "type": "http",
    "auth": "bearer",
    "scope": "ogcapi",
    "methods": ["GET"],
    "readonly": True,
    "typed": True,
}
JSON = "application/json"
GEOJSON = "application/geo+json"


class OgcFeaturesController(http.Controller):
    @http.route("/ogcapi", **ROUTE)
    def ogc_landing_page(self, **params: str) -> Response:
        return self._json(ogc.landing_page(request.env, self._base()))

    @http.route("/ogcapi/api", **ROUTE)
    def ogc_api_definition(self, **params: str) -> Response:
        return self._json(
            ogc.api_definition(request.env, self._base()),
            "application/vnd.oai.openapi+json;version=3.0",
        )

    @http.route("/ogcapi/conformance", **ROUTE)
    def ogc_conformance(self, **params: str) -> Response:
        return self._json(ogc.conformance())

    @http.route("/ogcapi/collections", **ROUTE)
    def ogc_collections(self, **params: str) -> Response:
        return self._json(ogc.collections_document(request.env, self._base()))

    @http.route("/ogcapi/collections/<string:collection_id>", **ROUTE)
    def ogc_collection(self, collection_id: str, **params: str) -> Response:
        collection = self._collection(collection_id)
        if collection is None:
            return self._not_found(collection_id)
        return self._json(
            ogc.collection_description(request.env, collection, self._base())
        )

    @http.route("/ogcapi/collections/<string:collection_id>/items", **ROUTE)
    def ogc_items(self, collection_id: str, **params: str) -> Response:
        collection = self._collection(collection_id)
        if collection is None:
            return self._not_found(collection_id)
        env = request.env
        try:
            bbox = ogc.parse_bbox(env, params.get("bbox"))
            limit, offset = ogc.parse_page(
                env, params.get("limit"), params.get("offset")
            )
            document = ogc.items(
                env, collection, self._base(), bbox=bbox, limit=limit, offset=offset
            )
        except ogc.OgcRequestError as error:
            return self._error(
                HTTPStatus.BAD_REQUEST, "InvalidParameterValue", str(error)
            )
        except ogc.TooDense:
            return self._too_dense()
        return self._json(document, GEOJSON)

    @http.route(
        "/ogcapi/collections/<string:collection_id>/items/<int:feature_id>", **ROUTE
    )
    def ogc_item(self, collection_id: str, feature_id: int, **params: str) -> Response:
        collection = self._collection(collection_id)
        if collection is None:
            return self._not_found(collection_id)
        try:
            feature = ogc.item(request.env, collection, feature_id, self._base())
        except ogc.TooDense:
            return self._too_dense()
        if feature is None:
            return self._error(
                HTTPStatus.NOT_FOUND,
                "NotFound",
                request.env._("No feature %s in this collection.", feature_id),
            )
        return self._json(feature, GEOJSON)

    def _base(self) -> str:
        return request.httprequest.host_url.rstrip("/") + "/ogcapi"

    def _collection(self, collection_id: str) -> ogc.Collection | None:
        return ogc.find_collection(request.env, collection_id)

    def _json(self, data: dict, media_type: str = JSON) -> Response:
        return request.prepare_json_response(
            data, headers=[("Content-Type", media_type)]
        )

    def _error(self, status: HTTPStatus, code: str, description: str) -> Response:
        return request.prepare_json_response(
            {"code": code, "description": description}, status=status.value
        )

    def _not_found(self, collection_id: str) -> Response:
        return self._error(
            HTTPStatus.NOT_FOUND,
            "NotFound",
            request.env._("No collection %s.", collection_id),
        )

    def _too_dense(self) -> Response:
        return self._error(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "Timeout",
            request.env._(
                "The query did not finish in time. Narrow it with bbox or a smaller limit."
            ),
        )
