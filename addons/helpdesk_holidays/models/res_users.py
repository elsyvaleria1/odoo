from datetime import UTC

from odoo import models
from odoo.libs.datetime import timezone
from odoo.libs.intervals import Intervals


class ResUsers(models.Model):
    _inherit = "res.users"

    def _get_working_user_interval(
        self, start_dt, end_dt, calendar, compute_leaves=True
    ):
        leaves = {}
        if compute_leaves:
            leaves = self.env["hr.leave"]._get_leave_interval(
                date_from=start_dt.astimezone(timezone("UTC")).replace(tzinfo=None),
                date_to=end_dt.astimezone(timezone("UTC")).replace(tzinfo=None),
                employee_ids=self.employee_id,
            )
        res = super()._get_working_user_interval(start_dt, end_dt, calendar, False)
        for employee in self.employee_ids:
            intervals = res[employee.resource_id.id]
            employee_leaves = leaves.get(employee.id, [])
            for leave in employee_leaves:
                if intervals:
                    leave_intervals = (
                        Intervals(
                            [
                                (
                                    leave.date_from.replace(tzinfo=UTC),
                                    leave.date_to.replace(tzinfo=UTC),
                                    leave,
                                )
                            ]
                        ),
                    )
                    intervals -= leave_intervals[0]
            res[employee.resource_id.id] = intervals
        return res
