from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardPosOrderPay(models.TransientModel):
    _name = "wizard.pos.order.pay"
    _description = "Point of Sale Make Payment Wizard"

    def _get_order(self):
        active_model = self.env.context.get("active_model")
        if active_model and active_model != "pos.order":
            raise UserError(
                self.env._("Select a point of sale order to register a payment.")
            )
        order = self.env["pos.order"].browse(self.env.context.get("active_id"))
        if len(order) > 1:
            raise UserError(self.env._("Select an order to register a payment."))
        return order.exists()

    def _default_config_id(self):
        return self._get_order().config_id

    def _default_amount(self):
        order = self._get_order()
        if order:
            amount_total = order.amount_total
            if order.currency_id.is_zero(
                order.refunded_order_id.amount_total + order.amount_total
            ):
                amount_total = -order.refunded_order_id.amount_paid
            return amount_total - order.amount_paid
        return False

    def _default_payment_method_id(self):
        methods = self._get_order().session_id.payment_method_ids
        return (methods.filtered("is_cash_count") or methods)[:1]

    config_id = fields.Many2one(
        comodel_name="pos.config",
        string="Point of Sale Configuration",
        default=lambda self: self._default_config_id(),
        required=True,
    )
    amount = fields.Float(
        digits=0,
        default=lambda self: self._default_amount(),
        required=True,
    )
    payment_method_id = fields.Many2one(
        comodel_name="pos.payment.method",
        default=lambda self: self._default_payment_method_id(),
        required=True,
    )
    payment_name = fields.Char(string="Payment Reference")
    payment_date = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )

    def action_make_payment(self):
        self.check_singleton()

        order = self._get_order()
        if not order:
            raise UserError(self.env._("Select an order to register a payment."))
        if self.config_id != order.config_id:
            raise UserError(
                self.env._(
                    "The payment configuration must match the order's point of sale."
                )
            )
        if order.state == "cancel":
            raise UserError(
                self.env._("You cannot register a payment for a cancelled order.")
            )
        if self.payment_method_id.split_transactions and not order.partner_id:
            raise UserError(
                self.env._(
                    "Customer is required for %s payment method.",
                    self.payment_method_id.name,
                )
            )

        currency = order.currency_id

        payment_method = self.payment_method_id
        _debug.lifecycle(
            "make_payment",
            order=order.uuid,
            method=payment_method,
            amount=self.amount,
            state=order.state,
            paid=order.amount_paid,
            total=order.amount_total,
        )
        if not currency.is_zero(self.amount):
            order.add_payment(
                {
                    "pos_order_id": order.id,
                    "amount": order._get_rounded_amount(
                        self.amount,
                        payment_method.is_cash_count
                        or not order.config_id.only_round_cash_method,
                    ),
                    "name": self.payment_name,
                    "payment_date": self.payment_date,
                    "payment_method_id": payment_method.id,
                }
            )

        if order.state == "draft" and order._is_pos_order_paid():
            _debug.pipeline("make_payment_fully_paid", order=order.uuid)
            order._process_saved_order(False)
            if order.state in {"paid", "done"}:
                order._send_order()
                order.config_id.notify_synchronisation(
                    order.config_id.current_session_id.id, 0
                )
            return {"type": "ir.actions.act_window_close"}

        return self._prepare_action_make_payment()

    def _prepare_action_make_payment(self) -> dict:
        return {
            "name": self.env._("Payment"),
            "view_mode": "form",
            "res_model": "wizard.pos.order.pay",
            "view_id": False,
            "target": "new",
            "views": False,
            "type": "ir.actions.act_window",
            "context": self.env.context,
        }
