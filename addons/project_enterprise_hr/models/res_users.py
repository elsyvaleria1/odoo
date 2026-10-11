from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"


    def _get_project_task_resource(self):
        _debug.pipeline(
            "task_resource_from_user",
            users=self,
            employees=self.employee_id,
            resources=self.employee_id.resource_id,
        )
        return self.employee_id.resource_id
