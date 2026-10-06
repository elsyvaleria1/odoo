from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    # Business Methods

    def _get_project_task_resource(self):
        _debug.pipeline(
            "task_resource_from_user",
            users=self,
            # `employee_id` answers for the ACTIVE company, so a user employed
            # in two companies resolves to one resource and the scheduling
            # view reads the other one's calendar as absent
            employees=self.employee_id,
            resources=self.employee_id.resource_id,
        )
        return self.employee_id.resource_id
