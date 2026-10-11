from odoo import fields, models


class AccountConfig(models.Model):
    _inherit = "account.config"

    account_tax_return_journal_id = fields.Many2one(
        comodel_name="account.journal",
        inverse="_inverse_account_tax_return_journal_id",
    )

    def write(self, vals):
        if not vals.get("account_tax_return_journal_id"):
            return super().write(vals)
        replaced = self.account_tax_return_journal_id
        res = super().write(vals)
        (replaced - self.account_tax_return_journal_id).show_on_dashboard = False
        return res

    def _inverse_account_tax_return_journal_id(self) -> None:
        self.account_tax_return_journal_id.show_on_dashboard = True
