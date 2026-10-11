import pprint

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.libs.json import loads as json_loads

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class FlutterwaveController(http.Controller):
    _return_url = "/payment/flutterwave/return"
    _auth_return_url = "/payment/flutterwave/auth_return"
    _webhook_url = "/payment/flutterwave/webhook"

    @http.route(_return_url, type="http", methods=["GET"], auth="public")
    def flutterwave_return_from_checkout(self, **data):
        _logger.info(
            "Handling redirection from Flutterwave with data:\n%s", pprint.pformat(data)
        )

        if data.get("status") != "cancelled":
            self._check_and_process(data)
        else:
            pass

        return request.redirect("/payment/status")

    @http.route(_auth_return_url, type="http", methods=["GET"], auth="public")
    def flutterwave_return_from_authorization(self, response=None):
        try:
            data = json_loads(response) if response else {}
        except ValueError:
            data = None
        if not isinstance(data, dict):
            _logger.warning(
                "Received an authorization response that is no JSON object."
            )
            data = {}
        return self.flutterwave_return_from_checkout(**data)

    @http.route(
        _webhook_url,
        type="http",
        methods=["POST"],
        auth="receiver",
        receiver="payment.transaction:_receiver_for_flutterwave_webhook",
        csrf=False,
        typed=True,
    )
    def flutterwave_webhook(self):
        _logger.info(
            "Notification received from Flutterwave with data:\n%s",
            pprint.pformat(request.get_json_data()),
        )
        request.admission.subject._process(
            "flutterwave", request.admission.extra["data"]
        )
        return request.prepare_json_response("")

    @staticmethod
    def _check_and_process(data):
        tx_sudo = (
            request.env["payment.transaction"]
            .sudo()
            ._search_by_reference("flutterwave", data)
        )
        if not tx_sudo:
            return

        try:
            verified_data = tx_sudo._send_api_request(
                "GET",
                "transactions/verify_by_reference",
                params={"tx_ref": tx_sudo.reference},
            )
        except ValidationError:
            _logger.error("Unable to verify the payment data")
        else:
            tx_sudo._process("flutterwave", verified_data)
