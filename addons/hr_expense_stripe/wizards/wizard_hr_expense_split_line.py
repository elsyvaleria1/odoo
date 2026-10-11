from odoo import models


class WizardHrExpenseSplitLine(models.TransientModel):
    _name = "wizard.hr.expense.split.line"
    _inherit = ["wizard.hr.expense.split.line"]

    def _prepare_expense_vals(self):
        values = super()._prepare_expense_vals()
        values.update(
            {
                "stripe_authorization_id": self.expense_id.stripe_authorization_id,
                "stripe_transaction_id": self.expense_id.stripe_transaction_id,
                "card_id": self.expense_id.card_id.id,
            }
        )
        return values
