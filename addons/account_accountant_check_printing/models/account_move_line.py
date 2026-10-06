from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    check_number = fields.Char(
        related="payment_id.check_number",
        string="Check Number",
    )
