from odoo import fields, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    employee_id = fields.Many2one(comodel_name="hr.employee")
