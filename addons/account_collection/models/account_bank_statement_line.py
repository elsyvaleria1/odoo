from odoo import api, models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if lines.filtered(lambda line: line.amount > 0):
            self.env.ref(
                "account_collection.ir_cron_match_remittance_bank_transactions"
            )._trigger()
        return lines
