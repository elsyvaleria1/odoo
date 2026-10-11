from collections import defaultdict
from datetime import UTC, datetime, timedelta

from odoo import models
from odoo.libs.intervals import Intervals
from odoo.tools.date_utils import get_intervals_hours


class ProjectProject(models.Model):
    _name = "project.project"
    _inherit = ["project.project", "mixin.timesheet.grid"]

    def check_can_start_timer(self) -> dict | bool:
        self.check_singleton()
        if (
            self.sudo().company_id.hr_timesheet_config_id.timesheet_encode_uom_id
            == self.env.ref("base.product_uom_day")
        ):
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "message": self.env._(
                        "You cannot start the timer for a project in a company encoding its timesheets in days."
                    ),
                    "type": "danger",
                    "sticky": False,
                },
            }
        return True

    def write(self, vals):
        result = super().write(vals)
        if "allow_timesheets" in vals and not vals["allow_timesheets"]:
            self.env["timer.timer"].search(
                [
                    ("res_model", "=", "project.task"),
                    ("res_id", "in", self.with_context(active_test=False).task_ids.ids),
                ]
            ).unlink()
        return result

    def get_allocated_hours_field(self) -> str:
        return "allocated_hours"

    def get_fields_worked_hours(self) -> list:
        return ["total_timesheet_time"]

    def _allocated_hours_per_user_for_scale(self, users, start, stop):
        absolute_max_end, absolute_min_start = stop, start
        allocated_hours_mapped = defaultdict(float)
        for project in self:
            absolute_max_end = max(
                absolute_max_end,
                datetime.combine(
                    project.date + timedelta(days=1), datetime.min.time()
                ).replace(tzinfo=UTC),
            )
            absolute_min_start = min(
                absolute_min_start,
                datetime.combine(project.date_start, datetime.min.time()).replace(
                    tzinfo=UTC
                ),
            )

        users_work_intervals, _dummy = users.sudo()._get_valid_work_intervals(
            absolute_min_start, absolute_max_end
        )
        for project in self:
            project_date_start = datetime.combine(
                project.date_start, datetime.min.time()
            ).replace(tzinfo=UTC)
            project_date_end = datetime.combine(
                project.date + timedelta(days=1), datetime.min.time()
            ).replace(tzinfo=UTC)
            max_start = max(start, project_date_start)
            min_end = min(stop, project_date_end)
            user_id = project.user_id.id
            user_work_intervals = users_work_intervals.get(user_id, Intervals())
            work_intervals_for_scale = get_intervals_hours(
                user_work_intervals
                & Intervals(
                    [(max_start, min_end, self.env["resource.calendar.attendance"])]
                )
            )
            work_intervals_for_project = get_intervals_hours(
                user_work_intervals
                & Intervals(
                    [
                        (
                            project_date_start,
                            project_date_end,
                            self.env["resource.calendar.attendance"],
                        )
                    ]
                )
            )
            # The ratio between the workable hours in the gantt view scale and the workable hours
            # between start and end dates of the project allows to determine the allocated hours for the current scale
            ratio = 1
            if work_intervals_for_project:
                ratio = work_intervals_for_scale / work_intervals_for_project
            allocated_hours_mapped[user_id] += project.allocated_hours * ratio

        return allocated_hours_mapped

    def _gantt_progress_bar_user_id(self, res_ids, start, stop) -> dict:
        start_naive, stop_naive = start.replace(tzinfo=None), stop.replace(tzinfo=None)
        projects = self.env["project.project"].search(
            [
                ("user_id", "in", res_ids),
                ("date_start", "<=", stop_naive),
                ("date", ">=", start_naive),
            ]
        )
        users = projects.user_id
        allocated_hours_mapped = projects._allocated_hours_per_user_for_scale(
            users, start, stop
        )
        users_work_intervals, _dummy = users.sudo()._get_valid_work_intervals(
            start, stop
        )
        return {
            user.id: {
                "value": allocated_hours_mapped.get(user.id, 0.0),
                "max_value": get_intervals_hours(
                    users_work_intervals.get(user.id, Intervals())
                ),
            }
            for user in users
        }

    def _gantt_progress_bar(self, field_name, res_ids, start, stop):
        if not self.env.user.has_group("project.group_project_user"):
            return {}
        if field_name != "user_id":
            raise NotImplementedError("This Progress Bar is not implemented.")
        start, stop = start.replace(tzinfo=UTC), stop.replace(tzinfo=UTC)
        return dict(
            self._gantt_progress_bar_user_id(res_ids, start, stop),
            warning=self.env._(
                "This user isn't expected to have any projects assigned during this period because they don't have any running contract."
            ),
        )
