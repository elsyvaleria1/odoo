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
        """Also show employees with an active contract version in the gantt's
        requested date range, even if they have no work entries yet.

        A plain `read_group` (what `get_gantt_data` ultimately runs) can only
        ever return a group for an `employee_id` value that already has at
        least one matching `hr.work.entry` -- it cannot invent an empty group
        for an employee with none. `group_expand` is the framework's own hook
        for exactly this ("also show these values even with zero matches");
        `web_gantt`'s `get_gantt_data` already requests it
        (`self.with_context(read_group_expand=True)`), so wiring it here is
        enough -- no extra domain-merging call needed.
        """
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
        # `_read_group_employee_id` (the `employee_id` group_expand hook above)
        # only sees the request's context, not these resolved kwargs -- pin
        # them into context so a caller that passed plain `start_date`/
        # `stop_date` kwargs (no `gantt_start_date`/`gantt_stop_date` context)
        # still expands correctly, the same as the JS gantt's own calls do.
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
        """Compute, per employee, the intervals where they are unavailable in [start, stop].

        :param field_name: unused, part of the base hook signature.
        :param res_ids: ``hr.employee`` ids to compute unavailability for.
        :param start: start of the period (timezone-aware datetime).
        :param stop: end of the period (timezone-aware datetime).
        :param scale: unused, part of the base hook signature.
        :return: dict mapping each employee id to a list of
            ``{"start": datetime, "stop": datetime}`` unavailable periods (UTC).
            An employee with no calendar is unavailable for the full interval;
            an employee with a fully flexible calendar is always available.
        :rtype: dict
        """
        employees_by_calendar = defaultdict(lambda: self.env["hr.employee"])
        employees = self.env["hr.employee"].browse(res_ids)

        # Retrieve for each employee, their period linked to their calendars
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

        # calculate the intervals not covered by employee-specific calendars.
        # store these uncovered intervals for each employee.
        # store by calendar, employees involved with them
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

        # retrieve, for each calendar, unavailability periods for employees linked to this calendar
        unavailable_intervals_by_calendar = {}
        for calendar, employees in employees_by_calendar.items():
            # A schedule without fixed hours leaves the employee always available.
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

        # calculate employee's unavailability periods based on his calendar's periods
        # (e.g. calendar A on monday and tuesday and calendar b for the rest of the week)
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
            # When an employee doesn't have any calendar,
            # he is considered unavailable for the entire interval
            if employee_id not in unavailable_intervals_by_employees:
                result[employee_id] = [
                    {
                        "start": start.astimezone(UTC),
                        "stop": stop.astimezone(UTC),
                    }
                ]
                continue

            # When an employee has a flexible calendar,
            # he is considered available for the entire interval
            if employee_id in flexible_employees.ids:
                result[employee_id] = []
                continue

            # When an employee doesn't have a calendar for a part of the entire interval,
            # he will be unavailable for this part
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
        """Compute the gantt progress-bar values for each employee.

        :param field_name: employee-relation field name on ``hr.work.entry`` used
            to group actual work entries.
        :param res_ids: ``hr.employee`` ids to compute the progress bar for.
        :param start: start of the period.
        :param stop: end of the period.
        :return: dict mapping each employee id to
            ``{"value": ..., "max_value": ..., "value_per_day": {...}, "max_per_day": {...}}``,
            where ``value``/``value_per_day`` are actual work entry durations
            and ``max_value``/``max_per_day`` are the expected durations
            derived from the employee's contract versions.
        :rtype: dict
        """
        # NOT `_get_all_versions_with_contract_overlap_with_period`: that one is
        # `@api.model` and searches every employee itself, so it silently drops
        # `res_ids` and makes us expand the whole payroll into work entry values
        # on each render, only to throw away every row the gantt never asked for.
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

        # Max duration value fetch
        # `v.employee_id.id`, not `v.employee_id`: `BaseModel.__lt__` is strict
        # subset, so two distinct employees are incomparable and the key orders
        # nothing between them. The pairing below walks each version against its
        # successor, so it needs an employee's versions to be adjacent and in
        # date order -- `date_version` is only reached when the first component
        # compares equal, which for two different employees it never does.
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
                # If the employee has multiple versions
                if (
                    current_version.date_version
                    < next_version.date_version
                    < start.date()
                ):
                    continue
                if next_version.date_version < stop.date():
                    # limit the interval stop with the version validity
                    temp_stop = datetime.combine(
                        next_version.date_version, datetime.min.time(), UTC
                    )
            if (
                current_version.contract_date_end
                and current_version.contract_date_end < stop.date()
            ):
                # limit the interval stop with the contract validity
                temp_stop = datetime.combine(
                    current_version.contract_date_end, datetime.min.time(), UTC
                ) + relativedelta(days=1)
            if current_version.date_version >= start.date():
                # limit the interval start with the version date if it's after the start date
                temp_start = datetime.combine(
                    current_version.date_version, datetime.min.time(), UTC
                )
            intervals_to_search[temp_start, temp_stop] |= current_version

        # The same behavior as work entry generation (batch per intervals) due to issues with _get_attendance_intervals
        # method makes a batch per all versions impossible for the whole date range
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

        # Current durations
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
