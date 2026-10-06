from odoo import fields, models


class WizardAccountPaymentBounce(models.TransientModel):
    _name = "wizard.account.payment.bounce"
    _description = "Record a Bounced Check"

    payment_id = fields.Many2one(
        comodel_name="account.payment",
        string="Collection",
        readonly=True,
        required=True,
    )
    company_id = fields.Many2one(
        related="payment_id.company_id",
    )
    currency_id = fields.Many2one(
        related="payment_id.company_currency_id",
    )
    amount = fields.Monetary(
        related="payment_id.amount_company_currency_signed",
        string="Check Amount",
        currency_field="currency_id",
    )
    date = fields.Date(
        string="Bounced On",
        default=fields.Date.context_today,
        required=True,
    )
    reason = fields.Char(
        required=True,
        help="Why the bank returned the check, as it reports it.",
    )
    fee = fields.Monetary(
        string="Bank Fee Charged to the Customer",
        currency_field="currency_id",
    )

    def action_bounce(self) -> None:
        self.check_singleton()
        self.payment_id._bounce_collection_check(self.date, self.fee, self.reason)
