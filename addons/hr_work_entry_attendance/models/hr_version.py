from collections import defaultdict
from datetime import UTC, datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals

_debug = DebugLog(__name__)


class HrVersion(models.Model):
    _inherit = "hr.version"

    work_entry_source = fields.Selection(
        selection_add=[("attendance", "Attendances")],
        ondelete={"attendance": "set default"},
    )
    overtime_from_attendance = fields.Boolean(
        string="Extra hours",
        compute="_compute_overtime_from_attendance",
        store=True,
        readonly=False,
        tracking=True,
        classification="hr.compensation",
        groups="hr.group_hr_manager",
        help="Add extra hours from attendances to the working entries",
    )

    def _get_overtime_intervals(self, start_dt, end_dt):
        start_naive = start_dt.replace(tzinfo=None)
        end_naive = end_dt.replace(tzinfo=None)

        overtimes = self.env["hr.attendance.overtime.line"]._read_group(
            domain=[
                ("employee_id", "in", self.employee_id.ids),
                ("date", "<=", end_naive.date()),
                ("date", ">=", start_naive.date()),
                ("manual_duration", ">", 0),
            ],
            groupby=["employee_id", "date:day"],
            aggregates=["id:recordset"],
        )
        _debug.perf.count(
            "overtime_intervals",
            versions=self,
            employees=self.employee_id,
            groups=len(overtimes),
        )
        overtimes_by_employee_by_date = defaultdict(dict)
        for employee, date, overtime_lines in overtimes:
            overtimes_by_employee_by_date[employee][date] = overtime_lines
        res = {}
        for employee, overtimes_by_date in overtimes_by_employee_by_date.items():
            resource = employee.resource_id
            overtime_list = []
            for overtimes in overtimes_by_date.values():
                for ots in overtimes.grouped(
                    lambda ot: (ot.time_start, ot.time_stop)
                ).values():
                    prev_duration = 0
                    for ot in ots:
                        datetime_stop = min(
                            datetime.combine(
                                ot.date + timedelta(days=1), datetime.min.time()
                            ),
                            ot.time_stop,
                        ) - relativedelta(hours=prev_duration)
                        datetime_start = datetime_stop - timedelta(hours=ot.duration)
                        prev_duration += ot.duration
                        overtime_list.append(
                            (
                                datetime_start.replace(tzinfo=UTC),
                                datetime_stop.replace(tzinfo=UTC),
                                ot,
                            )
                        )
            res[resource.id] = Intervals(overtime_list, keep_distinct=True)
        return res

    def _set_real_overtime_intervals(
        self, start_dt, end_dt, attendances, mapped_intervals, overtime_intervals
    ) -> None:
        attendances_by_resources = attendances.grouped(
            lambda attendance: attendance.employee_id.resource_id.id
        )
        for resource in mapped_intervals:
            if resource not in attendances_by_resources:
                continue
            attendance_overtime_intersection = (
                overtime_intervals[resource] & mapped_intervals[resource]
            )
            if not attendance_overtime_intersection:
                continue
            resource_attendance_intervals = Intervals(
                [
                    (
                        att.check_in.replace(tzinfo=UTC),
                        att.check_out.replace(tzinfo=UTC),
                        self.env["hr.attendance"],
                    )
                    for att in attendances_by_resources[resource]
                ]
            )
            relevant_attendance_interval = resource_attendance_intervals & Intervals(
                [(start_dt, end_dt, self.env["hr.attendance"])]
            )
            duration_remaining_by_overtime_line = defaultdict(float)
            for _start, _stop, model in overtime_intervals[resource]:
                duration_remaining_by_overtime_line[model] += model.duration
            real_overtime_intervals = Intervals(keep_distinct=True)
            outside_schedule_intervals = (
                relevant_attendance_interval - mapped_intervals[resource]
            )
            for intervals in [outside_schedule_intervals, mapped_intervals[resource]]:
                for start, stop, _model in intervals:
                    interval_duration = (stop - start).total_seconds() / 3600
                    remaining_duration = interval_duration
                    current_position = start

                    for (
                        ot_line,
                        duration,
                    ) in duration_remaining_by_overtime_line.items():
                        if remaining_duration <= 0:
                            break
                        if not duration:
                            continue

                        allocated_duration = min(remaining_duration, duration)

                        real_overtime_intervals |= Intervals(
                            [
                                (
                                    current_position,
                                    current_position
                                    + relativedelta(hours=allocated_duration),
                                    ot_line,
                                )
                            ]
                        )

                        duration_remaining_by_overtime_line[ot_line] -= (
                            allocated_duration
                        )
                        remaining_duration -= allocated_duration
                        current_position += relativedelta(hours=allocated_duration)

            overtime_intervals[resource] = real_overtime_intervals

    def _get_attendance_intervals(self, start_dt, end_dt):
        start_naive = start_dt.replace(tzinfo=None)
        end_naive = end_dt.replace(tzinfo=None)
        overtime_contracts = self.filtered_domain(
            ["|", ("work_entry_source", "=", "attendance"), ("ruleset_id", "!=", False)]
        )
        attendance_based_contracts = self.filtered_domain(
            [("work_entry_source", "=", "attendance")]
        )
        search_domain = [
            ("employee_id", "in", overtime_contracts.employee_id.ids),
            ("check_in", "<=", end_naive),
            (
                "check_out",
                ">=",
                start_naive,
            ),
        ]
        resource_ids = attendance_based_contracts.employee_id.resource_id.ids
        all_attendances = self.env["hr.attendance"].sudo().search(search_domain)
        attendances = (
            all_attendances.filtered_domain(
                [("employee_id.work_entry_source", "=", "attendance")]
            )
            if attendance_based_contracts
            else self.env["hr.attendance"]
        )
        _debug.logic(
            "attendance_intervals_scope",
            overtime_versions=overtime_contracts,
            attendance_based=attendance_based_contracts,
            attendances=all_attendances,
            used=attendances,
        )
        intervals = defaultdict(list)
        calendar_by_employee = {}
        leaves = {}
        lunches = {}
        employee_by_calendar = defaultdict(lambda: self.env["hr.employee"])
        for version in self:
            calendar = version.resource_calendar_id
            if calendar.schedule_type == "fully_fixed":
                calendar_by_employee[version.employee_id] = calendar
                employee_by_calendar[calendar] += version.employee_id
        for calendar, employees in employee_by_calendar.items():
            leaves |= calendar._leave_intervals_batch(
                start_dt, end_dt, resources=employees.resource_id
            )
            lunches |= calendar._attendance_intervals_batch(
                start_dt, end_dt, resources=employees.resource_id, lunch=True
            )
        for attendance in attendances:
            resource = attendance.employee_id.resource_id
            tz = timezone(
                attendance.employee_id.tz or resource.tz
            )
            check_in_tz = attendance.check_in.astimezone(tz)
            check_out_tz = attendance.check_out.astimezone(tz)
            if attendance.overtime_status == "refused":
                check_out_tz -= timedelta(hours=attendance.validated_overtime_hours)

            resource_lunch = lunches.get(
                attendance.employee_id.resource_id.id, Intervals([])
            )
            resource_leave = leaves.get(
                attendance.employee_id.resource_id.id, Intervals([])
            )
            real_lunch_intervals = resource_lunch - resource_leave
            attendance_intervals = (
                Intervals([(check_in_tz, check_out_tz, attendance)])
                - real_lunch_intervals
            )
            for interval in attendance_intervals:
                intervals[resource.id].append(
                    (max(start_dt, interval[0]), min(end_dt, interval[1]), attendance)
                )

        mapped_intervals = {
            r: Intervals(intervals[r], keep_distinct=True) for r in resource_ids
        }
        mapped_intervals.update(super()._get_attendance_intervals(start_dt, end_dt))

        overtime_intervals = {
            r: Intervals(keep_distinct=True) for r in mapped_intervals
        }
        overtime_intervals.update(
            overtime_contracts._get_overtime_intervals(start_dt, end_dt)
        )
        overtime_attendances = all_attendances.filtered_domain(
            [
                ("employee_id.ruleset_id", "!=", False),
                ("employee_id.work_entry_source", "=", "calendar"),
            ]
        )
        overtime_contracts._set_real_overtime_intervals(
            start_dt, end_dt, overtime_attendances, mapped_intervals, overtime_intervals
        )
        work_entry_overtime_intervals = defaultdict(list)
        for r, intervals in overtime_intervals.items():
            for start, end, overtime in intervals:
                if not (
                    overtime.rule_ids.work_entry_type_id
                    and overtime.status == "approved"
                ):
                    continue
                work_entry_overtime_intervals[r].extend([(start, end, overtime)])

        return {
            r: (mapped_intervals[r] - overtime_intervals[r])
            | Intervals(work_entry_overtime_intervals[r], keep_distinct=True)
            for r in mapped_intervals
        }

    def _get_valid_leave_intervals(self, attendances, interval):
        self.check_singleton()
        badge_attendances = Intervals(
            [
                (start, end, record)
                for (start, end, record) in attendances
                if start <= interval[1]
                and end > interval[0]
                and isinstance(record, self.env["hr.attendance"].__class__)
            ],
            keep_distinct=True,
        )
        if badge_attendances:
            leave_interval = Intervals([interval], keep_distinct=True)
            return list(leave_interval - badge_attendances)
        return super()._get_valid_leave_intervals(attendances, interval)

    def _prepare_real_attendance_work_entry_vals(self, intervals):
        self.check_singleton()
        non_attendance_intervals = [
            interval
            for interval in intervals
            if interval[2]._name not in ["hr.attendance", "hr.attendance.overtime.line"]
        ]
        attendance_intervals = [
            interval
            for interval in intervals
            if interval[2]._name in ["hr.attendance", "hr.attendance.overtime.line"]
        ]
        if attendance_intervals:
            default_overtime_type = self.env.ref(
                "hr_work_entry.work_entry_type_overtime"
            )
            attendance_work_entry_type = self.env.ref(
                "hr_work_entry.work_entry_type_attendance"
            )
        vals = super()._prepare_real_attendance_work_entry_vals(
            non_attendance_intervals
        )

        employee = self.employee_id
        for interval in attendance_intervals:
            if interval[2]._name == "hr.attendance":
                work_entry_type = attendance_work_entry_type
                vals += [
                    dict(
                        [
                            ("name", "%s: %s" % (work_entry_type.name, employee.name)),
                            (
                                "date_start",
                                interval[0].astimezone(UTC).replace(tzinfo=None),
                            ),
                            (
                                "date_stop",
                                interval[1].astimezone(UTC).replace(tzinfo=None),
                            ),
                            ("work_entry_type_id", work_entry_type.id),
                            ("employee_id", employee.id),
                            ("version_id", self.id),
                            ("company_id", self.company_id.id),
                        ]
                        + self._get_more_vals_attendance_interval(interval)
                    )
                ]
            elif interval[2]._name == "hr.attendance.overtime.line":
                overtime_mode = self.ruleset_id.rate_combination_mode
                overtime_line_id = interval[2]
                paid_rules = overtime_line_id.rule_ids.filtered("paid")
                if not paid_rules:
                    continue

                triggered_rule_work_entry_types = (
                    paid_rules.mapped("work_entry_type_id") or default_overtime_type
                )
                date_start = interval[0].astimezone(UTC).replace(tzinfo=None)
                date_stop = interval[1].astimezone(UTC).replace(tzinfo=None)
                if overtime_mode == "max" or len(triggered_rule_work_entry_types) == 1:
                    work_entry_type = max(
                        triggered_rule_work_entry_types, key=lambda w: w.amount_rate
                    )
                    vals += [
                        dict(
                            [
                                (
                                    "name",
                                    "%s: %s" % (work_entry_type.name, employee.name),
                                ),
                                ("date_start", date_start),
                                ("date_stop", date_stop),
                                ("work_entry_type_id", work_entry_type.id),
                                ("employee_id", employee.id),
                                ("version_id", self.id),
                                ("company_id", self.company_id.id),
                            ]
                            + self._get_more_vals_attendance_interval(interval)
                        )
                    ]
                else:
                    for triggered_rule in paid_rules:
                        vals += [
                            dict(
                                [
                                    (
                                        "name",
                                        "%s: %s"
                                        % (
                                            triggered_rule.work_entry_type_id.name,
                                            employee.name,
                                        ),
                                    ),
                                    ("date_start", date_start),
                                    ("date_stop", date_stop),
                                    (
                                        "work_entry_type_id",
                                        triggered_rule.work_entry_type_id.id,
                                    ),
                                    ("employee_id", employee.id),
                                    ("version_id", self.id),
                                    ("company_id", self.company_id.id),
                                ]
                                + self._get_more_vals_attendance_interval(interval)
                            )
                        ]
        return vals

    def _get_more_vals_attendance_interval(self, interval):
        vals = super()._get_more_vals_attendance_interval(interval)
        if interval[2]._name == "hr.attendance":
            vals.append(("attendance_id", interval[2].id))
        if interval[2]._name == "hr.attendance.overtime.line":
            vals.append(("overtime_id", interval[2].id))
        return vals

    def _get_real_attendances(self, attendances, leaves, worked_leaves):
        attendances_list = []
        no_attendances_list = []
        for start, stop, model in attendances:
            if model._name in ["hr.attendance", "hr.attendance.overtime.line"]:
                attendances_list.append((start, stop, model))
            else:
                no_attendances_list.append((start, stop, model))
        super_list = list(
            super()._get_real_attendances(
                Intervals(no_attendances_list, keep_distinct=True),
                leaves,
                worked_leaves,
            )
        )
        return Intervals(attendances_list + super_list, keep_distinct=True)

    @api.model
    def _get_whitelist_fields_from_template(self):
        return super()._get_whitelist_fields_from_template() + [
            "overtime_from_attendance"
        ]

    @api.depends("ruleset_id")
    def _compute_overtime_from_attendance(self) -> None:
        for record in self:
            record.overtime_from_attendance = bool(record.ruleset_id)
