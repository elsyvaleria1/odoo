from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    batch_payroll_move_lines = fields.Boolean()
