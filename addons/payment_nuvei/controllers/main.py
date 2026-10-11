import pprint

from odoo import http
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class NuveiController(http.Controller):
    _return_url = "/payment/nuvei/return"
    _webhook_url = "/payment/nuvei/webhook"

    @http.route(
        _return_url,
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_nuvei_return",
        methods=["GET"],
        typed=True,
    )
    def nuvei_return_from_checkout(
        self, tx_ref: str | None = None, error_access_token: str | None = None, **data
    ):
        _logger.info(
            "Handling redirection from Nuvei with data:\n%s", pprint.pformat(data)
        )
        if tx_ref and error_access_token:
            _logger.warning("Nuvei errored on transaction: %s.", tx_ref)
        tx_sudo = request.admission.subject
        data = request.admission.extra["data"]
        if not tx_sudo._is_notification_signature_valid(data):
            data = {}
        tx_sudo._process("nuvei", data)
        return request.redirect("/payment/status")

    @http.route(
        _webhook_url,
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_nuvei_webhook",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def nuvei_webhook(self, **data):
        _logger.info(
            "Notification received from Nuvei with data:\n%s", pprint.pformat(data)
        )
        request.admission.subject._process("nuvei", request.admission.extra["data"])
        return "OK"
