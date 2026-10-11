import pprint

from odoo import http
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class APSController(http.Controller):
    _return_url = "/payment/aps/return"
    _webhook_url = "/payment/aps/webhook"

    @http.route(
        _return_url,
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_aps_return",
        methods=["POST"],
        csrf=False,
        save_session=False,
        typed=True,
    )
    def aps_return_from_checkout(self, **data):
        _logger.info(
            "Handling redirection from APS with data:\n%s", pprint.pformat(data)
        )

        request.admission.subject._process("aps", request.admission.extra["data"])
        return request.redirect("/payment/status")

    @http.route(
        _webhook_url,
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_aps_webhook",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def aps_webhook(self, **data):
        _logger.info(
            "Notification received from APS with data:\n%s", pprint.pformat(data)
        )
        request.admission.subject._process("aps", request.admission.extra["data"])
        return ""
