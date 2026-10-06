from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountPaymentChannel(models.Model):
    _inherit = "account.payment.channel"

    card_id = fields.One2many(
        comodel_name="hr.expense.stripe.card",
        inverse_name="payment_channel_id",
        string="Expense Card",
    )
    employee_id = fields.Many2one(
        related="card_id.employee_id",
        readonly=True,
    )

    @api.ondelete(at_uninstall=False)
    def _cannot_unlink_if_card_active(self) -> None:
        for payment_channel in self:
            if payment_channel.card_id.state in {"active", "inactive"}:
                raise ValidationError(
                    self.env._(
                        "You cannot delete a payment method line that is used by an active/paused card."
                    )
                )
