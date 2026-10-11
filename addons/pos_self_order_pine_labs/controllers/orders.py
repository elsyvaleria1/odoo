from decimal import Decimal, InvalidOperation

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.exceptions import UserError

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController


class PosSelfOrderPineLabsController(PosSelfOrderController):
    def _get_pine_labs_kiosk_order(self, access_token, order_id, payment_method_id):
        pos_config = self._get_pos_config(access_token)
        order = pos_config.env["pos.order"].search(
            [("id", "=", order_id), ("config_id", "=", pos_config.id)], limit=1
        )
        payment_method = pos_config.payment_method_ids.filtered(
            lambda method: (
                method.id == payment_method_id
                and method.use_payment_terminal == "pine_labs"
            )
        )
        if (
            not order
            or not payment_method
            or pos_config.self_ordering_mode != "kiosk"
            or not order.kiosk_terminal_request
        ):
            raise NotFound
        return order, payment_method

    @http.route(
        "/pos-self-order/pine-labs-fetch-payment-status/", auth="public", type="jsonrpc"
    )
    def pine_labs_fetch_payment_status(
        self, access_token, order_id, payment_data, payment_method_id
    ):
        order, payment_method = self._get_pine_labs_kiosk_order(
            access_token, order_id, payment_method_id
        )
        response = self._fetch_pine_labs_status(order, payment_method)
        response["outcome"] = self._settle_pine_labs(order, payment_method, response)
        return response

    def _fetch_pine_labs_status(self, order, payment_method) -> dict:
        return payment_method.pine_labs_fetch_payment_status(
            {"plutusTransactionReferenceID": order.kiosk_terminal_request}
        )

    def _settle_pine_labs(self, order, payment_method, response, final=False) -> str:
        if response.get("status") == "TXN APPROVED":
            return self._pay_pine_labs(order, payment_method, response)
        if final:
            order._hold_kiosk_payment_to_verify(
                payment_method, order.amount_total, order.kiosk_terminal_reference
            )
            return "unverified"
        return "pending" if response.get("responseCode") == 1001 else "unknown"

    def _pay_pine_labs(self, order, payment_method, response) -> str:
        data = response.get("data") or {}
        try:
            self._check_pine_labs_transaction(order, payment_method, response)
            with order.env.cr.savepoint():
                paid = order._add_kiosk_terminal_payment(
                    payment_method,
                    {
                        "cardholder_name": data.get("Card Holder Name"),
                        "transaction_id": data.get("TransactionLogId"),
                        "payment_status": "done",
                        "payment_method_authcode": data.get("ApprovalCode"),
                        "card_brand": data.get("Card Type"),
                        "payment_method_issuer_bank": data.get("Acquirer Name"),
                        "card_no": data.get("Card Number")
                        and data.get("Card Number")[-4:],
                        "payment_method_payment_mode": data.get("PaymentMode"),
                        "payment_ref_no": order.kiosk_terminal_reference,
                        "pine_labs_plutus_transaction_ref": order.kiosk_terminal_request,
                    },
                )
        except UserError as error:
            response["error"] = error.args[0]
            order._hold_kiosk_payment_to_verify(
                payment_method,
                order.amount_total,
                data.get("TransactionLogId") or order.kiosk_terminal_reference,
            )
            return "unverified"
        if order.kiosk_payment_to_verify_method_id:
            order._clear_kiosk_payment_to_verify()
        if paid:
            order._send_payment_result("Success")
        return "approved"

    def _check_pine_labs_transaction(self, order, payment_method, response) -> None:
        if str(response.get("plutusTransactionReferenceID")) != (
            order.kiosk_terminal_request
        ):
            raise UserError(order.env._("The terminal approved another transaction."))
        try:
            paisa = Decimal(str(response["data"]["Amount"]))
        except KeyError, TypeError, InvalidOperation:
            paisa = None
        if order.currency_id.name != "INR" or paisa != payment_method._pine_labs_paisa(
            order
        ):
            raise UserError(
                order.env._("The terminal approved another amount than the order's.")
            )

    @http.route(
        "/pos-self-order/pine-labs-cancel-transaction/", auth="public", type="jsonrpc"
    )
    def pine_labs_cancel_transaction(
        self, access_token, order_id, payment_data, payment_method_id
    ):
        order, payment_method = self._get_pine_labs_kiosk_order(
            access_token, order_id, payment_method_id
        )
        response = payment_method.pine_labs_cancel_payment_request(
            {
                "plutusTransactionReferenceID": order.kiosk_terminal_request,
                "amount": payment_method._pine_labs_paisa(order),
            }
        )
        if response.get("responseCode") == 0:
            order._send_payment_result("fail")
            response["outcome"] = "failed"
            return response
        status = self._fetch_pine_labs_status(order, payment_method)
        response["outcome"] = self._settle_pine_labs(
            order, payment_method, status, final=True
        )
        return response
