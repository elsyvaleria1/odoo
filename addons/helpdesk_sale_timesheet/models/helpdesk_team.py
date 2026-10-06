from odoo import fields, models


class HelpdeskTeam(models.Model):
    _inherit = "team.team"

    project_id = fields.Many2one(
        domain="[('allow_timesheets', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id), ('allow_billable', '=', use_helpdesk_sale_timesheet)]"
    )

    def _create_project(self, name, allow_billable, other):
        new_values = dict(other, allow_billable=allow_billable)
        return super()._create_project(name, allow_billable, new_values)

    def write(self, vals):
        result = super().write(vals)
        if vals.get("use_helpdesk_sale_timesheet"):
            projects = self.filtered(lambda team: team.project_id).mapped("project_id")
            projects.write({"allow_billable": True})
        return result
