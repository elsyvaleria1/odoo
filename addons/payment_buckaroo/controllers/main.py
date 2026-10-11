import pprint

from odoo import http
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class BuckarooController(http.Controller):
    _return_url = "/payment/buckaroo/return"
    _webhook_url = "/payment/buckaroo/webhook"

    @http.route(
        _return_url,
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_buckaroo_return",
        methods=["POST"],
        csrf=False,
        save_session=False,
        typed=True,
    )
    def buckaroo_return_from_checkout(self, **raw_data):
        _logger.info(
            "handling redirection from Buckaroo with data:\n%s",
            pprint.pformat(raw_data),
        )
        request.admission.subject._process("buckaroo", request.admission.extra["data"])
        return request.redirect("/payment/status")

    @http.route(
        _webhook_url,
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_buckaroo_webhook",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def buckaroo_webhook(self, **raw_data):
        _logger.info(
            "notification received from Buckaroo with data:\n%s",
            pprint.pformat(raw_data),
        )
        request.admission.subject._process("buckaroo", request.admission.extra["data"])
        return ""
