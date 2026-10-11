import pprint

from odoo import http
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class AsiaPayController(http.Controller):
    _return_url = "/payment/asiapay/return"
    _webhook_url = "/payment/asiapay/webhook"

    @http.route(_return_url, type="http", auth="public", methods=["GET"])
    def asiapay_return_from_checkout(self, **data):
        return request.redirect("/payment/status")

    @http.route(
        _webhook_url,
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_asiapay_webhook",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def asiapay_webhook(self, **data):
        _logger.info(
            "Notification received from AsiaPay with data:\n%s", pprint.pformat(data)
        )
        request.admission.subject._process("asiapay", request.admission.extra["data"])
        return "OK"
