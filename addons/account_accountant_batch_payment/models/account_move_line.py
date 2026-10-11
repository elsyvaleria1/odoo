from odoo import fields, models


class AccountMoveLine(models.Model):
    _name = "account.move.line"
    _inherit = "account.move.line"

    payment_lines_ids = fields.Many2many(comodel_name="account.payment")
