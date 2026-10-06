from odoo import api, models
from odoo.exceptions import UserError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    @api.ondelete(at_uninstall=False)
    def _prevent_unlink_payroll_journal(self) -> None:
        payroll_journals = (
            self.env["hr.payroll.structure"]
            .sudo()
            .search([("journal_id", "in", self.ids)])
            .journal_id
        )
        if self & payroll_journals:
            raise UserError(
                self.env._("You cannot delete the journal linked to a Salary Structure")
            )
