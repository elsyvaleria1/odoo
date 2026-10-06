from odoo import Command, api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    batch_payment_id = fields.Many2one(
        comodel_name="account.batch.payment",
        index="btree_not_null",
        copy=False,
        ondelete="set null",
    )
    amount_signed = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_amount_signed",
        help="Negative value of amount field if payment_type is outbound",
    )
    payment_method_name = fields.Char(related="payment_channel_id.name")

    @api.depends("amount", "payment_type")
    def _compute_amount_signed(self) -> None:
        for payment in self:
            if payment.payment_type == "outbound":
                payment.amount_signed = -payment.amount
            else:
                payment.amount_signed = payment.amount

    @api.model
    def create_batch_payment(self) -> dict:
        valid_payment_states = self.env["account.batch.payment"]._valid_payment_states()
        if any(payment.state not in valid_payment_states for payment in self):
            create_batch_error_wizard = self.env[
                "wizard.account.payment.create.batch.partial"
            ].create({"payment_ids": [Command.set(self.ids)]})
            return {
                "name": self.env._("Create Batch"),
                "type": "ir.actions.act_window",
                "view_mode": "form",
                "target": "new",
                "res_model": "wizard.account.payment.create.batch.partial",
                "res_id": create_batch_error_wizard.id,
            }

        # We use self[0] to create the batch; the constrains on the model ensure
        # the consistency of the generated data (same journal, same payment method, ...)
        batch = self.env["account.batch.payment"].create(
            {
                "journal_id": self[0].journal_id.id,
                "payment_ids": [Command.link(payment.id) for payment in self],
                "payment_method_id": self[0].payment_method_id.id,
                "batch_type": self[0].payment_type,
            }
        )

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.batch.payment",
            "views": [[False, "form"]],
            "res_id": batch.id,
        }

    def button_open_batch_payment(self) -> dict:
        """Redirect the user to the batch payments containing this payment.
        :return:    An action on account.batch.payment.
        """
        self.check_singleton()

        return {
            "name": self.env._("Batch Payment"),
            "type": "ir.actions.act_window",
            "res_model": "account.batch.payment",
            "context": {"create": False},
            "view_mode": "form",
            "res_id": self.batch_payment_id.id,
        }

    def write(self, vals):
        old_batch_payments = {payment: payment.batch_payment_id for payment in self}
        result = super().write(vals)
        if "batch_payment_id" not in vals:
            return result
        batch_payment_id = vals.get("batch_payment_id")
        batch_payment = (
            self.env["account.batch.payment"].browse(batch_payment_id)
            if batch_payment_id
            else None
        )
        for payment in self:
            if batch_payment:
                payment.message_post(
                    body=self.env._(
                        "Payment added in batch %s",
                        batch_payment._get_html_link(title=batch_payment.name),
                    ),
                    message_type="comment",
                )
            elif old_batch_payments.get(payment):
                payment.message_post(
                    body=self.env._(
                        "Payment removed from batch %s",
                        old_batch_payments[payment]._get_html_link(
                            title=old_batch_payments[payment].name
                        ),
                    ),
                    message_type="comment",
                )
        return result
