from odoo import fields, models


class SaleCommissionPlan(models.Model):
    _inherit = "sale.commission.plan"

    commission_payroll_input = fields.Many2one(
        comodel_name="hr.payslip.input.type",
        string="Payslip input",
        help="Payslip input type for this commission plan, "
        "commission are grouped by input type.",
    )
