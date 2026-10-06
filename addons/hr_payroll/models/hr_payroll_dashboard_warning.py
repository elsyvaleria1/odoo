from odoo import fields, models


class HrPayrollDashboardWarning(models.Model):
    _name = "hr.payroll.dashboard.warning"
    _description = "Payroll Dashboard Warning"
    _order = "sequence, name"

    name = fields.Char(
        translate=True,
        required=True,
    )
    active = fields.Boolean(default=True)
    country_id = fields.Many2one(
        comodel_name="res.country",
        default=lambda self: self.env.company.country_id,
        domain=lambda self: [("id", "in", self.env.companies.country_id.ids)],
    )
    evaluation_code = fields.Text(
        string="Python Code",
        default="""
# Available variables:
#----------------------
#  - warning_count: Number of warnings.
#  - warning_records: Records containing warnings.
#  - warning_action: Action to perform in response to warnings.
#  - additional_context: Additional context to include with the action.""",
    )
    sequence = fields.Integer(default=10)
    color = fields.Integer(
        string="Warning Color",
        help="Tag color. No color means black.",
    )
