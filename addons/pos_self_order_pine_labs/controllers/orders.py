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
    def pine_labs_fetch_payment_status(  # noqa: E8539  device: a device's or a kiosk's credential, presented by a program
        self, access_token, order_id, payment_data, payment_method_id
    ):
        order, payment_method = self._get_pine_labs_kiosk_order(
            access_token, order_id, payment_method_id
        )
        pine_labs_status_response = payment_method.pine_labs_fetch_payment_status(
            {"plutusTransactionReferenceID": order.kiosk_terminal_request}
        )
        if pine_labs_status_response.get("status") == "TXN APPROVED":
            data = pine_labs_status_response.get("data") or {}
            try:
                self._check_pine_labs_transaction(
                    order, payment_method, pine_labs_status_response
                )
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
                return {"error": error.args[0]}
            if paid:
                order._send_payment_result("Success")
        return pine_labs_status_response

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
    def pine_labs_cancel_transaction(  # noqa: E8539  device: a device's or a kiosk's credential, presented by a program
        self, access_token, order_id, payment_data, payment_method_id
    ):
        order, payment_method = self._get_pine_labs_kiosk_order(
            access_token, order_id, payment_method_id
        )
        return payment_method.pine_labs_cancel_payment_request(
            {
                "plutusTransactionReferenceID": order.kiosk_terminal_request,
                "amount": payment_method._pine_labs_paisa(order),
            }
        )
