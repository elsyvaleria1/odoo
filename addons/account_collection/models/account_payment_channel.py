from odoo import api, models
from odoo.exceptions import ValidationError


class AccountPaymentChannel(models.Model):
    _inherit = "account.payment.channel"

    @api.constrains("payment_account_id")
    def _check_collection_custody_account(self) -> None:
        for journal in self.journal_id.filtered("is_collection_custody"):
            if problem := journal._get_collection_custody_problem():
                raise ValidationError(problem)
