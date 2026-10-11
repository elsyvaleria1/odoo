from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    pos_order_id = fields.Many2one(
        comodel_name="pos.order",
        string="POS Order",
        readonly=True,
        help="The Point of Sale order linked to the payment transaction",
    )

    @api.model
    def _get_reference_prefix(self, separator, **values):
        pos_order_id = values.get("pos_order_id")
        if pos_order_id:
            pos_order = self.env["pos.order"].sudo().browse(pos_order_id).exists()
            if pos_order:
                return pos_order.pos_reference
        return super()._get_reference_prefix(separator, **values)

    def _post_process(self):
        super()._post_process()
        self._process_pos_online_payment()

    def _process_pos_online_payment(self) -> None:
        pending = self.filtered(
            lambda tx: (
                tx.pos_order_id
                and tx.state in ("authorized", "done")
                and not tx.payment_id.pos_order_id
            )
        )
        pending.pos_order_id.lock_for_update(allow_referencing=True, wait=True)
        for tx in pending:
            pos_order = tx.pos_order_id
            if pos_order.currency_id.compare_amounts(tx.amount, 0.0) <= 0:
                raise ValidationError(
                    self.env._(
                        "The payment transaction (%d) has a negative amount.", tx.id
                    )
                )

            if not tx.payment_id:
                tx._create_payment()
            if not tx.payment_id:
                raise ValidationError(
                    self.env._(
                        "The POS online payment (tx.id=%d) could not be saved correctly",
                        tx.id,
                    )
                )

            payment_method = pos_order.online_payment_method_id
            if not payment_method:
                pos_config = pos_order.config_id
                payment_method = (
                    self.env["pos.payment.method"]
                    .sudo()
                    ._get_or_create_online_payment_method(
                        pos_config.company_id.id, pos_config.id
                    )
                )
                if not payment_method:
                    raise ValidationError(
                        self.env._(
                            "The POS online payment (tx.id=%d) could not be saved correctly because the online payment method could not be found",
                            tx.id,
                        )
                    )

            pos_order.add_payment(
                {
                    "amount": tx.amount,
                    "payment_date": tx.last_state_change,
                    "payment_method_id": payment_method.id,
                    "online_account_payment_id": tx.payment_id.id,
                    "pos_order_id": pos_order.id,
                }
            )
            tx.payment_id.update(
                {
                    "pos_payment_method_id": payment_method.id,
                    "pos_order_id": pos_order.id,
                    "pos_session_id": pos_order.session_id.id,
                }
            )
            if pos_order.state == "draft" and pos_order._is_payment_amount_valid():
                pos_order._process_saved_order(False)
            pos_order.config_id._notify(
                "ONLINE_PAYMENTS_NOTIFICATION", {"id": pos_order.id}
            )

    def action_view_pos_order(self):
        self.check_singleton()

        return {
            "name": self.env._("POS Order"),
            "type": "ir.actions.act_window",
            "res_model": "pos.order",
            "target": "current",
            "res_id": self.pos_order_id.id,
            "view_mode": "form",
        }
