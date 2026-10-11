from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    winbooks_line_id = fields.Char(help="Line ID that was used in Winbooks")

    @api.constrains("account_id", "display_type")
    def _check_payable_receivable(self) -> None:
        winbooks_lines = self.filtered("winbooks_line_id")
        super(AccountMoveLine, self - winbooks_lines)._check_payable_receivable()
