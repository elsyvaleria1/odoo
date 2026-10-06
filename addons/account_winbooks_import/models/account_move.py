from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # technical field used to reconcile the journal items in Odoo as they were in Winbooks
    winbooks_line_id = fields.Char(help="Line ID that was used in Winbooks")

    @api.constrains("account_id", "display_type")
    def _check_payable_receivable(self) -> None:
        # Winbooks imported lines might not respect Odoo constrains on account
        # type usage
        winbooks_lines = self.filtered("winbooks_line_id")
        super(AccountMoveLine, self - winbooks_lines)._check_payable_receivable()
