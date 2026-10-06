from odoo import api, models
from odoo.exceptions import UserError


class ResPartnerBankAccount(models.Model):
    _inherit = "res.partner.bank.account"

    @api.ondelete(at_uninstall=False)
    def _unlink_except_linked_to_mandate(self) -> None:
        if self.env["sdd.mandate"].search_count(
            [("bank_account_id", "in", self.ids), ("state", "=", "active")], limit=1
        ):
            raise UserError(
                self.env._(
                    "You cannot delete a bank account linked to an active SEPA Direct Debit mandate."
                )
            )
