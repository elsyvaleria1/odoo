from odoo import api, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    @api.model
    def _get_valid_payment_account_types(self):
        account_types = super()._get_valid_payment_account_types()
        if self.env.context.get("hr_payroll_payment_register"):
            account_types.append("liability_current")
        return account_types
