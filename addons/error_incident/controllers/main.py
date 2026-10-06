from typing import Any

from odoo import http
from odoo.http import request


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
