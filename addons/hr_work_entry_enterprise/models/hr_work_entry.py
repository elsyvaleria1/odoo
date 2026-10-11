from collections import defaultdict
from datetime import UTC, datetime
from itertools import chain, tee

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals
from odoo.tools.date_utils import localized

_debug = DebugLog(__name__)


class HrWorkEntry(models.Model):
    _inherit = "hr.work.entry"

    employee_id = fields.Many2one(group_expand="_read_group_employee_id")

    def _read_group_employee_id(self, employees, domain):
        start_date = self.env.context.get("gantt_start_date")
        stop_date = self.env.context.get("gantt_stop_date")
        if not (start_date and stop_date):
            _debug.logic("group_expand_skipped", reason="no_gantt_window")
            return employees
        employees_in_contract_ids = (
            self.env["hr.employee"]
            .search([])
            ._get_contract_versions(date_start=start_date, date_end=stop_date)
            .keys()
        )
        _debug.logic(
            "group_expand_employees",
            with_entries=employees,
            in_contract=len(employees_in_contract_ids),
        )
        return employees | self.env["hr.employee"].browse(employees_in_contract_ids)

    @api.model
    def get_gantt_data(
        self,
        domain,
        groupby,
        read_specification,
        limit=None,
        offset=0,
        unavailability_fields=None,
        progress_bar_fields=None,
        start_date=None,
        stop_date=None,
        scale=None,
    ):
        start_date = self.env.context.get("gantt_start_date") or start_date
        stop_date = self.env.context.get("gantt_stop_date") or stop_date
        domain = (
            Domain(domain)
            & Domain(self.env.context.get("active_domain") or Domain.TRUE)
            & Domain("date", "<", stop_date)
            & Domain("date", ">=", start_date)
        )
        return super(
            HrWorkEntry,
            self.with_context(gantt_start_date=start_date, gantt_stop_date=stop_date),
        ).get_gantt_data(
            domain,
            groupby,
            read_specification,
            limit=limit,
            offset=offset,
            unavailability_fields=unavailability_fields,
            progress_bar_fields=progress_bar_fields,
            start_date=start_date,
            stop_date=stop_date,
            scale=scale,
        )

    @api.model
    def _gantt_unavailability(self, field_name, res_ids, start, stop, scale):
        employees_by_calendar = defaultdict(lambda: self.env["hr.employee"])
        employees = self.env["hr.employee"].browse(res_ids)

        calendar_periods_by_employee = employees._get_calendar_periods(
            localized(start),
            localized(stop),
        )

        full_interval_UTC = Intervals(
            [
                (
                    start.astimezone(UTC),
                    stop.astimezone(UTC),
                    self.env["resource.calendar"],
                )
            ]
        )

        periods_without_calendar_by_employee = defaultdict(list)
        for employee, calendar_periods in calendar_periods_by_employee.items():
            employee_interval_UTC = Intervals([])
            for period_start, period_stop, calendar in calendar_periods:
                calendar_periods_interval_UTC = Intervals(
                    [
                        (
                            period_start.astimezone(UTC),
                            period_stop.astimezone(UTC),
                            self.env["resource.calendar"],
                        )
                    ]
                )
                employee_interval_UTC |= calendar_periods_interval_UTC
                employees_by_calendar[calendar] |= employee
            interval_without_calendar = full_interval_UTC - employee_interval_UTC
            if interval_without_calendar:
                periods_without_calendar_by_employee[employee.id] = (
                    interval_without_calendar
                )

        unavailable_intervals_by_calendar = {}
        for calendar, employees in employees_by_calendar.items():
            if calendar.schedule_type != "fully_fixed":
                unavailable_intervals_by_calendar[calendar] = {
                    employee.id: Intervals([]) for employee in employees
                }
                continue

            calendar_work_intervals = calendar._work_intervals_batch(
                localized(start),
                localized(stop),
                resources=employees.resource_id,
            )
            full_interval = Intervals(
                [
                    (
                        start.astimezone(timezone(calendar.tz)),
                        stop.astimezone(timezone(calendar.tz)),
                        calendar,
                    )
                ]
            )
            unavailable_intervals_by_calendar[calendar] = {
                employee.id: full_interval
                - calendar_work_intervals[employee.resource_id.id]
                for employee in employees
            }

        unavailable_intervals_by_employees = {}
        for employee, calendar_periods in calendar_periods_by_employee.items():
            employee_unavailable_full_interval = Intervals([])
            for period_start, period_stop, calendar in calendar_periods:
                interval = Intervals(
                    [(period_start, period_stop, self.env["resource.calendar"])]
                )
                calendar_unavailable_interval_list = unavailable_intervals_by_calendar[
                    calendar
                ][employee.id]
                employee_unavailable_full_interval |= (
                    interval & calendar_unavailable_interval_list
                )
            unavailable_intervals_by_employees[employee.id] = (
                employee_unavailable_full_interval
            )

        flexible_employees = self.env["hr.employee"]
        for calendar, employees in employees_by_calendar.items():
            if calendar.schedule_type == "flexible":
                flexible_employees |= employees

        result = {}
        for employee_id in res_ids:
            if employee_id not in unavailable_intervals_by_employees:
                result[employee_id] = [
                    {
                        "start": start.astimezone(UTC),
                        "stop": stop.astimezone(UTC),
                    }
                ]
                continue

            if employee_id in flexible_employees.ids:
                result[employee_id] = []
                continue

            if employee_id in periods_without_calendar_by_employee:
                unavailable_intervals_by_employees[employee_id] |= (
                    periods_without_calendar_by_employee[employee_id]
                )
            result[employee_id] = [
                {
                    "start": interval[0].astimezone(UTC),
                    "stop": interval[1].astimezone(UTC),
                }
                for interval in unavailable_intervals_by_employees[employee_id]
            ]

        return result

    @api.model
    def _gantt_progress_bar(self, field_name, res_ids, start, stop):
        employees = self.env["hr.employee"].browse(res_ids)
        all_versions = employees._get_versions_with_contract_overlap_with_period(
            start, stop
        )
        intervals_to_search = defaultdict(lambda: self.env["hr.version"])
        values = defaultdict(
            lambda: {
                "value": 0,
                "max_value": 0,
                "value_per_day": defaultdict(float),
                "max_per_day": defaultdict(float),
            }
        )

        all_version_normal, all_version_shifted = tee(
            all_versions.sorted(lambda v: (v.employee_id.id, v.date_version))
        )
        next(all_version_shifted, None)
        all_version_shifted = chain(all_version_shifted, [None])
        for current_version, next_version in zip(
            all_version_normal, all_version_shifted, strict=True
        ):
            temp_start = start
            temp_stop = stop
            if next_version and next_version.employee_id == current_version.employee_id:
                if (
                    current_version.date_version
                    < next_version.date_version
                    < start.date()
                ):
                    continue
                if next_version.date_version < stop.date():
                    temp_stop = datetime.combine(
                        next_version.date_version, datetime.min.time(), UTC
                    )
            if (
                current_version.contract_date_end
                and current_version.contract_date_end < stop.date()
            ):
                temp_stop = datetime.combine(
                    current_version.contract_date_end, datetime.min.time(), UTC
                ) + relativedelta(days=1)
            if current_version.date_version >= start.date():
                temp_start = datetime.combine(
                    current_version.date_version, datetime.min.time(), UTC
                )
            intervals_to_search[temp_start, temp_stop] |= current_version

        for interval, versions in intervals_to_search.items():
            date_from, date_to = interval
            for work_entry_value in self.env[
                "hr.version"
            ]._generate_work_entries_postprocess(
                versions._prepare_work_entries_values(date_from, date_to)
            ):
                if work_entry_value["date"] < stop.date():
                    values[work_entry_value["employee_id"]]["max_value"] += (
                        work_entry_value["duration"]
                    )
                    values[work_entry_value["employee_id"]]["max_per_day"][
                        str(work_entry_value["date"])
                    ] += work_entry_value["duration"]

        work_entries = self._read_group(
            domain=[
                (field_name, "in", res_ids),
                ["date", "<", stop],
                ["date", ">=", start],
            ],
            groupby=[field_name, "date:day"],
            aggregates=["duration:sum"],
        )

        for employee, date, duration in work_entries:
            values[employee.id]["value"] += duration
            values[employee.id]["value_per_day"][str(date)] += duration

        return values
