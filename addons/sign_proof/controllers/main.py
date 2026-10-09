from typing import Any

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.sign.controllers.main import Sign

# codes one signer is sent, and one visitor's address asks for: at once, then
# refilled over the seconds
SIGNER_BUDGET = (3, 1800)
VISITOR_BUDGET = (10, 3600)


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
        sign_request = request_item.sign_request_id
        if (
            not request_item
            or not request_item.partner_id
            or request_item.role_id.auth_method != "proof"
            or (sign_request.validity and sign_request.validity < fields.Date.today())
        ):
            return {"error": request.env._("This signature does not ask for a code.")}
        # a public page: a signer, and a visitor's address, get so many codes
        if not request_item._consume_send_budget(
            "proof_code", *SIGNER_BUDGET
        ) or not self._consume_visitor_budget(request_item):
            return {
                "error": request.env._(
                    "Several codes were just sent. Use the last one, or wait a "
                    "few minutes before asking for another."
                )
            }
        try:
            params = request_item._issue_signer_proof()
        except UserError as error:
            return {"error": str(error)}
        coded = [
            method
            for method in params["methods"]
            if (method.get("options") or {}).get("sent_to")
        ]
        if not coded:
            return {"error": request.env._("No code could be sent to the signer.")}
        return {
            "token": params["token"],
            "method": coded[0]["code"],
            "sent_to": ", ".join(method["options"]["sent_to"] for method in coded),
        }

    def _consume_visitor_budget(self, request_item) -> bool:
        remote = request.httprequest.remote_addr or "-"
        return request_item.env["rate.limit.bucket"].consume_for_key(
            f"sign.proof_code_visitor:{remote}",
            subject_model="sign.request.item",
            subject_id=0,
            capacity=VISITOR_BUDGET[0],
            window_seconds=VISITOR_BUDGET[1],
            strict=True,
        )

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
