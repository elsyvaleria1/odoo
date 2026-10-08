from odoo import api, models
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees._adopt_direct_assignments()
        return employees

    def write(self, vals):
        result = super().write(vals)
        if vals.get("user_id"):
            self._adopt_direct_assignments()
        if "resource_id" in vals and self.ids:
            tasks = self._get_tasks_sudo().search([("employee_ids", "in", self.ids)])
            _debug.pipeline(
                "employee_resource_changed_resyncing_tasks",
                employees=self,
                tasks=tasks,
            )
            if tasks:
                tasks._sync_reservations()
        return result

    def _get_tasks_sudo(self):
        # an HR officer edits employees without reaching every project they
        # are assigned in, and the tasks follow the employee all the same
        return self.env["project.task"].sudo()

    def _adopt_direct_assignments(self) -> None:
        # a user is assigned directly only while they hold no employee: the
        # employee they are given takes those assignments over
        tasks_sudo = self._get_tasks_sudo().with_context(
            active_test=False, tracking_disable=True
        )
        for user, employees in self.filtered("user_id").grouped("user_id").items():
            tasks = tasks_sudo.search([("direct_user_ids", "in", user.ids)])
            _debug.pipeline(
                "direct_assignments_adopted",
                user=user,
                employees=employees,
                tasks=tasks,
            )
            by_company = employees.grouped("company_id")
            for company, company_tasks in tasks.grouped("company_id").items():
                employee = by_company.get(company, employees)[:1]
                company_tasks.write(
                    {
                        "direct_user_ids": [Command.unlink(user.id)],
                        "employee_ids": [Command.link(employee.id)],
                    }
                )
