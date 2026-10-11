from werkzeug.exceptions import NotFound

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.stock_fleet_trace.controllers.main import (
    DRIVER_PAGE,
    StockFleetTraceOffline,
)

PLUGIN = "/stock_fleet_trace_proof/static/driver/confirm_code.js"


class StockFleetTraceProof(StockFleetTraceOffline):
    def _get_driver_terms(self, env):
        _ = env._
        return {
            **super()._get_driver_terms(env),
            "confirm_code": _("Customer is here: confirm with a code"),
            "confirm_code_send": _("Send the customer a code"),
            "confirm_code_sent": _(
                "Code sent to %(sent_to)s. Type the code they read you."
            ),
            "confirm_code_check": _("Confirm"),
            "confirm_code_done": _("The customer confirmed this delivery."),
            "confirm_code_offline": _("Needs signal: capture the signature instead."),
        }

    def _get_driver_plugins(self):
        return [*super()._get_driver_plugins(), PLUGIN]

    def _picking(self, picking_id):
        picking = request.env["stock.picking"].browse(picking_id).exists()
        if (
            not picking
            or not picking.has_access("write")
            or picking.batch_id.operator_id.user_id != request.env.user
        ):
            raise NotFound
        return picking

    @http.route(
        f"{DRIVER_PAGE}/confirm_code/issue",
        methods=["POST"],
        type="jsonrpc",
        auth="user",
    )
    def confirm_code_issue(self, picking_id):
        params = self._picking(picking_id).action_issue_confirmation_code()
        return {
            "token": params["token"],
            "method": params["methods"][0]["code"],
            "sent_to": ", ".join(
                method["options"]["sent_to"] for method in params["methods"]
            ),
        }

    @http.route(
        f"{DRIVER_PAGE}/confirm_code/prove",
        methods=["POST"],
        type="jsonrpc",
        auth="user",
    )
    def confirm_code_prove(self, picking_id, token, method, code):
        picking = self._picking(picking_id)
        try:
            picking.action_prove_confirmation_code(
                {"token": token, "method": method, "payload": {"code": code}}
            )
        except UserError as error:
            return {"error": str(error)}
        return {"confirmed": True}
