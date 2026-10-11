import pprint

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class MollieController(http.Controller):
    _return_url = "/payment/mollie/return"
    _webhook_url = "/payment/mollie/webhook"

    @http.route(
        _return_url,
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_mollie_notification",
        methods=["GET", "POST"],
        csrf=False,
        save_session=False,
        typed=True,
    )
    def mollie_return_from_checkout(self, **data):
        _logger.info(
            "handling redirection from Mollie with data:\n%s", pprint.pformat(data)
        )
        self._check_and_process(data)
        return request.redirect("/payment/status")

    @http.route(
        _webhook_url,
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_mollie_notification",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def mollie_webhook(self, **data):
        _logger.info(
            "notification received from Mollie with data:\n%s", pprint.pformat(data)
        )
        self._check_and_process(data)
        return ""

    @staticmethod
    def _check_and_process(data):
        tx_sudo = request.admission.subject
        try:
            verified_data = tx_sudo._send_api_request(
                "GET", f"/payments/{tx_sudo.provider_reference}"
            )
        except ValidationError:
            _logger.error("Unable to process the payment data")
        else:
            tx_sudo._process("mollie", verified_data)
