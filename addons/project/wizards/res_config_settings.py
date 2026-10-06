from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    module_hr_timesheet = fields.Boolean(string="Task Logs")
    group_project_stages = fields.Boolean(
        string="Project Stages",
        implied_group="project.group_project_stages",
    )

    def set_values(self) -> None:
        project_stage_change_mail_type = self.env.ref("project.mt_project_stage_change")
        if project_stage_change_mail_type.hidden == self["group_project_stages"]:
            _debug.lifecycle(
                "stage_change_subtype_toggled",
                project_stages=self["group_project_stages"],
                hidden=not self["group_project_stages"],
            )
            project_stage_change_mail_type.hidden = not self["group_project_stages"]
        super().set_values()
