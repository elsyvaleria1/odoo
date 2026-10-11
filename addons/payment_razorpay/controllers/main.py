import pprint

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class RazorpayController(http.Controller):
    _return_url = "/payment/razorpay/return"
    _webhook_url = "/payment/razorpay/webhook"

    @http.route(
        _return_url,
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_razorpay_return",
        methods=["POST"],
        csrf=False,
        save_session=False,
        typed=True,
    )
    def razorpay_return_from_checkout(self, reference: str, **data):
        _logger.info(
            "Handling redirection from Razorpay with data:\n%s", pprint.pformat(data)
        )
        admission = request.admission
        tx_sudo = admission.subject
        return_data = admission.extra["data"]
        try:
            payment = tx_sudo._send_api_request(
                "GET", f"payments/{return_data['razorpay_payment_id']}"
            )
        except ValidationError as error:
            tx_sudo._set_error(str(error))
        else:
            if (
                payment.get("order_id") != return_data["razorpay_order_id"]
                or payment.get("description") != tx_sudo.reference
                or not tx_sudo._is_razorpay_payment_of_own_order(payment)
            ):
                _logger.warning(
                    "Payment %s does not belong to transaction %s.",
                    return_data["razorpay_payment_id"],
                    tx_sudo.reference,
                )
                admission.refuse(
                    403, "the payment belongs to another transaction", "forbidden"
                )
            tx_sudo._process("razorpay", payment)
        return request.redirect("/payment/status")

    @http.route(
        _webhook_url,
        type="http",
        methods=["POST"],
        auth="receiver",
        receiver="payment.transaction:_receiver_for_razorpay_webhook",
        csrf=False,
        typed=True,
    )
    def razorpay_webhook(self):
        _logger.info(
            "Notification received from Razorpay with data:\n%s",
            pprint.pformat(request.get_json_data()),
        )
        request.admission.subject.env["payment.transaction"]._process(
            "razorpay", request.admission.extra["data"]
        )
        return request.prepare_json_response("")
