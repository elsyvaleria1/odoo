from werkzeug.exceptions import Unauthorized

from odoo import http
from odoo.exceptions import UserError

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController


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
    def razorpay_payment_status(  # noqa: E8539  device: a device's or a kiosk's credential, presented by a program
        self, access_token, order_id, payment_data, payment_method_id
    ):
        order, payment_method = self._get_razorpay_kiosk_order(
            access_token, order_id, payment_method_id
        )
        razorpay_status_response = payment_method.razorpay_fetch_payment_status(
            {"p2pRequestId": order.kiosk_terminal_request}
        )
        payment_status = razorpay_status_response.get("status")
        if payment_status == "AUTHORIZED":
            try:
                self._check_razorpay_transaction(order, razorpay_status_response)
                with order.env.cr.savepoint():
                    paid = order._add_kiosk_terminal_payment(
                        payment_method,
                        {
                            "card_type": razorpay_status_response.get(
                                "paymentCardType"
                            ),
                            "cardholder_name": razorpay_status_response.get(
                                "nameOnCard"
                            ),
                            "transaction_id": razorpay_status_response.get("txnId"),
                            "payment_status": payment_status,
                            "payment_method_authcode": razorpay_status_response.get(
                                "authCode"
                            ),
                            "card_brand": razorpay_status_response.get(
                                "paymentCardBrand"
                            ),
                            "payment_method_issuer_bank": razorpay_status_response.get(
                                "acquirerCode"
                            ),
                            "card_no": razorpay_status_response.get(
                                "cardLastFourDigit"
                            ),
                            "payment_method_payment_mode": razorpay_status_response.get(
                                "paymentMode"
                            ),
                            "payment_ref_no": order.kiosk_terminal_reference,
                            "razorpay_reverse_ref_no": razorpay_status_response.get(
                                "reverseReferenceNumber"
                            ),
                        },
                    )
            except UserError as error:
                return {"error": error.args[0]}
            if paid:
                self.call_bus_service(order, payment_result="Success")
        elif payment_status == "FAILED" or not payment_status:
            self.call_bus_service(order, payment_result="fail")
        return razorpay_status_response

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

    @http.route(
        "/pos-self-order/razorpay-cancel-transaction/",
        auth="public",
        type="jsonrpc",
        website=True,
    )
    def razorpay_cancel_status(  # noqa: E8539  device: a device's or a kiosk's credential, presented by a program
        self, access_token, order_id, payment_data, payment_method_id
    ):
        order, payment_method = self._get_razorpay_kiosk_order(
            access_token, order_id, payment_method_id
        )
        razorpay_cancel_response = payment_method.razorpay_cancel_payment_request(
            {"p2pRequestId": order.kiosk_terminal_request}
        )
        cancel_status = razorpay_cancel_response.get("status")
        if cancel_status:
            self.call_bus_service(order, payment_result="fail")
        return razorpay_cancel_response

    def call_bus_service(self, order, payment_result):
        order._send_payment_result(payment_result)
