from werkzeug.exceptions import Unauthorized

from odoo import http
from odoo.exceptions import UserError

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController

RAZORPAY_FAILED = frozenset({"VOIDED", "AUTHORIZED_REFUNDED"})
RAZORPAY_PENDING = frozenset({"RECEIVED", "SENT", "QUEUED"})


class PosSelfOrderControllerRazorpay(PosSelfOrderController):
    def _get_razorpay_kiosk_order(self, access_token, order_id, payment_method_id):
        pos_config = self._get_pos_config(access_token)
        order = pos_config.env["pos.order"].search(
            [("id", "=", order_id), ("config_id", "=", pos_config.id)], limit=1
        )
        payment_method = pos_config.payment_method_ids.filtered(
            lambda method: (
                method.id == payment_method_id
                and method.use_payment_terminal == "razorpay"
            )
        )
        if (
            not order
            or not payment_method
            or pos_config.self_ordering_mode != "kiosk"
            or not order.kiosk_terminal_request
        ):
            raise Unauthorized
        return order, payment_method

    @http.route(
        "/pos-self-order/razorpay-fetch-payment-status/",
        auth="public",
        type="jsonrpc",
        website=True,
    )
    def razorpay_payment_status(  # noqa: E8539 -- device: a device's or a kiosk's credential, presented by a program
        self, access_token, order_id, payment_data, payment_method_id
    ):
        order, payment_method = self._get_razorpay_kiosk_order(
            access_token, order_id, payment_method_id
        )
        response = self._fetch_razorpay_status(order, payment_method)
        response["outcome"] = self._settle_razorpay(order, payment_method, response)
        return response

    @http.route(
        "/pos-self-order/razorpay-cancel-transaction/",
        auth="public",
        type="jsonrpc",
        website=True,
    )
    def razorpay_cancel_status(  # noqa: E8539 -- device: a device's or a kiosk's credential, presented by a program
        self, access_token, order_id, payment_data, payment_method_id
    ):
        order, payment_method = self._get_razorpay_kiosk_order(
            access_token, order_id, payment_method_id
        )
        response = payment_method.razorpay_cancel_payment_request(
            {"p2pRequestId": order.kiosk_terminal_request}
        )
        if "error" in response:
            order._send_payment_result("fail")
            response["outcome"] = "failed"
            return response
        status = self._fetch_razorpay_status(order, payment_method)
        response["outcome"] = self._settle_razorpay(
            order, payment_method, status, final=True
        )
        return response

    def _fetch_razorpay_status(self, order, payment_method) -> dict:
        return payment_method.razorpay_fetch_payment_status(
            {"p2pRequestId": order.kiosk_terminal_request}
        )

    def _settle_razorpay(self, order, payment_method, response, final=False) -> str:
        status = response.get("status")
        if status == "AUTHORIZED":
            return self._pay_razorpay(order, payment_method, response)
        if response.get("payment_messageCode") or status in RAZORPAY_FAILED:
            order._send_payment_result("fail")
            return "failed"
        if final:
            order._hold_kiosk_payment_to_verify(
                payment_method, order.amount_total, order.kiosk_terminal_reference
            )
            return "unverified"
        return "pending" if status in RAZORPAY_PENDING else "unknown"

    def _pay_razorpay(self, order, payment_method, response) -> str:
        try:
            self._check_razorpay_transaction(order, response)
            with order.env.cr.savepoint():
                paid = order._add_kiosk_terminal_payment(
                    payment_method,
                    {
                        "card_type": response.get("paymentCardType"),
                        "cardholder_name": response.get("nameOnCard"),
                        "transaction_id": response.get("txnId"),
                        "payment_status": response.get("status"),
                        "payment_method_authcode": response.get("authCode"),
                        "card_brand": response.get("paymentCardBrand"),
                        "payment_method_issuer_bank": response.get("acquirerCode"),
                        "card_no": response.get("cardLastFourDigit"),
                        "payment_method_payment_mode": response.get("paymentMode"),
                        "payment_ref_no": order.kiosk_terminal_reference,
                        "razorpay_reverse_ref_no": response.get(
                            "reverseReferenceNumber"
                        ),
                    },
                )
        except UserError as error:
            response["error"] = error.args[0]
            order._hold_kiosk_payment_to_verify(
                payment_method,
                order.amount_total,
                response.get("txnId") or order.kiosk_terminal_reference,
            )
            return "unverified"
        if order.kiosk_payment_to_verify_method_id:
            order._clear_kiosk_payment_to_verify()
        if paid:
            order._send_payment_result("Success")
        return "approved"

    def _check_razorpay_transaction(self, order, response) -> None:
        if (
            response.get("externalRefNumber") != order.kiosk_terminal_reference
            or str(response.get("p2pRequestId")) != order.kiosk_terminal_request
        ):
            raise UserError(order.env._("The terminal approved another transaction."))
        try:
            amount = float(response.get("amount"))
        except TypeError, ValueError:
            amount = None
        if (
            order.currency_id.name != "INR"
            or amount is None
            or order.currency_id.compare_amounts(amount, order.amount_total)
        ):
            raise UserError(
                order.env._("The terminal approved another amount than the order's.")
            )
