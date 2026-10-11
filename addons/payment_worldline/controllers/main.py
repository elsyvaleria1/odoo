import pprint
import re

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)

HOSTED_CHECKOUT_ID = re.compile(r"[0-9A-Za-z_-]{1,64}")


class WorldlineController(http.Controller):
    _return_url = "/payment/worldline/return"
    _webhook_url = "/payment/worldline/webhook"

    @http.route(_return_url, type="http", auth="public", methods=["GET"])
    def worldline_return_from_checkout(self, **data):
        _logger.info(
            "Handling redirection from Worldline with data:\n%s", pprint.pformat(data)
        )

        try:
            provider_id = int(data.get("provider_id", ""))
        except ValueError:
            provider_id = 0
        provider_sudo = (
            request.env["payment.provider"].sudo().browse(provider_id).exists()
        )
        if not provider_sudo or provider_sudo.code != "worldline":
            _logger.warning("Received payment data with invalid provider id.")
            raise Forbidden
        hosted_checkout_id = data.get("hostedCheckoutId", "")
        if not HOSTED_CHECKOUT_ID.fullmatch(hosted_checkout_id):
            _logger.warning(
                "Received payment data with no or malformed hosted checkout id."
            )
            raise Forbidden

        try:
            checkout_session_data = provider_sudo._send_api_request(
                "GET", f"hostedcheckouts/{hosted_checkout_id}"
            )
        except ValidationError:
            _logger.error("Unable to process the payment data")
        else:
            payment_data = checkout_session_data.get("createdPaymentOutput", {})
            request.env["payment.transaction"].sudo()._process(
                "worldline", payment_data
            )
        return request.redirect("/payment/status")

    @http.route(
        _webhook_url,
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_worldline_webhook",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def worldline_webhook(self):
        _logger.info(
            "Notification received from Worldline with data:\n%s",
            pprint.pformat(request.get_json_data()),
        )
        request.admission.subject._process("worldline", request.admission.extra["data"])
        return request.prepare_json_response("")
