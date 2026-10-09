import pprint

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class RazorpayController(http.Controller):
    _return_url = "/payment/razorpay/return"
    _webhook_url = "/payment/razorpay/webhook"

    # csrf=False: auth="receiver" admits the caller through its inbound gate
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
        """Process the payment data sent by Razorpay after redirection from checkout.

        The route is configured with save_session=False to prevent Odoo from creating a new session
        when the user is redirected here via a POST request. Indeed, as the session cookie is
        created without a `SameSite` attribute, some browsers that don't implement the recommended
        default `SameSite=Lax` behavior will not include the cookie in the redirection request from
        the payment provider to Odoo. However, the redirection to the /payment/status page will
        satisfy any specification of the `SameSite` attribute, the session of the user will be
        retrieved and with it the transaction which will be immediately post-processed.

        The payment is fetched back from Razorpay: the signature covers the order and payment ids,
        not the reference of the return URL nor the amount.

        :param str reference: The transaction reference, a query parameter of the return URL.
        :param dict data: The payment data.
        """
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

    # csrf=False: auth="receiver" admits the caller through its inbound gate
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
        """Process the payment data sent by Razorpay to the webhook.

        :return: An empty string to acknowledge the notification.
        :rtype: str
        """
        _logger.info(
            "Notification received from Razorpay with data:\n%s",
            pprint.pformat(request.get_json_data()),
        )
        # The admitted subject is the refunded transaction when the refund was initiated from
        # Razorpay: the refund transaction is only created once the notification is verified.
        request.admission.subject.env["payment.transaction"]._process(
            "razorpay", request.admission.extra["data"]
        )
        return request.prepare_json_response("")
