from odoo import models


class ProjectProject(models.Model):
    _name = "project.project"
    _inherit = "project.project"

    def action_project_forecast_from_project(self):
        action = super().action_project_forecast_from_project()
        pivot_view = self.env.ref(
            "project_timesheet_forecast.planning_view_pivot_view_inherit_timesheet"
        ).id
        action["views"] = [
            (view_id, view_type)
            if view_type != "pivot"
            else (pivot_view or view_id, view_type)
            for view_id, view_type in action["views"]
        ]
        return action
