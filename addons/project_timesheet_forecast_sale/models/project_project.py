from odoo import api, fields, models
from odoo.libs.json import dumps as json_dumps


class ProjectProject(models.Model):
    _name = "project.project"
    _inherit = "project.project"

    display_planning_timesheet_analysis = fields.Boolean(
        export_string_translation=False,
        compute="_compute_display_planning_timesheet_analysis",
    )

    @api.depends("allow_timesheets")
    @api.depends_context("uid")
    def _compute_display_planning_timesheet_analysis(self) -> None:
        is_user_authorized = self.env.user.has_group(
            "planning.group_planning_manager"
        ) and self.env.user.has_group("hr_timesheet.group_hr_timesheet_approver")
        if not is_user_authorized:
            self.display_planning_timesheet_analysis = False
        else:
            for project in self:
                project.display_planning_timesheet_analysis = project.allow_timesheets

    def open_timesheets_planning_report(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "project_timesheet_forecast.project_timesheet_forecast_report_action"
        )
        action.update(
            {
                "display_name": self.env._(
                    "%(name)s's Timesheets and Planning Analysis", name=self.name
                ),
                "domain": [("project_id", "=", self.id)],
                "context": {
                    "pivot_row_groupby": ["entry_date:month"],
                },
            }
        )
        return action

    def _get_stat_buttons(self):
        buttons = super()._get_stat_buttons()
        buttons.append(
            {
                "icon": "clock-o",
                "text": self.env._("Timesheets and Planning"),
                "action_type": "object",
                "action": "open_timesheets_planning_report",
                "additional_context": json_dumps(
                    {
                        "active_id": self.id,
                    }
                ),
                "show": self.display_planning_timesheet_analysis,
                "sequence": 63,
            }
        )
        return buttons
