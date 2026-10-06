import copy
from datetime import UTC, datetime, timedelta

from dateutil.rrule import DAILY, rrule

from odoo import models
from odoo.fields import Domain
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals
from odoo.tools.date_utils import get_intervals_hours

_debug = DebugLog(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _get_schedules_by_employee_by_work_type(
        self, start, stop, version_periods_by_employee
    ):
        res = super()._get_schedules_by_employee_by_work_type(
            start, stop, version_periods_by_employee
        )
        employee_schedule = copy.deepcopy(res["schedule"])
        planning_periods = []
        scheduled = self.env["planning.slot"]._get_scheduled_states()
        for employee, version_periods in version_periods_by_employee.items():
            for begin, end, version in version_periods:
                if version.work_entry_source == "planning":
                    planning_periods.append(
                        [
                            ("state", "in", scheduled),
                            ("start_datetime", "<=", end.replace(tzinfo=None)),
                            ("end_datetime", ">=", begin.replace(tzinfo=None)),
                        ]
                    )
                    version_period = Intervals(
                        [
                            (
                                begin.replace(tzinfo=None),
                                end.replace(tzinfo=None),
                                self.env["resource.calendar"],
                            )
                        ]
                    )
                    res["schedule"][employee]["work"] -= version_period
                    res["fully_flexible"][employee] -= version_period

        _debug.pipeline(
            "planning_schedule_periods_cleared",
            employees=self,
            planning_periods=len(planning_periods),
        )
        planning_slots_by_employee = dict(
            self.env["planning.slot"]
            .sudo()
            ._read_group(
                domain=Domain.AND(
                    [
                        Domain("state", "in", scheduled),
                        Domain("employee_id", "in", self.ids),
                        Domain.OR(planning_periods),
                    ]
                ),
                groupby=["employee_id"],
                aggregates=["id:recordset"],
            )
        )
        _debug.perf.count(
            "planning_schedule_slots_read",
            employees=self,
            employees_with_slots=len(planning_slots_by_employee),
        )
        for employee, planning_slots in planning_slots_by_employee.items():
            planning_slot_interval = Intervals([])
            tz = timezone(employee.tz)
            for planning_slot in planning_slots:
                start = (
                    planning_slot.start_datetime.replace(tzinfo=UTC)
                    .astimezone(tz)
                    .replace(tzinfo=None)
                )
                stop = (
                    planning_slot.end_datetime.replace(tzinfo=UTC)
                    .astimezone(tz)
                    .replace(tzinfo=None)
                )
                allocated_percentage = planning_slot.allocated_percentage
                schedule_interval = employee_schedule[employee]["work"] & Intervals(
                    [(start, stop, self.env["resource.calendar"])]
                )
                planning_intervals = Intervals([])
                if allocated_percentage == 100:
                    _debug.logic(
                        "planning_schedule_slot_full",
                        employee=employee,
                        slot=planning_slot,
                        start=start,
                        stop=stop,
                    )
                    planning_intervals = schedule_interval
                else:
                    _debug.logic(
                        "planning_schedule_slot_prorated",
                        employee=employee,
                        slot=planning_slot,
                        allocated_percentage=allocated_percentage,
                        start=start,
                        stop=stop,
                    )
                    for day in rrule(DAILY, dtstart=start, until=stop):
                        day_start = max(
                            datetime.combine(day, datetime.min.time()), start
                        )
                        day_stop = min(
                            datetime.combine(
                                day + timedelta(days=1), datetime.min.time()
                            ),
                            stop,
                        )
                        full_duration = get_intervals_hours(
                            schedule_interval
                            & Intervals(
                                [(day_start, day_stop, self.env["resource.calendar"])]
                            )
                        )
                        day_stop -= timedelta(
                            hours=full_duration * (100 - allocated_percentage)
                        )
                        planning_intervals |= Intervals(
                            [(day_start, day_stop, self.env["resource.calendar"])]
                        )
                planning_slot_interval |= planning_intervals
            res["schedule"][employee]["work"] |= planning_slot_interval
            _debug.pipeline(
                "planning_schedule_rebuilt",
                employee=employee,
                slots=planning_slots,
                intervals=len(planning_slot_interval),
            )
        return res
