from collections import defaultdict
from datetime import UTC

from dateutil.relativedelta import MO, SU, relativedelta

from odoo import api, exceptions, fields, models
from odoo.fields import Domain
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals
from odoo.libs.numbers import float_round
from odoo.tools import consteq

_debug = DebugLog(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    attendance_manager_id = fields.Many2one(
        comodel_name="res.users",
        string="Attendance Approver",
        store=True,
        readonly=False,
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
        groups="hr_attendance.group_hr_attendance_officer",
        help="The user set in Attendance will access the attendance of the employee through the dedicated app and will be able to edit them.",
    )
    attendance_ids = fields.One2many(
        comodel_name="hr.attendance",
        inverse_name="employee_id",
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
    )
    last_attendance_id = fields.Many2one(
        comodel_name="hr.attendance",
        compute="_compute_last_attendance_id",
        store=True,
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
    )
    last_check_in = fields.Datetime(
        related="last_attendance_id.check_in",
        tracking=False,
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
    )
    last_check_out = fields.Datetime(
        related="last_attendance_id.check_out",
        tracking=False,
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
    )
    attendance_state = fields.Selection(
        selection=[("checked_out", "Checked out"), ("checked_in", "Checked in")],
        string="Attendance Status",
        compute="_compute_attendance_state",
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
    )
    hours_this_month = fields.Float(compute="_compute_hours_this_month")
    hours_this_month_overtime = fields.Float(compute="_compute_hours_this_month")
    hours_today = fields.Float(
        compute="_compute_hours_today",
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
    )
    hours_previously_today = fields.Float(
        compute="_compute_hours_today",
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
    )
    last_attendance_worked_hours = fields.Float(
        compute="_compute_hours_today",
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
    )
    hours_this_month_display = fields.Char(
        compute="_compute_hours_this_month",
        groups="hr.group_hr_user",
    )
    overtime_ids = fields.One2many(
        comodel_name="hr.attendance.overtime.line",
        inverse_name="employee_id",
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
    )
    total_overtime = fields.Float(
        compute="_compute_total_overtime",
        compute_sudo=True,
    )
    display_extra_hours = fields.Boolean(
        related="company_id.hr_attendance_config_id.hr_attendance_display_overtime"
    )

    attendance_pin_failure_count = fields.Integer(
        default=0,
        copy=False,
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
    )
    attendance_pin_retry_after = fields.Datetime(
        copy=False,
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
    )

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        for employee, vals in zip(employees, vals_list, strict=True):
            if vals.get("attendance_manager_id"):
                employee._grant_attendance_officer(
                    self.env["res.users"].browse(vals["attendance_manager_id"])
                )
        return employees

    def _grant_attendance_officer(self, users) -> None:
        officer_group = self.env.ref(
            "hr_attendance.group_hr_attendance_officer", raise_if_not_found=False
        )
        if officer_group:
            self.env["res.users.grant"].with_privilege(
                "hr_attendance.privilege_grant_attendance_officer",
                reason="attendance manager of an employee",
            )._grant(users, officer_group, cause="automation", cause_ref=self)

    def write(self, vals):
        old_officers = self.env["res.users"]
        if "attendance_manager_id" in vals:
            old_officers = self.attendance_manager_id
            if vals["attendance_manager_id"]:
                officer = self.env["res.users"].browse(vals["attendance_manager_id"])
                if not officer.has_group("hr_attendance.group_hr_attendance_officer"):
                    self[:1]._grant_attendance_officer(officer)

        res = super().write(vals)
        if old_officers:
            old_officers.sudo()._clean_attendance_officers()
        return res

    def action_archive(self):
        res = super().action_archive()
        open_attendances = (
            self.env["hr.attendance"]
            .sudo()
            .search(
                [
                    ("employee_id", "in", self.ids),
                    ("check_out", "=", False),
                ]
            )
        )
        if open_attendances:
            open_attendances.write({"check_out": fields.Datetime.now()})
        return res

    @api.depends("overtime_ids.manual_duration", "overtime_ids", "overtime_ids.status")
    def _compute_total_overtime(self) -> None:
        mapped_validated_overtimes = dict(
            self.env["hr.attendance.overtime.line"]._read_group(
                domain=[("status", "=", "approved"), ("employee_id", "in", self.ids)],
                groupby=["employee_id"],
                aggregates=["manual_duration:sum"],
            )
        )

        for employee in self:
            employee.total_overtime = mapped_validated_overtimes.get(employee, 0)

    @api.depends(
        "attendance_ids.worked_hours",
        "attendance_ids.validated_overtime_hours",
        "attendance_ids.check_in",
        "attendance_ids.check_out",
        "tz",
    )
    def _compute_hours_this_month(self) -> None:
        now = fields.Datetime.now()
        now_utc = now.replace(tzinfo=UTC)
        totals = {}
        for tz_name, employees in self.grouped(lambda e: e.tz or "UTC").items():
            now_tz = now_utc.astimezone(timezone(tz_name))
            start_naive = (
                now_tz.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                .astimezone(UTC)
                .replace(tzinfo=None)
            )
            grouped = self.env["hr.attendance"]._read_group(  # noqa: E8507 -- one query per timezone; employees sharing one were merged above
                domain=[
                    ("employee_id", "in", employees.ids),
                    ("check_in", ">=", start_naive),
                    ("check_out", "<=", now),
                ],
                groupby=["employee_id"],
                aggregates=["worked_hours:sum", "validated_overtime_hours:sum"],
            )
            totals.update(
                {
                    employee.id: (worked, overtime)
                    for employee, worked, overtime in grouped
                }
            )
        for employee in self:
            worked, overtime = totals.get(employee.id, (0.0, 0.0))
            employee.hours_this_month = round(worked, 2)
            employee.hours_this_month_display = "%g" % employee.hours_this_month
            employee.hours_this_month_overtime = round(overtime, 2)

    @api.depends("attendance_ids.check_in", "attendance_ids.check_out", "tz")
    def _compute_hours_today(self) -> None:
        now = fields.Datetime.now()
        now_utc = now.replace(tzinfo=UTC)
        by_tz = self.grouped("tz")
        if _debug.logic.enabled:
            _debug.logic(
                "hours_today_grouped",
                employees=self,
                tz_groups=len(by_tz),
                tzs=",".join(sorted(map(repr, by_tz))),
            )
        for tz_name, employees in by_tz.items():
            start_tz = now_utc.astimezone(timezone(tz_name)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            start_naive = start_tz.astimezone(UTC).replace(tzinfo=None)

            attendances = self.env["hr.attendance"].search(  # noqa: E8507 -- loop is over timezones, not records
                [
                    ("employee_id", "in", employees.ids),
                    ("check_in", "<=", now),
                    "|",
                    ("check_out", ">=", start_naive),
                    ("check_out", "=", False),
                ],
                order="check_in asc",
            )
            per_employee = attendances.grouped("employee_id")
            for employee in employees:
                hours_previously_today = 0
                worked_hours = 0
                attendance_worked_hours = 0
                for attendance in per_employee.get(employee, attendances.browse()):
                    delta = (attendance.check_out or now) - max(
                        attendance.check_in, start_naive
                    )
                    attendance_worked_hours = delta.total_seconds() / 3600.0
                    worked_hours += attendance_worked_hours
                    hours_previously_today += attendance_worked_hours
                employee.last_attendance_worked_hours = attendance_worked_hours
                hours_previously_today -= attendance_worked_hours
                employee.hours_previously_today = hours_previously_today
                employee.hours_today = worked_hours

    @api.depends("attendance_ids.check_in")
    def _compute_last_attendance_id(self) -> None:
        Attendance = self.env["hr.attendance"]
        self.last_attendance_id = False
        if not self:
            return
        latest = Attendance._read_group(
            [("employee_id", "in", self.ids)],
            groupby=["employee_id"],
            aggregates=["check_in:max"],
        )
        if not latest:
            return
        domain = Domain.OR(
            [
                Domain("employee_id", "=", employee.id)
                & Domain("check_in", "=", check_in)
                for employee, check_in in latest
            ]
        )
        by_employee = {}
        for attendance in Attendance.search(domain, order="id"):
            by_employee[attendance.employee_id.id] = attendance
        for employee in self:
            employee.last_attendance_id = by_employee.get(employee.id, False)

    @api.depends(
        "last_attendance_id.check_in",
        "last_attendance_id.check_out",
        "last_attendance_id",
    )
    def _compute_attendance_state(self) -> None:
        for employee in self:
            att = employee.last_attendance_id.sudo()
            employee.attendance_state = (
                att and not att.check_out and "checked_in"
            ) or "checked_out"

    _PIN_FAILURES_BEFORE_THROTTLE = 3
    _PIN_MAX_RETRY_DELAY = 60

    def _attendance_pin_retry_delay(self):
        self.check_singleton()
        over = self.attendance_pin_failure_count - self._PIN_FAILURES_BEFORE_THROTTLE
        if over < 1:
            return 0
        return min(2**over, self._PIN_MAX_RETRY_DELAY)

    def _check_attendance_pin(self, pin_code) -> bool:
        self.check_singleton()
        employee = self.sudo()
        now = fields.Datetime.now()
        locked = (
            employee.attendance_pin_retry_after
            and now < employee.attendance_pin_retry_after
        )
        _debug.logic(
            "pin_check",
            employee=self,
            failures=employee.attendance_pin_failure_count,
            locked=bool(locked),
            retry_after=employee.attendance_pin_retry_after,
        )
        if not locked and pin_code and consteq(str(pin_code), employee.pin):
            if employee.attendance_pin_failure_count:
                employee.write(
                    {
                        "attendance_pin_failure_count": 0,
                        "attendance_pin_retry_after": False,
                    }
                )
            _debug.logic("pin_accepted", employee=self)
            return True
        employee.attendance_pin_failure_count += 1
        delay = employee._attendance_pin_retry_delay()
        _debug.logic(
            "pin_rejected",
            employee=self,
            failures=employee.attendance_pin_failure_count,
            delay_s=delay,
        )
        employee.attendance_pin_retry_after = (
            now + relativedelta(seconds=delay) if delay else False
        )
        return False

    def _attendance_action_change(self, geo_information=None):
        self.check_singleton()
        employee = self.sudo()
        action_date = fields.Datetime.now()
        geo_information = geo_information or {}
        _debug.pipeline(
            "attendance_action_change",
            employee=self.id,
            at=action_date,
            state=employee.attendance_state,
            geo_keys=sorted(geo_information),
        )
        if employee.attendance_state != "checked_in":
            attendance = employee.env["hr.attendance"].create(
                {
                    "employee_id": self.id,
                    "check_in": action_date,
                    **{f"in_{key}": value for key, value in geo_information.items()},
                }
            )
            return attendance.with_env(self.env)
        attendance = employee.env["hr.attendance"].search(
            [("employee_id", "=", self.id), ("check_out", "=", False)], limit=1
        )
        if not attendance:
            raise exceptions.UserError(
                self.env._(
                    "Cannot perform check out on %(empl_name)s, could not find corresponding check in. "
                    "Your attendances have probably been modified manually by human resources.",
                    empl_name=employee.name,
                )
            )
        attendance.write(
            {
                "check_out": action_date,
                **{f"out_{key}": value for key, value in geo_information.items()},
            }
        )
        return attendance.with_env(self.env)

    def _get_attendance_systray_data(self) -> dict:
        if not self:
            return {}
        employee = self.sudo()
        return {
            "id": employee.id,
            "hours_today": float_round(employee.hours_today, precision_digits=2),
            "hours_previously_today": float_round(
                employee.hours_previously_today, precision_digits=2
            ),
            "last_attendance_worked_hours": float_round(
                employee.last_attendance_worked_hours, precision_digits=2
            ),
            "last_check_in": employee.last_check_in,
            "attendance_state": employee.attendance_state,
            "display_systray": employee.company_id.hr_attendance_config_id.attendance_from_systray,
            "device_tracking_enabled": employee.company_id.hr_attendance_config_id.attendance_device_tracking,
        }

    @_debug.perf.timed
    def _round_overtime_window(self, first, last) -> tuple:
        self.check_singleton()
        rules = self.sudo().version_ids.ruleset_id.rule_ids
        if any(
            rule.base_off == "quantity" and rule.quantity_period == "week"
            for rule in rules
        ):
            _debug.logic(
                "overtime_window_widened",
                employee=self,
                first=first,
                last=last,
                to="whole_weeks",
            )
            return (
                first + relativedelta(weekday=MO(-1)),
                last + relativedelta(weekday=SU),
            )
        return first, last

    def action_view_this_month_attendances(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Attendances This Month"),
            "res_model": "hr.attendance",
            "views": [
                [
                    self.env.ref(
                        "hr_attendance.hr_attendance_employee_simple_tree_view"
                    ).id,
                    "list",
                ]
            ],
            "context": {
                "create": 0,
                "search_default_check_in_filter": 1,
                "employee_id": self.id,
                "display_extra_hours": self.display_extra_hours,
            },
            "domain": [("employee_id", "=", self.id)],
        }

    @api.depends("user_id.im_status", "attendance_state")
    def _compute_hr_presence_state(self) -> None:
        super()._compute_hr_presence_state()
        attendance_state = {
            employee.id: employee.attendance_state for employee in self.sudo()
        }
        expected_but_out = self.filtered(
            lambda employee: (
                attendance_state[employee.id] == "checked_out"
                and employee.hr_presence_state == "out_of_working_hour"
            )
        )
        working_now = set(expected_but_out._get_employee_ids_working_now())
        for employee in self:
            if attendance_state[employee.id] == "checked_in":
                employee.hr_presence_state = "present"
            elif (
                employee.id in working_now
                and employee.company_id.hr_config_id.hr_presence_control_attendance
            ):
                employee.hr_presence_state = "absent"

    def _compute_presence_icon(self):
        res = super()._compute_presence_icon()
        for employee in self:
            employee.show_hr_icon_display = (
                employee.company_id.hr_config_id.hr_presence_control_attendance
                or bool(employee.user_id)
            )
        return res

    def open_barcode_scanner(self) -> dict:
        return {
            "type": "ir.actions.client",
            "tag": "employee_barcode_scanner",
            "name": "Badge Scanner",
        }

    def _get_schedules_by_employee_by_work_type(
        self, start, stop, version_periods_by_employee
    ):
        employees_by_calendar = defaultdict(lambda: self.env["hr.employee"])
        leave_intervals_by_cal_by_resource = defaultdict(lambda: defaultdict(Intervals))
        attendance_intervals_by_cal = defaultdict(Intervals)
        lunch_intervals_by_cal = defaultdict(Intervals)

        for employee, intervals in version_periods_by_employee.items():
            for _start, _stop, version in intervals:
                employees_by_calendar[version.resource_calendar_id] |= employee

        for cal, employees in employees_by_calendar.items():
            if cal.schedule_type == "fully_flexible":
                continue
            cal_leave_intervals_by_resource = cal._leave_intervals_batch(
                start,
                stop,
                resources=employees.resource_id,
            )
            for resource, leave_intervals in cal_leave_intervals_by_resource.items():
                naive_leave_intervals = Intervals(
                    [
                        (
                            i_start.replace(tzinfo=None),
                            i_stop.replace(tzinfo=None),
                            i_model,
                        )
                        for (i_start, i_stop, i_model) in leave_intervals
                    ]
                )
                leave_intervals_by_cal_by_resource[cal][resource] = (
                    naive_leave_intervals
                )

            cal_attendance_intervals = cal._attendance_intervals_batch(
                start,
                stop,
            )[False]
            attendance_intervals_by_cal[cal] = Intervals(
                [
                    (i_start.replace(tzinfo=None), i_stop.replace(tzinfo=None), i_model)
                    for (i_start, i_stop, i_model) in cal_attendance_intervals
                ]
            )

            cal_lunch_intervals = cal._attendance_intervals_batch(
                start, stop, lunch=True
            )[False]
            lunch_intervals_by_cal[cal] = Intervals(
                [
                    (i_start.replace(tzinfo=None), i_stop.replace(tzinfo=None), i_model)
                    for (i_start, i_stop, i_model) in cal_lunch_intervals
                ]
            )

        full_schedule_by_employee = {
            "leave": defaultdict(Intervals),
            "schedule": defaultdict(
                lambda: {
                    "work": Intervals([]),
                    "lunch": Intervals([]),
                }
            ),
            "fully_flexible": defaultdict(Intervals),
        }
        for employee, intervals in version_periods_by_employee.items():
            for p_start, p_stop, version in intervals:
                interval = Intervals(
                    [
                        (
                            p_start.replace(tzinfo=None),
                            p_stop.replace(tzinfo=None),
                            self.env["resource.calendar"],
                        )
                    ]
                )
                calendar = version.resource_calendar_id
                if calendar.schedule_type == "fully_flexible":
                    full_schedule_by_employee["fully_flexible"][employee] |= interval
                    continue
                employee_leaves = leave_intervals_by_cal_by_resource[calendar][
                    employee.resource_id.id
                ]
                full_schedule_by_employee["leave"][employee] |= (
                    employee_leaves & interval
                )
                employee_attendances = attendance_intervals_by_cal[calendar]
                full_schedule_by_employee["schedule"][employee]["work"] |= (
                    employee_attendances & interval
                )
                employee_lunches = lunch_intervals_by_cal[calendar]
                full_schedule_by_employee["schedule"][employee]["lunch"] |= (
                    employee_lunches & interval
                )

        return full_schedule_by_employee
