import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PosMollie(http.Controller):
    _PAYMENT_ID = re.compile(r"tr_[A-Za-z0-9]+")

    # csrf=False: auth="receiver" admits the caller through its inbound gate
    @http.route(
        "/pos_mollie/webhook",
        methods=["POST"],
        auth="receiver",
        receiver="pos.payment.method:_receiver_for_mollie_terminal",
        receiver_event="mollie_terminal",
        type="http",
        save_session=False,
        csrf=False,
        typed=True,
    )
    def mollie_webhook(self, id: str, payload: str):
        _logger.info("Received webhook from Mollie for payment '%s'", id)
        admission = request.admission
        payment_method_sudo = admission.subject
        signed_payload = admission.extra["payload"]
        pos_session_id = signed_payload["pos_session_id"]
        if not self._PAYMENT_ID.fullmatch(id):
            admission.refuse(400, "id is not a Mollie payment id", "bad_request")
        pos_session_sudo = (
            request.env["pos.session"].sudo().browse(pos_session_id).exists()
        )
        if not pos_session_sudo:
            _logger.warning("No POS session found matching Mollie webhook, ignoring")
            return "OK"

        payment_info = payment_method_sudo._mollie_get_payment(id)
        signed_description = payment_method_sudo._get_mollie_payment_description(
            pos_session_id, signed_payload["payment_uuid"]
        )
        if payment_info.get("description") != signed_description:
            _logger.warning(
                "Mollie payment '%s' is not the one the webhook URL was signed for",
                id,
            )
            admission.refuse(
                403, "the payment is not the one the payload names", "forbidden"
            )

        message = {
            "session_id": int(pos_session_id),
            **payment_method_sudo._mollie_payment_status(id, payment_info),
        }
        pos_session_sudo.config_id._notify("MOLLIE_PAYMENT_STATUS", message)

        return "OK"
