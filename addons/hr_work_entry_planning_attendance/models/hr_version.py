from collections import defaultdict

from odoo import models
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals

_debug = DebugLog(__name__)


class HrVersion(models.Model):
    _inherit = "hr.version"
    _name = "hr.version"

    def _get_attendance_intervals(self, start_dt, end_dt):
        # Planning-based contracts with attendance overtime
        mapped_intervals = super()._get_attendance_intervals(start_dt, end_dt)
        planning_based_contracts = self.filtered(
            lambda c: c.work_entry_source == "planning" and c.overtime_from_attendance
        )
        attendances = (
            self.env["hr.attendance"]
            .sudo()
            .search(
                [
                    ("employee_id", "in", planning_based_contracts.employee_id.ids),
                    ("check_in", "<=", end_dt.replace(tzinfo=None)),
                    (
                        "check_out",
                        ">=",
                        start_dt.replace(tzinfo=None),
                    ),  # We ignore attendances which don't have a check_out
                ]
            )
        )
        _debug.perf.count(
            "planning_overtime_attendances",
            versions=self,
            overtime_versions=planning_based_contracts,
            attendances=attendances,
            resources=len(mapped_intervals),
        )
        overtime_intervals = {
            r: Intervals(keep_distinct=True) for r in mapped_intervals
        }
        overtime_intervals.update(
            planning_based_contracts._get_overtime_intervals(start_dt, end_dt)
        )
        planning_based_contracts._set_real_overtime_intervals(
            start_dt, end_dt, attendances, mapped_intervals, overtime_intervals
        )
        work_entry_overtime_intervals = defaultdict(list)
        rejected = 0  # debuglog
        for r, intervals in overtime_intervals.items():
            for start, end, overtime in intervals:
                if not (
                    overtime.rule_ids.work_entry_type_id
                    and overtime.status == "approved"
                ):
                    rejected += 1  # debuglog
                    continue
                work_entry_overtime_intervals[r].extend([(start, end, overtime)])

        _debug.pipeline(
            "planning_overtime_intervals_kept",
            resources=len(mapped_intervals),
            kept=sum(len(v) for v in work_entry_overtime_intervals.values()),
            rejected=rejected,
        )
        return {
            r: (mapped_intervals[r] - overtime_intervals[r])
            | Intervals(work_entry_overtime_intervals[r], keep_distinct=True)
            for r in mapped_intervals
        }
