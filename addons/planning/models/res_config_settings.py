from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    module_project_forecast = fields.Boolean(
        string="Project Planning",
        default=False,
    )
    planning_generation_interval = fields.Integer(
        related="company_id.planning_generation_interval",
        string="Rate Of Shift Generation",
        readonly=False,
        required=True,
    )

    planning_employee_unavailabilities = fields.Selection(
        related="company_id.planning_employee_unavailabilities",
        readonly=False,
    )

    planning_self_unassign_days_before = fields.Integer(
        related="company_id.planning_self_unassign_days_before",
        string="Days before shift for unassignment",
        readonly=False,
    )
