from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime, time, timedelta
from itertools import chain, pairwise
from typing import Self

from dateutil.relativedelta import relativedelta
from dateutil.rrule import DAILY, rrule

from odoo import api, exceptions, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.http import request
from odoo.libs.datetime import float_to_time, timezone
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals
from odoo.tools import (
    convert,
    format_datetime,
    format_duration,
    format_time,
    frozendict,
)
from odoo.tools.date_utils import get_intervals_hours

from ..tools import demo
from odoo.addons.base.models.resource_utils import last_day_of

_debug = DebugLog(__name__)


def get_google_maps_url(latitude, longitude) -> str:
    return "https://maps.google.com?q=%s,%s" % (latitude, longitude)


class HrAttendance(models.Model):
    _name = "hr.attendance"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("employee_id.company_id", shared=True),
            "employee": "employee_id",
            "owner": "employee_id.attendance_manager_id",
        }
    )
    _description = "Attendance"
    _order = "check_in desc"
    _inherit = ["mixin.mail.thread"]

    def _default_employee_id(self):
        if self.env.user.has_group("hr_attendance.group_hr_attendance_user"):
            return self.env.user.employee_id
        return None

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        default=lambda self: self._default_employee_id(),
        index=True,
        required=True,
        group_expand="_read_group_employee_id",
        ondelete="cascade",
    )
    department_id = fields.Many2one(
        comodel_name="hr.department",
        related="employee_id.department_id",
        string="Department",
        readonly=True,
    )
    manager_id = fields.Many2one(
        comodel_name="hr.employee",
        related="employee_id.parent_id",
        export_string_translation=False,
        readonly=True,
    )
    attendance_manager_id = fields.Many2one(
        comodel_name="res.users",
        related="employee_id.attendance_manager_id",
        export_string_translation=False,
    )
    is_manager = fields.Boolean(compute="_compute_is_manager")
    check_in = fields.Datetime(
        default=fields.Datetime.now,
        index=True,
        required=True,
        tracking=True,
    )
    check_out = fields.Datetime(tracking=True)
    date = fields.Date(
        compute="_compute_date",
        precompute=True,
        store=True,
        index=True,
        required=True,
    )
    day_of_date = fields.Selection(
        selection=[
            ("0", "Monday"),
            ("1", "Tuesday"),
            ("2", "Wednesday"),
            ("3", "Thursday"),
            ("4", "Friday"),
            ("5", "Saturday"),
            ("6", "Sunday"),
        ],
        string="Day of Week",
        compute="_compute_day_of_date",
        precompute=True,
        store=True,
    )
    resource_calendar_id = fields.Many2one(
        related="employee_id.resource_calendar_id",
        string="Working Schedule",
    )
    worked_hours = fields.Float(
        compute="_compute_worked_hours",
        store=True,
        readonly=True,
    )
    color = fields.Integer(compute="_compute_color")
    overtime_hours = fields.Float(
        string="Over Time",
        compute="_compute_overtime_hours",
        store=True,
    )
    overtime_status = fields.Selection(
        selection=[
            ("to_approve", "To Approve"),
            ("approved", "Approved"),
            ("refused", "Refused"),
        ],
        compute="_compute_overtime_status",
        store=True,
        readonly=False,
        tracking=True,
    )
    validated_overtime_hours = fields.Float(
        string="Extra Hours",
        compute="_compute_validated_overtime_hours",
        store=True,
        readonly=True,
        tracking=True,
    )
    in_latitude = fields.Float(
        string="Latitude",
        digits=(10, 7),
        readonly=True,
        aggregator=None,
    )
    in_longitude = fields.Float(
        string="Longitude",
        digits=(10, 7),
        readonly=True,
        aggregator=None,
    )
    in_location = fields.Char(
        help="Based on GPS-Coordinates if available or on IP Address"
    )
    in_ip_address = fields.Char(
        string="IP Address",
        readonly=True,
    )
    in_browser = fields.Char(
        string="Browser",
        readonly=True,
    )
    in_mode = fields.Selection(
        selection=[
            ("kiosk", "Kiosk"),
            ("systray", "Systray"),
            ("manual", "Manual"),
            ("technical", "Technical"),
        ],
        string="Mode",
        default="manual",
        readonly=True,
    )
    out_latitude = fields.Float(
        digits=(10, 7),
        readonly=True,
        aggregator=None,
    )
    out_longitude = fields.Float(
        digits=(10, 7),
        readonly=True,
        aggregator=None,
    )
    out_location = fields.Char(
        help="Based on GPS-Coordinates if available or on IP Address"
    )
    out_ip_address = fields.Char(readonly=True)
    out_browser = fields.Char(readonly=True)
    out_mode = fields.Selection(
        selection=[
            ("kiosk", "Kiosk"),
            ("systray", "Systray"),
            ("manual", "Manual"),
            ("technical", "Technical"),
            ("auto_check_out", "Automatic Check-Out"),
        ],
        default="manual",
        readonly=True,
    )
    expected_hours = fields.Float(
        compute="_compute_expected_hours",
        store=True,
        aggregator="sum",
    )
    device_tracking_enabled = fields.Boolean(
        related="employee_id.company_id.hr_attendance_config_id.attendance_device_tracking"
    )
    linked_overtime_ids = fields.One2many(
        comodel_name="hr.attendance.overtime.line",
        inverse_name="attendance_id",
        readonly=False,
    )

    @api.depends("check_in", "employee_id")
    def _compute_date(self) -> None:
        for attendance in self:
            if not attendance.employee_id or not attendance.check_in:
                attendance.date = fields.Date.context_today(attendance)
                continue
            tz = attendance._schedule_tz()
            attendance.date = (
                attendance.check_in.replace(tzinfo=UTC).astimezone(tz).date()
            )
            _debug.logic(
                "date_computed",
                attendance=attendance,
                check_in=attendance.check_in,
                tz=tz,
                date=attendance.date,
            )

    @api.depends("date")
    def _compute_day_of_date(self) -> None:
        for attendance in self:
            attendance.day_of_date = (
                str(attendance.date.weekday()) if attendance.date else False
            )

    @api.depends("worked_hours", "linked_overtime_ids.duration")
    def _compute_expected_hours(self) -> None:
        for attendance in self:
            attendance.expected_hours = attendance.worked_hours - sum(
                attendance.linked_overtime_ids.mapped("duration")
            )

    @api.depends("check_in", "check_out", "worked_hours", "out_mode")
    def _compute_color(self) -> None:
        stale = fields.Datetime.now() - timedelta(days=1)
        for attendance in self:
            if attendance.check_out:
                attendance.color = (
                    1
                    if attendance.worked_hours > 16
                    or attendance.out_mode == "technical"
                    else 0
                )
            elif not attendance.check_in:
                attendance.color = 0
            else:
                attendance.color = 1 if attendance.check_in < stale else 10

    @api.depends("linked_overtime_ids.status")
    def _compute_overtime_status(self) -> None:
        for attendance in self:
            statuses = set(attendance.linked_overtime_ids.mapped("status"))
            if not statuses:
                attendance.overtime_status = False
            elif statuses == {"approved"}:
                attendance.overtime_status = "approved"
            elif statuses == {"refused"}:
                attendance.overtime_status = "refused"
            else:
                attendance.overtime_status = "to_approve"

    @api.depends("linked_overtime_ids.manual_duration")
    def _compute_overtime_hours(self) -> None:
        for attendance in self:
            attendance.overtime_hours = sum(
                attendance.linked_overtime_ids.mapped("manual_duration")
            )

    @api.depends("linked_overtime_ids.manual_duration", "linked_overtime_ids.status")
    def _compute_validated_overtime_hours(self) -> None:
        for attendance in self:
            attendance.validated_overtime_hours = sum(
                attendance.linked_overtime_ids.filtered_domain(
                    [("status", "=", "approved")]
                ).mapped("manual_duration")
            )

    @api.depends("employee_id", "check_in", "check_out")
    def _compute_display_name(self):
        tz = request.httprequest.cookies.get("tz") if request else None
        for attendance in self:
            if not attendance.check_out:
                attendance.display_name = self.env._(
                    "From %s",
                    format_time(
                        self.env,
                        attendance.check_in,
                        time_format=None,
                        tz=tz,
                        lang_code=self.env.lang,
                    ),
                )
            else:
                attendance.display_name = self.env._(
                    "%(worked_hours)s (%(check_in)s-%(check_out)s)",
                    worked_hours=format_duration(attendance.worked_hours),
                    check_in=format_time(
                        self.env,
                        attendance.check_in,
                        time_format=None,
                        tz=tz,
                        lang_code=self.env.lang,
                    ),
                    check_out=format_time(
                        self.env,
                        attendance.check_out,
                        time_format=None,
                        tz=tz,
                        lang_code=self.env.lang,
                    ),
                )

    @api.depends("employee_id")
    def _compute_is_manager(self) -> None:
        have_manager_right = self.env.user.has_group(
            "hr_attendance.group_hr_attendance_user"
        )
        have_officer_right = self.env.user.has_group(
            "hr_attendance.group_hr_attendance_officer"
        )
        for attendance in self:
            attendance.is_manager = have_manager_right or (
                have_officer_right
                and attendance.attendance_manager_id.id == self.env.user.id
            )

    _SCHEDULE_VERSION_PASSES = 3

    def _schedule_version(self):
        self.check_singleton()
        employee = self.employee_id.sudo()
        version = employee._get_version(self.check_in.date())
        for _pass in range(self._SCHEDULE_VERSION_PASSES):
            local_day = (
                self.check_in.replace(tzinfo=UTC)
                .astimezone(timezone(version._get_schedule_tz()))
                .date()
            )
            settled = employee._get_version(local_day)
            if settled == version:
                break
            version = settled
        return version

    def _schedule_tz(self, version=None):
        return timezone((version or self._schedule_version())._get_schedule_tz())

    def _get_employee_calendar(self, version=None):
        self.check_singleton()
        return (version or self._schedule_version()).resource_calendar_id

    @api.depends("check_in", "check_out", "employee_id")
    def _compute_worked_hours(self) -> None:
        for attendance in self:
            if attendance.check_out and attendance.check_in and attendance.employee_id:
                attendance.worked_hours = attendance._get_worked_hours_in_range(
                    attendance.check_in, attendance.check_out
                )
            else:
                attendance.worked_hours = False

    def _get_worked_hours_in_range(self, start_dt, end_dt):
        self.check_singleton()
        return self._worked_hours_between(
            max(self.check_in, start_dt), min(self.check_out, end_dt)
        )

    def _worked_hours_between(self, start_dt, end_dt):
        self.check_singleton()
        version = self._schedule_version()
        tz = self._schedule_tz(version)
        start_dt_tz = start_dt.replace(tzinfo=UTC).astimezone(tz)
        end_dt_tz = end_dt.replace(tzinfo=UTC).astimezone(tz)

        if end_dt_tz < start_dt_tz:
            return 0.0

        return get_intervals_hours(
            Intervals([(start_dt_tz, end_dt_tz, self)])
            - self._lunch_intervals(start_dt_tz, end_dt_tz, version=version)
        )

    def _lunch_intervals(self, start_dt_tz, end_dt_tz, version=None):
        self.check_singleton()
        version = version or self._schedule_version()
        calendar = self._get_employee_calendar(version)
        return calendar._attendance_intervals_batch(
            start_dt_tz,
            end_dt_tz,
            tz=self._schedule_tz(version),
            lunch=True,
        )[False]

    @api.constrains("check_in", "check_out")
    def _check_validity_check_in_check_out(self) -> None:
        for attendance in self:
            if attendance.check_in and attendance.check_out:
                if attendance.check_out < attendance.check_in:
                    raise exceptions.ValidationError(
                        self.env._(
                            '"Check Out" time cannot be earlier than "Check In" time.'
                        )
                    )

    @api.constrains("check_in", "check_out", "employee_id")
    def _check_validity(self):
        for employee, attendances in self.grouped("employee_id").items():
            for earlier, later in self._sorted_span_pairs(employee, attendances):
                if earlier.check_out and earlier.check_out <= later.check_in:
                    continue
                _debug.logic(
                    "attendances_overlap",
                    earlier=earlier,
                    later=later,
                    employee=employee,
                )
                raise exceptions.ValidationError(
                    self.env._(
                        "Cannot create new attendance record for %(empl_name)s, the employee was already checked in on %(datetime)s",
                        empl_name=employee.sudo().name,
                        datetime=format_datetime(
                            self.env, earlier.check_in, dt_format=False
                        ),
                    )
                )

    def _sorted_span_pairs(self, employee, attendances):
        window_start = min(attendances.mapped("check_in"))
        domain = Domain("employee_id", "=", employee.id) & Domain(
            Domain("check_out", "=", False) | Domain("check_out", ">", window_start)
        )
        if all(attendance.check_out for attendance in attendances):
            domain &= Domain("check_in", "<", max(attendances.mapped("check_out")))
        neighbours = self.env["hr.attendance"].sudo().search(domain)
        spans = (neighbours | attendances).sorted(lambda a: (a.check_in, a.id))
        return pairwise(spans)

    @api.model
    def _get_day_start_and_day(self, employee, dt) -> tuple:
        if not dt.tzinfo:
            calendar_tz = employee._get_schedule_tz_batch(dt)[employee.id]
            date_employee_tz = dt.replace(tzinfo=UTC).astimezone(timezone(calendar_tz))
        else:
            date_employee_tz = dt
        start_day_employee_tz = date_employee_tz.replace(hour=0, minute=0, second=0)
        return (
            start_day_employee_tz.astimezone(UTC).replace(tzinfo=None),
            start_day_employee_tz.date(),
        )

    def _local_date_span(self) -> tuple:
        self.check_singleton()
        start, stop = self._get_localized_times()
        return start.date(), last_day_of(start, stop)

    @staticmethod
    def _merge_windows(*window_dicts):
        merged = {}
        for windows in window_dicts:
            for employee, (first, last) in (windows or {}).items():
                if employee in merged:
                    first = min(first, merged[employee][0])
                    last = max(last, merged[employee][1])
                merged[employee] = (first, last)
        return merged

    def _overtime_windows(self):
        windows = {}
        for employee, attendances in self.grouped("employee_id").items():
            spans = [
                attendance._local_date_span()
                for attendance in attendances
                if attendance.check_out
            ]
            if not spans:
                continue
            first = min(span[0] for span in spans)
            last = max(span[1] for span in spans)
            windows[employee] = employee._round_overtime_window(first, last)
            _debug.pipeline(
                "overtime_window_rounded",
                employee=employee.id,
                first=first,
                last=last,
                rounded_first=windows[employee][0],
                rounded_last=windows[employee][1],
            )
        return windows

    def _attendances_in_overtime_windows(self, windows) -> tuple:
        Attendance = self.env["hr.attendance"].sudo()
        selected = Attendance
        closed = {}
        for employee, (first, last) in windows.items():
            passes = 0
            while True:
                passes += 1
                candidates = Attendance.search(
                    [
                        ("employee_id", "=", employee.id),
                        ("check_out", "!=", False),
                        (
                            "check_in",
                            "<=",
                            datetime.combine(last, time.max) + timedelta(days=1),
                        ),
                        (
                            "check_out",
                            ">=",
                            datetime.combine(first, time.min) - timedelta(days=1),
                        ),
                    ]
                )
                spans = [
                    span
                    for attendance in candidates
                    if (span := attendance._local_date_span())[1] >= first
                    and span[0] <= last
                ]
                if not spans:
                    break
                grown = employee._round_overtime_window(
                    min(first, *(span[0] for span in spans)),
                    max(last, *(span[1] for span in spans)),
                )
                if grown == (first, last):
                    break
                _debug.logic(
                    "overtime_window_grown",
                    employee=employee.id,
                    first=first,
                    last=last,
                    grown_first=grown[0],
                    grown_last=grown[1],
                    passes=passes,
                )
                first, last = grown
            closed[employee] = (first, last)
            _debug.pipeline(
                "overtime_window_closed",
                employee=employee.id,
                first=first,
                last=last,
                attendances=len(candidates),
                passes=passes,
            )
            selected |= candidates._filtered_local_span_overlapping(first, last)
        return closed, selected

    def _filtered_local_span_overlapping(self, first, last) -> Self:
        return self.filtered(
            lambda attendance: (
                (span := attendance._local_date_span())[1] >= first and span[0] <= last
            )
        )

    def _update_overtime(self, windows=None) -> None:
        windows = self._merge_windows(self._overtime_windows(), windows)
        if not windows:
            _debug.logic("overtime_skipped", attendances=self, reason="none_closed")
            return
        windows, all_attendances = self._attendances_in_overtime_windows(windows)
        Line = self.env["hr.attendance.overtime.line"].sudo()
        superseded = Line.search(
            Domain.OR(
                Domain("employee_id", "=", employee.id)
                & Domain("date", ">=", first)
                & Domain("date", "<=", last)
                for employee, (first, last) in windows.items()
            )
        )
        decisions_by_key = defaultdict(list)
        for line in superseded:
            decisions_by_key[line._regeneration_key()].append(
                {"status": line.status, "manual_duration": line.manual_duration}
            )
        _debug.lifecycle(
            "overtime_lines_superseded", lines=len(superseded), windows=len(windows)
        )
        superseded.unlink()
        if not all_attendances:
            return

        start_check_in = min(all_attendances.mapped("check_in")).date() - relativedelta(
            days=1
        )
        min_check_in = datetime.combine(start_check_in, datetime.min.time()).replace(
            tzinfo=UTC
        )

        start_check_out = max(
            all_attendances.mapped("check_out")
        ).date() + relativedelta(days=1)
        max_check_out = datetime.combine(start_check_out, datetime.max.time()).replace(
            tzinfo=UTC
        )

        version_periods_by_employee = (
            all_attendances.employee_id.sudo()._get_version_periods(
                min_check_in, max_check_out
            )
        )
        attendances_by_employee = all_attendances.grouped("employee_id")
        attendances_by_ruleset = defaultdict(lambda: self.env["hr.attendance"])
        for employee, emp_attendance in attendances_by_employee.items():
            for attendance in emp_attendance:
                attendance_intervals = Intervals(
                    [
                        (
                            attendance.check_in.replace(tzinfo=UTC),
                            attendance.check_out.replace(tzinfo=UTC),
                            self.env["hr.version"],
                        )
                    ]
                )
                inter = (
                    Intervals(version_periods_by_employee[employee])
                    & attendance_intervals
                )
                if not inter:
                    continue
                version = inter._items[0][2]
                ruleset = version.ruleset_id
                if ruleset:
                    attendances_by_ruleset[ruleset] += attendance
        employees = all_attendances.employee_id
        schedules_intervals_by_employee = (
            employees._get_schedules_by_employee_by_work_type(
                min_check_in, max_check_out, version_periods_by_employee
            )
        )
        overtime_vals_list = []
        for ruleset, ruleset_attendances in attendances_by_ruleset.items():
            attendances_dates = list(chain(*ruleset_attendances._get_dates().values()))
            overtime_vals_list.extend(
                ruleset.rule_ids._generate_overtime_vals(
                    min(attendances_dates),
                    max(attendances_dates),
                    ruleset_attendances,
                    schedules_intervals_by_employee,
                )
            )
        for vals in overtime_vals_list:
            decisions = decisions_by_key.get(Line._regeneration_key_from_vals(vals))
            if decisions:
                vals.update(decisions.pop(0))
        _debug.lifecycle(
            "overtime_lines_created",
            lines=len(overtime_vals_list),
            attendances=len(all_attendances),
            kept_decisions=sum(
                len(decisions) for decisions in decisions_by_key.values()
            ),
        )
        Line.create(overtime_vals_list)

    _OVERTIME_SOURCE_FIELDS = frozenset({"employee_id", "check_in", "check_out"})
    _OVERTIME_DEFERRAL = "hr_attendance_deferred_overtime"

    @contextmanager
    def _deferring_overtime(self):
        pending = self.env.context.get(self._OVERTIME_DEFERRAL)
        if pending is not None:
            yield self
            return
        pending = {"windows": {}, "records": self.browse()}
        try:
            yield self.with_context(**{self._OVERTIME_DEFERRAL: pending})
        finally:
            pending["records"].exists()._update_overtime(pending["windows"])

    def _defer_overtime(self, windows=None, records=None) -> bool:
        pending = self.env.context.get(self._OVERTIME_DEFERRAL)
        if pending is None:
            return False
        pending["windows"] = self._merge_windows(pending["windows"], windows)
        if records is not None:
            pending["records"] |= records
        return True

    @api.model_create_multi
    @_debug.perf.timed
    def create(self, vals_list):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                count=len(vals_list),
                keys=sorted({key for vals in vals_list for key in vals}),
            )
        res = super().create(vals_list)
        if not res._defer_overtime(records=res):
            res._update_overtime()
        return res

    def write(self, vals):
        if (
            vals.get("employee_id")
            and vals["employee_id"] not in self.env.user.employee_ids.ids
            and not self.env.user.has_group("hr_attendance.group_hr_attendance_user")
            and self.env["hr.employee"]
            .sudo()
            .browse(vals["employee_id"])
            .attendance_manager_id.id
            != self.env.user.id
        ):
            raise AccessError(
                self.env._(
                    "Do not have access, user cannot edit the attendances that are not their own or if they are not the attendance manager of the employee."
                )
            )
        if self._OVERTIME_SOURCE_FIELDS.isdisjoint(vals):
            _debug.lifecycle(
                "write", attendances=self, keys=sorted(vals), overtime_source=False
            )
            return super().write(vals)
        _debug.lifecycle(
            "write", attendances=self, keys=sorted(vals), overtime_source=True
        )
        windows_before = self._overtime_windows()
        if self._defer_overtime(windows=windows_before, records=self):
            return super().write(vals)
        result = super().write(vals)
        self._update_overtime(windows_before)
        return result

    @_debug.perf.timed
    def unlink(self):
        _debug.lifecycle("unlink", attendances=self)
        windows = self._overtime_windows()
        self.linked_overtime_ids.unlink()
        deferred = self._defer_overtime(windows=windows)
        res = super().unlink()
        if not deferred:
            self.env["hr.attendance"]._update_overtime(windows)
        return res

    def copy(self, default=None):
        raise exceptions.UserError(self.env._("You cannot duplicate an attendance."))

    def _action_attendance_maps(self, side) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_url",
            "url": get_google_maps_url(
                self[f"{side}_latitude"], self[f"{side}_longitude"]
            ),
            "target": "new",
        }

    def action_in_attendance_maps(self):
        return self._action_attendance_maps("in")

    def action_out_attendance_maps(self):
        return self._action_attendance_maps("out")

    def get_kiosk_url(self):
        return (
            self.get_base_url()
            + "/hr_attendance/"
            + self.env.company.hr_attendance_config_id.attendance_kiosk_key
        )

    @api.model
    def has_demo_data(self) -> bool:
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_user"):
            return True
        demo_tag = self.env.ref(
            "hr_attendance.resource_calendar_std_38h", raise_if_not_found=False
        )
        return bool(demo_tag) or bool(
            self.env["ir.module.module"].search_count([("demo", "=", True)], limit=1)
        )

    def _load_demo_data(self) -> dict | None:
        if self.has_demo_data():
            _debug.logic("demo_data_skipped", reason="already_loaded")
            return None
        env_sudo = self.sudo().with_context({}).env
        env_sudo["hr.employee"]._load_scenario()
        convert.convert_file(
            env_sudo,
            "hr_attendance",
            "data/scenarios/hr_attendance_scenario.xml",
            None,
            mode="init",
        )
        self.env["hr.attendance"].create(demo.attendance_vals(env_sudo))
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def action_try_kiosk(self) -> dict:
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_user"):
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "message": self.env._(
                        "You don't have the rights to execute that action."
                    ),
                    "type": "info",
                },
            }
        return {
            "type": "ir.actions.act_url",
            "target": "self",
            "url": self.env.company.hr_attendance_config_id.attendance_kiosk_url
            + "?from_trial_mode=True",
        }

    def _read_group_employee_id(self, resources, domain):
        user_domain = Domain(self.env.context.get("user_domain") or Domain.TRUE)
        employee_domain = Domain(
            "company_id", "in", self.env.context.get("allowed_company_ids", [])
        )
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_user"):
            employee_domain &= Domain("attendance_manager_id", "=", self.env.user.id)
        if user_domain.is_true():
            if "gantt_start_date" in self.env.context:
                return self.env["hr.employee"].search(employee_domain)
            return resources & self.env["hr.employee"].search(employee_domain)
        else:
            employee_name_domain = Domain.OR(
                Domain("name", condition.operator, condition.value)
                for condition in user_domain.iter_conditions()
                if condition.field_expr == "employee_id"
            )
            return resources | self.env["hr.employee"].search(
                employee_name_domain & employee_domain
            )

    def _linked_overtimes(self):
        return self.linked_overtime_ids

    def action_approve_overtime(self) -> None:
        self.linked_overtime_ids.action_approve()

    def action_refuse_overtime(self) -> None:
        self.linked_overtime_ids.action_refuse()

    def _local_check_in(self):
        self.check_singleton()
        return self.check_in.replace(tzinfo=UTC).astimezone(self._schedule_tz())

    def _scheduled_hours_on(self, local_day):
        self.check_singleton()
        calendar = self._get_employee_calendar()
        tz = self._schedule_tz()
        return sum(
            calendar._get_hours_by_day(
                calendar._attendance_intervals_batch(
                    datetime.combine(local_day, time.min).replace(tzinfo=tz),
                    datetime.combine(local_day + timedelta(days=1), time.min).replace(
                        tzinfo=tz
                    ),
                    tz=tz,
                )[False]
            ).values()
        )

    _AUTO_CHECK_OUT_HORIZON_DAYS = 7

    def _worked_hours_spent_at(self, budget):
        self.check_singleton()
        tz = self._schedule_tz()
        cursor = self._local_check_in()
        floor = self.check_in + timedelta(seconds=1)
        spent = 0.0
        for _day in range(self._AUTO_CHECK_OUT_HORIZON_DAYS):
            day_end = datetime.combine(
                cursor.date() + timedelta(days=1), time.min
            ).replace(tzinfo=tz)
            for period_start, period_stop, _record in Intervals(
                [(cursor, day_end, self)]
            ) - self._lunch_intervals(cursor, day_end):
                hours = (period_stop - period_start).total_seconds() / 3600
                if spent + hours >= budget:
                    reached = period_start + timedelta(hours=budget - spent)
                    return max(reached.astimezone(UTC).replace(tzinfo=None), floor)
                spent += hours
            cursor = day_end.astimezone(tz)
        return max(cursor.astimezone(UTC).replace(tzinfo=None), floor)

    def _worked_hours_already_closed(self):
        totals = defaultdict(lambda: defaultdict(float))
        if not self:
            return totals
        earliest = min(self.mapped("check_in")).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=1)
        closed = self.env["hr.attendance"].search(
            [
                ("employee_id", "in", self.employee_id.ids),
                ("check_in", ">=", earliest),
                ("check_out", "!=", False),
            ]
        )
        for attendance in closed:
            totals[attendance.employee_id.id][attendance._local_check_in().date()] += (
                attendance.worked_hours
            )
        return totals

    @_debug.perf.timed
    def _cron_auto_check_out(self) -> None:
        self._cron_auto_check_out_tolerance()
        self._cron_auto_check_out_specific_time()

    def _cron_auto_check_out_tolerance(self) -> None:
        to_verify = self.env["hr.attendance"].search(
            [
                ("check_out", "=", False),
                (
                    "employee_id.company_id.hr_attendance_config_id.auto_check_out",
                    "=",
                    True,
                ),
                (
                    "employee_id.company_id.hr_attendance_config_id.auto_check_out_mode",
                    "=",
                    "tolerance",
                ),
                ("employee_id.resource_calendar_id.schedule_type", "=", "fully_fixed"),
            ]
        )

        _debug.lifecycle(
            "auto_check_out_sweep", mode="tolerance", to_verify=len(to_verify)
        )
        if not to_verify:
            return

        now = fields.Datetime.now()
        already_closed = to_verify._worked_hours_already_closed()
        closed = self.browse()
        with to_verify._deferring_overtime() as attendances:
            for attendance in attendances:
                employee = attendance.employee_id
                local_day = attendance._local_check_in().date()
                budget = (
                    attendance._scheduled_hours_on(local_day)
                    + employee.company_id.hr_attendance_config_id.auto_check_out_tolerance
                    - already_closed[employee.id][local_day]
                )
                worked = attendance._worked_hours_between(attendance.check_in, now)
                _debug.logic(
                    "auto_check_out_measured",
                    attendance=attendance,
                    worked_hours=worked,
                    budget_hours=budget,
                    day=local_day,
                    tz=attendance._schedule_tz(),
                )
                if worked <= budget:
                    continue
                check_out = attendance._worked_hours_spent_at(budget)
                _debug.lifecycle(
                    "auto_checked_out",
                    attendance=attendance,
                    mode="tolerance",
                    check_out=check_out,
                )
                attendance.write({"check_out": check_out, "out_mode": "auto_check_out"})
                closed |= attendance
        closed._log_cron_note(
            self.env._(
                "This attendance was automatically checked out because the employee exceeded the allowed time for their scheduled work hours."
            )
        )

    def _specific_time_cut_off(self):
        self.check_singleton()
        tz = self._schedule_tz()
        cut_off = datetime.combine(
            self._local_check_in().date(),
            float_to_time(
                self.employee_id.company_id.hr_attendance_config_id.auto_check_out_specific_time
            ),
        ).replace(tzinfo=tz)
        if cut_off <= self._local_check_in():
            cut_off += timedelta(days=1)
        return cut_off.astimezone(UTC).replace(tzinfo=None)

    def _cron_auto_check_out_specific_time(self) -> None:
        to_verify = self.env["hr.attendance"].search(
            [
                ("check_out", "=", False),
                (
                    "employee_id.company_id.hr_attendance_config_id.auto_check_out",
                    "=",
                    True,
                ),
                (
                    "employee_id.company_id.hr_attendance_config_id.auto_check_out_mode",
                    "=",
                    "specific_time",
                ),
            ]
        )

        _debug.lifecycle(
            "auto_check_out_sweep", mode="specific_time", to_verify=len(to_verify)
        )
        if not to_verify:
            return

        now = fields.Datetime.now()
        closed = self.browse()
        with to_verify._deferring_overtime() as attendances:
            for attendance in attendances:
                cut_off = attendance._specific_time_cut_off()
                _debug.logic(
                    "auto_check_out_cut_off",
                    attendance=attendance,
                    cut_off=cut_off,
                    tz=attendance._schedule_tz(),
                )
                if cut_off > now:
                    continue
                attendance.write({"check_out": cut_off, "out_mode": "auto_check_out"})
                closed |= attendance
        closed._log_cron_note(
            self.env._(
                "This attendance was automatically checked out because the employee did not check out before the company's check-out time."
            )
        )

    def _log_cron_note(self, body) -> None:
        if not self:
            return
        self._message_log_batch(dict.fromkeys(self.ids, body)).is_internal = False

    @_debug.perf.timed
    def _cron_absence_detection(self) -> None:
        yesterday = fields.Date.today() - relativedelta(days=1)
        companies = (
            self.env["hr_attendance.config"]
            .search([("absence_management", "=", True)])
            .company_id
        )
        _debug.lifecycle(
            "absence_detection_started", day=yesterday, companies=len(companies)
        )
        if not companies:
            return

        in_scope = Domain("employee_id.company_id", "in", companies.ids)
        checked_in_employees = (
            self.env["hr.attendance"]
            .search(in_scope & Domain("date", "=", yesterday))
            .employee_id
        )
        still_checked_in = (
            self.env["hr.attendance"]
            .search(in_scope & Domain("check_out", "=", False))
            .employee_id
        )

        technical_attendances_vals = []
        absent_employees = self.env["hr.employee"].search(
            [
                ("id", "not in", (checked_in_employees | still_checked_in).ids),
                ("company_id", "in", companies.ids),
                ("resource_calendar_id.schedule_type", "=", "fully_fixed"),
                ("current_version_id.contract_date_start", "<=", yesterday),
                "|",
                ("current_version_id.contract_date_end", "=", False),
                ("current_version_id.contract_date_end", ">=", yesterday),
            ]
        )

        for emp in absent_employees:
            local_day_start = datetime.combine(yesterday, time.min).replace(
                tzinfo=timezone(emp.sudo()._get_version(yesterday)._get_schedule_tz())
            )
            check_in = local_day_start.astimezone(UTC).replace(tzinfo=None)
            technical_attendances_vals.append(
                {
                    "check_in": check_in,
                    "check_out": check_in + relativedelta(seconds=1),
                    "in_mode": "technical",
                    "out_mode": "technical",
                    "employee_id": emp.id,
                }
            )

        _debug.lifecycle(
            "absence_markers_created", absent=len(technical_attendances_vals)
        )
        technical_attendances = self.create(technical_attendances_vals)
        to_unlink = technical_attendances.filtered(lambda a: a.overtime_hours == 0)
        _debug.logic(
            "absence_markers_dropped",
            dropped=len(to_unlink),
            markers=len(technical_attendances),
            reason="no_overtime",
        )
        kept = technical_attendances - to_unlink
        to_unlink.unlink()
        kept._log_cron_note(
            self.env._(
                "This attendance was automatically created to cover an unjustified absence on that day."
            )
        )

    def _get_localized_times(self) -> tuple:
        self.check_singleton()
        tz = self._schedule_tz()
        _debug.logic("localized_times", attendance=self, tz=tz)
        localized_start = (
            self.check_in.replace(tzinfo=UTC).astimezone(tz).replace(tzinfo=None)
        )
        localized_end = (
            self.check_out.replace(tzinfo=UTC).astimezone(tz).replace(tzinfo=None)
        )
        return localized_start, localized_end

    def _get_dates(self):
        result = {}
        for attendance in self:
            localized_start, localized_end = attendance._get_localized_times()
            result[attendance] = list(
                rrule(
                    DAILY,
                    dtstart=localized_start.date(),
                    until=last_day_of(localized_start, localized_end),
                )
            )
        return result

    def _get_attendance_by_periods_by_employee(self) -> dict:
        attendance_by_employee_by_day = defaultdict(
            lambda: defaultdict(lambda: Intervals([], keep_distinct=True))
        )
        attendance_by_employee_by_week = defaultdict(
            lambda: defaultdict(lambda: Intervals([], keep_distinct=True))
        )

        for attendance in self.sorted("check_in"):
            employee = attendance.employee_id
            check_in, check_out = attendance._get_localized_times()
            for day in rrule(
                dtstart=check_in.date(),
                until=last_day_of(check_in, check_out),
                freq=DAILY,
            ):
                week_date = day + relativedelta(days=6 - day.weekday())

                start_datetime = datetime.combine(day, time.min)
                stop_datetime_for_day = start_datetime + timedelta(days=1)
                day_interval = Intervals(
                    [
                        (
                            start_datetime,
                            stop_datetime_for_day,
                            self.env["resource.calendar"],
                        )
                    ]
                )

                stop_datetime_for_week = datetime.combine(
                    week_date + timedelta(days=1), time.min
                )
                week_interval = Intervals(
                    [
                        (
                            start_datetime,
                            stop_datetime_for_week,
                            self.env["resource.calendar"],
                        )
                    ]
                )

                attendance_interval = Intervals([(check_in, check_out, attendance)])
                attendance_by_employee_by_day[employee][day] |= (
                    attendance_interval & day_interval
                )
                attendance_by_employee_by_week[employee][week_date] |= (
                    attendance_interval & week_interval
                )

        return {
            "day": attendance_by_employee_by_day,
            "week": attendance_by_employee_by_week,
        }
