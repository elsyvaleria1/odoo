from odoo import fields, models


class HrPayrollHeadcountLine(models.Model):
    _inherit = "hr.payroll.headcount.line"

    employer_cost = fields.Monetary(
        related="version_id.monthly_yearly_costs",
        string="Employer Cost",
    )
