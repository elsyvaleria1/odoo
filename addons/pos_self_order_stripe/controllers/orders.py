from werkzeug.exceptions import Unauthorized

from odoo import fields, http
from odoo.exceptions import UserError

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController


class PosSelfOrderControllerStripe(PosSelfOrderController):
    @http.route(
        "/pos-self-order/stripe-connection-token/",
        auth="public",
        type="jsonrpc",
        website=True,
    )
    def get_stripe_creditentials(self, access_token, payment_method_id):  # noqa: E8539 -- device: a device's or a kiosk's credential, presented by a program
        pos_config, _ = self._get_pos_config_and_table(access_token, "", {})
        payment_method = pos_config.payment_method_ids.filtered(
            lambda p: p.id == payment_method_id
        )
        return payment_method.stripe_connection_token()

    @http.route(
        "/pos-self-order/stripe-capture-payment/",
        auth="public",
        type="jsonrpc",
        website=True,
    )
    def stripe_capture_payment(  # noqa: E8539 -- device: a device's or a kiosk's credential, presented by a program
        self, access_token, order_access_token, payment_intent_id, payment_method_id
    ):
        pos_config, _ = self._get_pos_config_and_table(access_token, "", {})
        order = pos_config.env["pos.order"].search(  # noqa: E8537 -- device: a device's or a service's credential, presented by a program
            [
                ("access_token", "=", order_access_token),
                ("config_id", "=", pos_config.id),
            ]
        )
        payment_method = pos_config.payment_method_ids.filtered(
            lambda p: p.id == payment_method_id and p.use_payment_terminal == "stripe"
        )
        if (
            not order
            or not payment_method
            or pos_config.self_ordering_mode != "kiosk"
            or not payment_intent_id
            or payment_intent_id != order.kiosk_terminal_request
        ):
            raise Unauthorized

        stripe_confirmation = payment_method.stripe_capture_payment(payment_intent_id)
        currency = (
            payment_method.journal_id.currency_id
            or payment_method.company_id.currency_id
        )
        if not (
            stripe_confirmation.get("status") == "succeeded"
            and stripe_confirmation.get("id") == payment_intent_id
            and stripe_confirmation.get("amount")
            == payment_method._stripe_get_amount(order.amount_total)
            and str(stripe_confirmation.get("currency") or "").upper() == currency.name
        ):
            order._send_payment_result("fail")
            return
        try:
            with order.env.cr.savepoint():
                paid = order._add_kiosk_terminal_payment(
                    payment_method,
                    {
                        "payment_date": fields.Datetime.now(),
                        "card_type": False,
                        "cardholder_name": "",
                        "transaction_id": payment_intent_id,
                        "payment_status": stripe_confirmation["status"],
                        "ticket": "",
                    },
                )
        except UserError:
            order._send_payment_result("fail")
            return
        if paid:
            order._send_payment_result("Success")
