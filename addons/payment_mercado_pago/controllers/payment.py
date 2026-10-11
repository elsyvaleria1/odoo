import pprint
import re

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_mercado_pago import const

_logger = get_payment_logger(__name__)


class MercadoPagoPaymentController(http.Controller):
    _PAYMENT_ID = re.compile(r"[0-9]+")

    @http.route("/payment/mercado_pago/payments", type="jsonrpc", auth="public")
    def mercado_pago_payment(
        self,
        reference,
        token,
        installments,
        payment_method_brand,
        issuer_id,
        transaction_amount=None,
    ):
        tx_sudo = (
            request.env["payment.transaction"]
            .sudo()
            ._search_by_reference("mercado_pago", {"external_reference": reference})
        )
        payload = tx_sudo._mercado_pago_prepare_payment_request_payload()
        payload.update(
            {
                "transaction_amount": tx_sudo._mercado_pago_convert_amount(),
                "token": token,
                "installments": installments,
                "payment_method_id": payment_method_brand,
                "issuer_id": issuer_id,
            }
        )
        response_content = tx_sudo._send_api_request(
            "POST",
            endpoint="/v1/payments",
            json=payload,
            idempotency_key=payment_utils.generate_idempotency_key(
                tx_sudo, scope="direct_payment"
            ),
        )
        tx_sudo._process(
            "mercado_pago",
            dict(response_content, merchantReference=reference, token=token),
        )

    @http.route(
        const.PAYMENT_RETURN_ROUTE,
        type="http",
        methods=["GET"],
        auth="receiver",
        receiver="payment.transaction:_receiver_for_mercado_pago_return",
        typed=True,
    )
    def mercado_pago_return_from_checkout(self, **data):
        _logger.info(
            "Handling redirection from Mercado Pago with data:\n%s",
            pprint.pformat(data),
        )
        self._check_and_process()
        return request.redirect("/payment/status")

    @http.route(
        f"{const.WEBHOOK_ROUTE}/<reference>",
        type="http",
        auth="receiver",
        receiver="payment.transaction:_receiver_for_mercado_pago_webhook",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def mercado_pago_webhook(self, reference: str, **_kwargs):
        _logger.info(
            "Notification received from Mercado Pago with data:\n%s",
            pprint.pformat(request.get_json_data()),
        )
        self._check_and_process()
        return ""

    @staticmethod
    def _check_and_process():
        admission = request.admission
        tx_sudo = admission.subject
        payment_id = admission.extra["data"].get("payment_id")
        if (
            isinstance(payment_id, bool)
            or not isinstance(payment_id, str | int)
            or not MercadoPagoPaymentController._PAYMENT_ID.fullmatch(str(payment_id))
        ):
            admission.refuse(400, "payment_id missing or malformed", "bad_request")
        try:
            verified_data = tx_sudo._send_api_request(
                "GET", f"/v1/payments/{payment_id}"
            )
        except ValidationError:
            _logger.error("Unable to verify the payment data")
            return
        if verified_data.get("external_reference") != tx_sudo.reference:
            _logger.warning(
                "Payment %s does not belong to transaction %s.",
                payment_id,
                tx_sudo.reference,
            )
            admission.refuse(
                403, "the payment belongs to another transaction", "forbidden"
            )
        tx_sudo._process("mercado_pago", verified_data)
