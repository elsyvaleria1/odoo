import odoo.release
from odoo import http
from odoo.http import Forbidden, request
from odoo.http.openapi import prepare_openapi_from_map
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class OpenAPI(http.Controller):
    @http.route(
        "/web/openapi.json", type="http", auth="user", methods=["GET"], readonly=True
    )
    def openapi_json(self):
        _debug.lifecycle("openapi_document")
        if not request.env.user.has_group("base.group_system"):
            _debug.logic("openapi_document_refused", reason="not_system")
            raise Forbidden("Only system administrators may read the API document.")
        with _debug.perf("openapi_document_build", cr=request.env.cr):
            ir_http = request.env["ir.http"]
            resolver = getattr(ir_http, "_openapi_security_for", None)
            document = prepare_openapi_from_map(
                ir_http.routing_map(),
                title="Odoo HTTP API",
                version=odoo.release.major_version,
                servers=[{"url": request.httprequest.url_root.rstrip("/")}],
                typed_only=True,
                security_resolver=resolver,
            )
        _debug.perf.count(
            "openapi_document_size",
            paths=len(document.get("paths", ())),
            schemas=len(document.get("components", {}).get("schemas", ())),
        )
        return request.prepare_json_response(document)
