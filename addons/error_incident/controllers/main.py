from typing import Any

from odoo import api, http
from odoo.http import request
from odoo.libs.fixed_window import FixedWindowLimiter

from ..models.error_incident import client_capture_payload

_reports = FixedWindowLimiter(window=60, limit=20)
_MAX_STACK = 20_000


class ErrorIncidentController(http.Controller):
    @http.route(
        "/error_incident/journey",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def journey(self, occurrence: str | None = None) -> dict[str, Any]:
        if not request.env.user._is_internal():
            return {"state": "unavailable"}
        incident = request.env["error.occurrence"]._own_incident(occurrence)
        if not incident:
            return {"state": "pending"}
        return {"state": "found", **incident._journey()}

    @http.route(
        "/error_incident/report",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def report(self, stack: object = None, location: object = None) -> dict[str, Any]:
        env = request.env
        if not env.user._is_internal():
            return {"state": "unavailable"}
        if not isinstance(stack, str) or not stack.strip():
            return {"state": "unavailable"}
        if _reports.is_limited(f"uid:{env.uid}"):
            return {"state": "limited"}
        system = api.Environment(env.cr, api.SUPERUSER_ID, {})
        payload = client_capture_payload(
            system,
            stack[:_MAX_STACK],
            user_id=env.uid,
            location=location[:500] if isinstance(location, str) else None,
        )
        if not env["error.incident"]._capture_quietly(payload):
            return {"state": "unavailable"}
        incident = env["error.occurrence"]._own_incident(payload["occurrence_ref"])
        return {
            "state": "found",
            "occurrence": payload["occurrence_ref"],
            **incident._journey(),
        }
