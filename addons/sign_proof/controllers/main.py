from typing import Any

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.sign.controllers.main import Sign


class SignProof(Sign):
    @http.route(
        "/sign/proof/<int:request_id>/<token>",
        type="jsonrpc",
        auth="public",
    )
    def send_proof_code(self, request_id, token):
        request_item = (
            request.env["sign.request.item"]
            ._from_signer_token(token, request_id)
            .filtered(lambda item: item.state == "sent")
        )
        if not request_item or request_item.role_id.auth_method != "proof":
            return {"error": request.env._("This signature does not ask for a code.")}
        try:
            params = request_item._issue_signer_proof()
        except UserError as error:
            return {"error": str(error)}
        return {
            "token": params["token"],
            "method": params["methods"][0]["code"],
            "sent_to": ", ".join(
                method["options"]["sent_to"] for method in params["methods"]
            ),
        }

    def _acquire_auth_method_result(
        self, request_item_sudo, sms_token=None, **kwargs
    ) -> dict[str, Any]:
        if request_item_sudo.role_id.auth_method != "proof":
            return super()._acquire_auth_method_result(
                request_item_sudo, sms_token=sms_token, **kwargs
            )
        proof = kwargs.get("proof")
        if not isinstance(proof, dict):
            return {"success": False, "proof": True}
        try:
            request_item_sudo._redeem_signer_proof(proof)
        except UserError as error:
            return {"success": False, "proof": True, "message": str(error)}
        return {"success": True}
