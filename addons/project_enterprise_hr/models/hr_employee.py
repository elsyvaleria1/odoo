from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees._book_tasks_of_users(employees.user_id)
        return employees

    def write(self, vals):
        users = self.user_id if "user_id" in vals else self.env["res.users"]
        result = super().write(vals)
        if "user_id" in vals:
            self._book_tasks_of_users(users | self.user_id)
        return result

    def _book_tasks_of_users(self, users) -> None:
        if not users:
            return
        tasks = (
            self.env["project.task"]
            .with_privilege(
                "project_enterprise_hr.privilege_book_employee_tasks",
                reason="a user's dated tasks are booked on the employee they are given",
            )
            .search(
                [
                    ("user_ids", "in", users.ids),
                    ("date_start", "!=", False),
                    ("date_end", "!=", False),
                ]
            )
        )
        _debug.pipeline("tasks_rebooked_on_employee", users=users, tasks=tasks)
        tasks._sync_reservations()
