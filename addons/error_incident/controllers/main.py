from typing import Any

from odoo import api, http
from odoo.http import request
from odoo.libs.fixed_window import FixedWindowLimiter

from ..models.error_incident import client_capture_payload

# A browser reports what its dialogs show: a few a minute is a bad day, more is
# a loop or a script.
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
        """Where the incident of the caller's own occurrence stands.

        ``pending`` stands for an occurrence not written yet -- the error
        response leaves before its occurrence is recorded -- and, alike, for
        one that is not the caller's: telling them apart would make this an
        oracle for other users' errors.
        """
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
        """Record an error the browser raised on its own, and answer where its
        incident stands -- the server-side answer the dialog of a request
        error gets from `journey`.

        The stack is the browser's word, so it locates the error and nothing
        more: the user is the session's, and what is stored is masked and
        capped.
        """
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
