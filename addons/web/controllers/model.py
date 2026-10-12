from typing import Any

from odoo.http import BadRequest, Controller, Response, request, route
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps, loads

_debug = DebugLog(__name__)


class Model(Controller):
    @route(
        "/web/model/get_definitions",
        methods=["POST"],
        type="http",
        auth="user",
        readonly=True,
    )
    def get_model_definitions(self, model_names: str, **kwargs: Any) -> Response:
        try:
            names = loads(model_names)
        except ValueError as exc:
            _debug.logic("definitions_get_rejected", reason="not_json")
            raise BadRequest("model_names must be a JSON list of model names.") from exc
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            _debug.logic("definitions_get_rejected", reason="not_a_list")
            raise BadRequest("model_names must be a JSON list of model names.")
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "definitions_get", models=len(names), ignored=sorted(kwargs)
            )
        with _debug.perf("definitions_build", cr=request.env.cr, models=len(names)):
            definitions = request.env["ir.model"]._get_definitions(names)
        if _debug.perf.enabled:
            _debug.perf.count(
                "definitions_size",
                models=len(names),
                definitions=len(definitions),
                fields=sum(len(d.get("fields", ())) for d in definitions.values()),
            )
        return request.prepare_response(
            dumps(definitions),
            headers=[("Content-Type", "application/json")],
        )
