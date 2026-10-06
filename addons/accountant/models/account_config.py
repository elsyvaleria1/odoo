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
        # The inverse below pins the incoming journal, but it runs after the
        # write and can no longer see the journal it replaced. Read that one
        # here, and un-pin whatever is no longer any of these companies' tax
        # return journal. Only on replacement: clearing the field leaves the
        # journal pinned, because nothing takes over the role.
        replaced = self.account_tax_return_journal_id
        res = super().write(vals)
        (replaced - self.account_tax_return_journal_id).show_on_dashboard = False
        return res

    def _inverse_account_tax_return_journal_id(self) -> None:
        self.account_tax_return_journal_id.show_on_dashboard = True
