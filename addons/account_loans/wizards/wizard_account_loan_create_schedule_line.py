from odoo import fields, models


class WizardAccountLoanCreateScheduleLine(models.TransientModel):
    _name = "wizard.account.loan.create.schedule.line"
    _description = "Loan Schedule Preview Line"
    _order = "date, id"

    wizard_id = fields.Many2one(
        comodel_name="wizard.account.loan.create.schedule",
        index=True,
        required=True,
        ondelete="cascade",
    )
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    date = fields.Date()
    principal = fields.Monetary()
    interest = fields.Monetary()
    payment = fields.Monetary()
    balance = fields.Monetary()
