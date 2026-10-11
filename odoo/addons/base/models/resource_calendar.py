from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any, NamedTuple, Self
from zoneinfo import ZoneInfo

from dateutil.rrule import DAILY, rrule

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.libs.datetime import elapsed_hours, timezone, wall_at
from odoo.libs.intervals import Intervals
from odoo.libs.numbers import float_round
from odoo.models import ValuesType
from odoo.tools import SQL, date_utils, float_compare
from odoo.tools.date_utils import localized, to_timezone

from .resource_utils import (
    HOURS_PER_DAY,
    fill_week,
    hours_by_day,
    last_day_of,
    split_at_midnight,
    week_of,
    week_type_of,
)
from odoo.addons.base.models.res_partner import _selection_timezones

if TYPE_CHECKING:
    from .resource_calendar_attendance import ResourceCalendarAttendance
    from .resource_resource import ResourceResource


class DummyAttendance(NamedTuple):
    hour_from: float
    hour_to: float
    dayofweek: str
    day_period: str | None
    week_type: str | None


_PLAN_WINDOW = timedelta(days=14)
_RATE_CONDITIONS = {
    "<": lambda rate, value: SQL("%s < %s", rate, value),
    ">": lambda rate, value: SQL("%s > %s", rate, value),
    "<=": lambda rate, value: SQL("%s <= %s", rate, value),
    ">=": lambda rate, value: SQL("%s >= %s", rate, value),
    "=": lambda rate, value: SQL("%s = %s", rate, value),
    "!=": lambda rate, value: SQL("%s != %s", rate, value),
    "in": lambda rate, values: SQL("%s = ANY(%s)", rate, values),
    "not in": lambda rate, values: SQL("%s != ALL(%s)", rate, values),
}
_PLAN_MAX_ITERATIONS = 100


class ResourceCalendar(models.Model):
    _name = "resource.calendar"
    _description = "Resource Working Time"

    name = fields.Char(required=True)
    active = fields.Boolean(
        default=True,
        help="If the active field is set to false, it will allow you to hide the Working Time without removing it.",
    )
    attendance_ids = fields.One2many(
        comodel_name="resource.calendar.attendance",
        inverse_name="calendar_id",
        string="Working Time",
        compute="_compute_attendance_ids",
        store=True,
        copy=True,
        readonly=False,
    )
    attendance_ids_1st_week = fields.One2many(
        comodel_name="resource.calendar.attendance",
        inverse_name="calendar_id",
        string="Working Time 1st Week",
        compute="_compute_two_weeks_attendance",
        inverse="_inverse_two_weeks_calendar",
    )
    attendance_ids_2nd_week = fields.One2many(
        comodel_name="resource.calendar.attendance",
        inverse_name="calendar_id",
        string="Working Time 2nd Week",
        compute="_compute_two_weeks_attendance",
        inverse="_inverse_two_weeks_calendar",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index="btree_not_null",
        domain=lambda self: [("id", "in", self.env.companies.ids)],
    )
    leave_ids = fields.One2many(
        comodel_name="resource.schedule.exception",
        inverse_name="calendar_id",
        string="Time Off",
    )
    resource_ids = fields.One2many(
        comodel_name="resource.resource",
        inverse_name="calendar_id",
        string="Work Resources",
    )
    schedule_type = fields.Selection(
        selection=[
            ("fully_fixed", "Fully Fixed"),
            ("flexible", "Flexible"),
            ("fully_flexible", "Fully Flexible"),
        ],
        default="fully_fixed",
        required=True,
        help="How the schedule defines working time:\n"
        "- Fully Fixed: the days, periods and hours of each day.\n"
        "- Flexible: an amount of hours to work in the week.\n"
        "- Fully Flexible: any hour; a day of work counts its hours per day.",
    )
    duration_based = fields.Boolean(
        string="Attendance based on duration",
        help="The hours will be centered around 12:00 to cover the duration for the day",
    )
    full_time_required_hours = fields.Float(
        string="Full Time Equivalent",
        compute="_compute_full_time_required_hours",
        store=True,
        readonly=False,
        help="Number of hours to work on the company schedule to be considered as fulltime.",
    )
    global_leave_ids = fields.One2many(
        comodel_name="resource.schedule.exception",
        inverse_name="calendar_id",
        string="Global Time Off",
        copy=True,
        domain=[("resource_id", "=", False)],
    )
    hours_per_day = fields.Float(
        string="Average Hour per Day",
        digits=(2, 2),
        compute="_compute_hours_per_day",
        store=True,
        readonly=False,
        help="Average hours per day a resource is supposed to work with this calendar.",
    )
    hours_per_week = fields.Float(
        string="Hours per Week",
        compute="_compute_hours_per_week",
        store=True,
        copy=False,
        readonly=False,
    )
    is_fulltime = fields.Boolean(
        string="Is Full Time",
        compute="_compute_work_time",
    )
    two_weeks_calendar = fields.Boolean(string="Calendar in 2 weeks mode")
    two_weeks_explanation = fields.Char(
        string="Explanation",
        compute="_compute_two_weeks_explanation",
    )

    tz = fields.Selection(
        selection=_selection_timezones,
        string="Timezone",
        default=lambda self: self._default_tz(),
        help="The time zone of this schedule's company-level uses: the company working hours, and the public holidays and closures entered on it. A resource working this schedule reads its hours in the resource's own time zone, so one 08:00-17:00 schedule means 08:00-17:00 local time for employees deployed in other zones.",
    )
    tz_offset = fields.Char(
        string="Timezone offset",
        compute="_compute_tz_offset",
    )
    work_resources_count = fields.Integer(
        string="Work Resources count",
        compute="_compute_work_resources_count",
    )
    work_time_rate = fields.Float(
        compute="_compute_work_time",
        search="_search_work_time_rate",
        help="Work time rate versus full time working schedule, should be between 0 and 100 %.",
    )

    @api.constrains("tz", "schedule_type")
    def _check_tz(self) -> None:
        if missing := self.filtered(
            lambda c: not c.tz and c.schedule_type != "fully_flexible"
        ):
            raise ValidationError(
                self.env._(
                    "%(names)s: a schedule with working hours needs a time zone.",
                    names=", ".join(missing.mapped("name")),
                )
            )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_fully_flexible(self) -> None:
        if self._get_fully_flexible_calendar() in self:
            raise UserError(
                self.env._(
                    "The Fully Flexible schedule is what an empty schedule means; "
                    "it cannot be deleted."
                )
            )

    @api.constrains("schedule_type", "tz", "company_id", "active")
    def _check_the_fully_flexible_schedule_stays_shared(self) -> None:
        shared = self.env.ref(
            "base.resource_calendar_fully_flexible", raise_if_not_found=False
        )
        if not shared or shared not in self:
            return
        if (
            shared.schedule_type != "fully_flexible"
            or shared.tz
            or shared.company_id
            or not shared.active
        ):
            raise ValidationError(
                self.env._(
                    "The Fully Flexible schedule is what an empty schedule means "
                    "for every company: it stays fully flexible, active, without "
                    "a company or a time zone of its own."
                )
            )

    @api.constrains(
        "attendance_ids", "two_weeks_calendar", "duration_based", "schedule_type"
    )
    def _check_attendance_ids(self) -> None:
        for calendar in self:
            if calendar.schedule_type != "fully_fixed" and calendar.attendance_ids:
                raise ValidationError(
                    self.env._(
                        "%(name)s: only a schedule of fixed hours has working "
                        "hours lines; a flexible one is read from its daily and "
                        "weekly hours.",
                        name=calendar.name,
                    )
                )
            lines = calendar.attendance_ids.filtered(
                lambda attendance: not attendance.display_type
            )
            breaks = lines.filtered(lambda attendance: attendance.day_period == "lunch")
            if calendar.duration_based and breaks:
                raise ValidationError(
                    self.env._(
                        "%(names)s: a duration-based schedule has no breaks.",
                        names=", ".join(breaks.mapped("name")),
                    )
                )
            if not calendar.two_weeks_calendar:
                calendar._check_overlap(lines)
                continue
            sections = calendar.attendance_ids - lines
            if (
                sections
                and not calendar.attendance_ids.sorted("sequence")[0].display_type
            ):
                raise ValidationError(
                    self.env._(
                        "In a calendar with 2 weeks mode, all periods need to be in the sections."
                    )
                )
            if orphans := calendar.attendance_ids.filtered(
                lambda attendance: not attendance.week_type
            ):
                raise ValidationError(
                    self.env._(
                        "%(names)s: a line on a 2 weeks calendar must belong"
                        " to the first or the second week.",
                        names=", ".join(orphans.mapped("name")),
                    )
                )
            for week_lines in lines.grouped("week_type").values():
                calendar._check_overlap(week_lines)

    @api.model
    def default_get(self, fields: list[str]) -> dict[str, Any]:
        res = super().default_get(fields)
        if not res.get("name") and res.get("company_id"):
            res["name"] = self.env._(
                "Working Hours of %s",
                self.env["res.company"].browse(res["company_id"]).name,
            )
        company = self.env["res.company"].browse(
            res.get("company_id", self.env.company.id)
        )
        if "attendance_ids" in fields and not res.get("attendance_ids"):
            res["attendance_ids"] = self._prepare_default_attendance_commands(company)
            res["two_weeks_calendar"] = company.resource_calendar_id.two_weeks_calendar
        return res

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        for vals in vals_list:
            if vals.get("schedule_type", "fully_fixed") != "fully_fixed":
                vals.setdefault("attendance_ids", [])
        return super().create(vals_list)

    def _get_tz(self, resource=None) -> str:
        return (resource and resource.tz) or self.tz or self._default_tz()

    def _default_tz(self):
        admin = self.env.ref("base.user_admin", raise_if_not_found=False)
        return (
            self.env.context.get("tz")
            or self.env.user.tz
            or (admin and admin.tz)
            or "UTC"
        )

    def write(self, vals: ValuesType) -> bool:
        result = super().write(vals)
        if self._get_fields_schedule().intersection(vals):
            self._recompute_reservation_hours()
        return result

    @api.model
    def _get_fields_schedule(self) -> frozenset[str]:
        return frozenset(
            {
                "two_weeks_calendar",
                "duration_based",
                "schedule_type",
                "hours_per_day",
                "hours_per_week",
                "tz",
            }
        )

    def _recompute_reservation_hours(self) -> None:
        if self:
            self.env["resource.reservation"]._recompute_allocated_hours(
                Domain("resource_calendar_id", "in", self.ids)
                & Domain("date_end", ">", fields.Datetime.now())
            )

    def copy_data(self, default: ValuesType | None = None) -> list[ValuesType]:
        vals_list = super().copy_data(default=default)
        new_lines = "attendance_ids" in (default or {})
        for calendar, vals in zip(self, vals_list, strict=True):
            if "name" not in (default or {}):
                vals["name"] = self.env._("%s (copy)", calendar.name)
            if calendar.schedule_type != "fully_fixed":
                vals.setdefault("hours_per_week", calendar.hours_per_week)
            elif new_lines and "hours_per_day" not in default:
                vals.pop("hours_per_day", None)
        return vals_list

    @api.depends("two_weeks_calendar", "attendance_ids.week_type")
    def _compute_two_weeks_attendance(self) -> None:
        for calendar in self:
            if not calendar.two_weeks_calendar:
                calendar.attendance_ids_1st_week = False
                calendar.attendance_ids_2nd_week = False
                continue
            calendar.attendance_ids_1st_week = calendar.attendance_ids.filtered(
                lambda a: a.week_type == "0"
            )
            calendar.attendance_ids_2nd_week = calendar.attendance_ids.filtered(
                lambda a: a.week_type == "1"
            )

    @api.depends("company_id")
    def _compute_full_time_required_hours(self) -> None:
        for calendar in self.filtered("company_id"):
            calendar.full_time_required_hours = (
                calendar.company_id.resource_calendar_id.full_time_required_hours
                or calendar.company_id.resource_calendar_id.hours_per_week
            )

    @api.depends("company_id", "schedule_type")
    def _compute_attendance_ids(self) -> None:
        self.filtered(
            lambda c: c.schedule_type != "fully_fixed" and c.attendance_ids
        ).attendance_ids = [Command.clear()]
        for calendar in self.filtered(
            lambda c: (
                c.schedule_type == "fully_fixed"
                and (
                    not c._origin
                    or not c.attendance_ids
                    or (c._origin.company_id != c.company_id and c.company_id)
                )
            )
        ):
            company_calendar = calendar.company_id.resource_calendar_id
            calendar.update(
                {
                    "two_weeks_calendar": company_calendar.two_weeks_calendar,
                    "tz": company_calendar.tz,
                    "attendance_ids": [Command.clear()]
                    + [
                        Command.create(attendance._copy_attendance_vals())
                        for attendance in company_calendar.attendance_ids
                    ],
                }
            )

    @api.depends(
        "attendance_ids",
        "attendance_ids.hour_from",
        "attendance_ids.hour_to",
        "attendance_ids.duration_hours",
        "attendance_ids.day_period",
        "attendance_ids.display_type",
        "attendance_ids.dayofweek",
        "attendance_ids.week_type",
        "duration_based",
        "two_weeks_calendar",
        "schedule_type",
    )
    def _compute_hours_per_day(self) -> None:
        for calendar in self.filtered(lambda c: c.schedule_type == "fully_fixed"):
            calendar.hours_per_day = float_round(
                calendar._get_hours_per_day(), precision_digits=2
            )

    @api.depends(
        "attendance_ids",
        "attendance_ids.hour_from",
        "attendance_ids.hour_to",
        "attendance_ids.duration_hours",
        "attendance_ids.day_period",
        "attendance_ids.display_type",
        "duration_based",
        "two_weeks_calendar",
        "schedule_type",
    )
    def _compute_hours_per_week(self) -> None:
        for calendar in self.filtered(lambda c: c.schedule_type == "fully_fixed"):
            calendar.hours_per_week = float_round(
                calendar._get_hours_per_week(), precision_digits=2
            )

    def _compute_two_weeks_explanation(self) -> None:
        today = fields.Date.context_today(self)
        week_type_str = (
            self.env._("the second")
            if week_type_of(today) == "1"
            else self.env._("the first")
        )
        first_day = date_utils.start_of(today, "week")
        last_day = date_utils.end_of(today, "week")
        explanation = self.env._(
            "The current week (from %(first_day)s to %(last_day)s) is %(number)s week.",
            first_day=first_day,
            last_day=last_day,
            number=week_type_str,
        )
        for calendar in self:
            calendar.two_weeks_explanation = explanation

    @api.depends("tz")
    def _compute_tz_offset(self) -> None:
        for calendar in self:
            calendar.tz_offset = datetime.now(timezone(calendar._get_tz())).strftime(
                "%z"
            )

    @api.depends("resource_ids")
    def _compute_work_resources_count(self) -> None:
        resources_per_calendar = dict(
            self.env["resource.resource"]._read_group(
                domain=[("calendar_id", "in", self.ids)],
                groupby=["calendar_id"],
                aggregates=["__count"],
            )
        )
        for calendar in self:
            calendar.work_resources_count = resources_per_calendar.get(calendar, 0)

    @api.depends("hours_per_week", "full_time_required_hours")
    def _compute_work_time(self) -> None:
        for calendar in self:
            if calendar.full_time_required_hours:
                calendar.work_time_rate = (
                    calendar.hours_per_week / calendar.full_time_required_hours * 100
                )
            else:
                calendar.work_time_rate = 100

            calendar.is_fulltime = (
                float_compare(
                    calendar.full_time_required_hours, calendar.hours_per_week, 3
                )
                == 0
            )

    def _inverse_two_weeks_calendar(self) -> None:
        for calendar in self:
            if not calendar.two_weeks_calendar:
                continue
            calendar.attendance_ids = (
                calendar.attendance_ids_1st_week + calendar.attendance_ids_2nd_week
            )

    @api.model
    def _search_work_time_rate(self, operator, value):
        values = list(value) if operator in ("in", "not in") else [value]
        if operator not in _RATE_CONDITIONS or not all(
            isinstance(v, int | float) for v in values
        ):
            return NotImplemented
        values = [float(v) for v in values]

        def to_sql(model, alias, query):
            hours = model._field_to_sql(alias, "hours_per_week", query)
            full_time = model._field_to_sql(alias, "full_time_required_hours", query)
            rate = SQL(
                "(CASE WHEN COALESCE(%s, 0) > 0 THEN COALESCE(%s, 0) / %s * 100"
                " ELSE 100 END)",
                full_time,
                hours,
                full_time,
            )
            if operator in ("in", "not in"):
                return _RATE_CONDITIONS[operator](rate, values)
            return _RATE_CONDITIONS[operator](rate, values[0])

        return Domain.custom(to_sql=to_sql)

    @api.onchange("attendance_ids")
    def _onchange_attendance_ids(self) -> None:
        if not self.two_weeks_calendar:
            return

        even_week_seq = self.attendance_ids.filtered(
            lambda att: att.display_type == "line_section" and att.week_type == "0"
        )
        odd_week_seq = self.attendance_ids.filtered(
            lambda att: att.display_type == "line_section" and att.week_type == "1"
        )
        if len(even_week_seq) != 1 or len(odd_week_seq) != 1:
            raise ValidationError(self.env._("You can't delete section between weeks."))

        even_week_seq = even_week_seq.sequence
        odd_week_seq = odd_week_seq.sequence

        for line in self.attendance_ids.filtered(lambda att: att.display_type is False):
            if even_week_seq > odd_week_seq:
                line.week_type = "1" if even_week_seq > line.sequence else "0"
            else:
                line.week_type = "0" if odd_week_seq > line.sequence else "1"

    def action_switch_two_weeks(self) -> None:
        self.check_singleton()
        if not self.two_weeks_calendar:
            self.write(
                {
                    "two_weeks_calendar": True,
                    "attendance_ids": [Command.clear()]
                    + self._prepare_two_weeks_attendance_commands(),
                }
            )
        else:
            self.write(
                {
                    "two_weeks_calendar": False,
                    "duration_based": False,
                    "attendance_ids": [Command.clear()]
                    + [
                        Command.create(vals)
                        for vals in self._get_single_week_attendance_vals(
                            self._prepare_default_attendance_vals(self.company_id)
                        )
                    ],
                }
            )

    def action_switch_duration_based(self) -> None:
        self.check_singleton()
        if not self.duration_based:
            self.attendance_ids.filtered(lambda att: att.day_period == "lunch").unlink()
            self.duration_based = True
            return
        self.duration_based = False
        default_vals = self._get_single_week_attendance_vals(
            self._prepare_default_attendance_vals(self.company_id)
        )
        if self.two_weeks_calendar:
            commands = self._prepare_two_weeks_attendance_commands(default_vals)
        else:
            commands = [Command.create(vals) for vals in default_vals]
        self.attendance_ids = [Command.clear()] + commands

    def _new_virtual_attendance(self, hours, days):
        return self.env["resource.calendar.attendance"].new(
            {"duration_hours": hours, "duration_days": days}
        )

    def _get_fully_flexible_intervals(self, start_datetime, end_datetime, tz):
        self.check_singleton()
        expected_day_hours = self.hours_per_day or HOURS_PER_DAY
        intervals = []
        day = start_datetime.date()
        last_day = (end_datetime - timedelta(microseconds=1)).date()
        while day <= last_day:
            midnight = datetime.combine(day, time.min).replace(tzinfo=tz)
            next_midnight = datetime.combine(day + timedelta(days=1), time.min).replace(
                tzinfo=tz
            )
            day_start = max(start_datetime, midnight)
            day_end = min(end_datetime, next_midnight)
            if day_end > day_start:
                covered_hours = elapsed_hours(day_start, day_end)
                intervals.append(
                    (
                        day_start,
                        day_end,
                        self._new_virtual_attendance(
                            covered_hours,
                            min(1.0, covered_hours / expected_day_hours),
                        ),
                    )
                )
            day += timedelta(days=1)
        return intervals

    @staticmethod
    def _center_block_on_noon(day, hours, tz, free) -> tuple | None:
        noon = datetime.combine(day, time(12, 0)).replace(tzinfo=tz)
        spans = [(start, stop) for start, stop, _meta in free]
        if not spans:
            return None
        span = next(
            (
                (start, stop)
                for start, stop in spans
                if start <= noon <= stop
                and (stop - start).total_seconds() >= hours * 3600
            ),
            max(spans, key=lambda span: span[1] - span[0]),
        )
        lower, upper = span
        length = min(timedelta(hours=hours), upper - lower)
        start_time = min(max(noon - length / 2, lower), upper - length)
        return start_time, start_time + length

    @classmethod
    def _place_flexible_hours(cls, day, hours, tz, free, start, stop) -> list:
        midnight = datetime.combine(day, time.min).replace(tzinfo=tz)
        if start <= midnight and stop >= midnight + timedelta(days=1):
            block = cls._center_block_on_noon(day, hours, tz, free)
            return [block] if block else []
        lower, upper = max(start, midnight), min(stop, midnight + timedelta(days=1))
        blocks, left = [], hours
        for span_start, span_stop, _meta in free:
            span_start, span_stop = max(span_start, lower), min(span_stop, upper)
            if left <= 0 or span_start >= span_stop:
                continue
            take = min(left, elapsed_hours(span_start, span_stop))
            end_utc = span_start.astimezone(UTC) + timedelta(hours=take)
            blocks.append((span_start, end_utc.astimezone(tz)))
            left -= take
        return blocks

    def _get_flexible_hours_per_week(self):
        self.check_singleton()
        return self.hours_per_week or self.full_time_required_hours

    def _get_flexible_leave_hours(self, leave_intervals: Intervals, tz) -> tuple:
        hours_per_day = self.hours_per_day or HOURS_PER_DAY
        hours = defaultdict(float)
        windows = defaultdict(list)
        records = self.env["resource.schedule.exception"].union(
            *(meta for _start, _stop, meta in leave_intervals)
        )
        for record in records:
            for day, window_start, window_stop, cost in record._get_flexible_windows(
                self, tz
            ):
                hours[day] += cost
                windows[day].append((window_start, window_stop))
        return (
            {day: min(hours_per_day, cost) for day, cost in hours.items()},
            windows,
        )

    def _get_flexible_intervals(
        self, start_datetime, end_datetime, tz, leave_hours=None, leave_windows=None
    ):
        self.check_singleton()
        leave_hours = leave_hours or {}
        leave_windows = leave_windows or {}
        hours_per_day = self.hours_per_day or HOURS_PER_DAY
        hours_per_week = self._get_flexible_hours_per_week()
        no_attendance = self.env["resource.calendar.attendance"]
        first_day = start_datetime.date()
        last_day = last_day_of(start_datetime, end_datetime)
        week = week_of(first_day, self.company_id._get_resource_week_start())
        intervals = []
        while week <= last_day:
            filled = fill_week(week, hours_per_day, hours_per_week, leave_hours)
            for day, hours in filled.items():
                if hours <= 0 or not first_day <= day <= last_day:
                    continue
                midnight = datetime.combine(day, time.min).replace(tzinfo=tz)
                free = Intervals(
                    [(midnight, midnight + timedelta(days=1), no_attendance)]
                ) - Intervals(
                    [
                        (window_start, window_stop, no_attendance)
                        for window_start, window_stop in leave_windows.get(day, ())
                    ]
                )
                for start, stop in self._place_flexible_hours(
                    day, hours, tz, free, start_datetime, end_datetime
                ):
                    covered = elapsed_hours(start, stop)
                    intervals.append(
                        (
                            start,
                            stop,
                            self._new_virtual_attendance(
                                covered, min(1.0, covered / hours_per_day)
                            ),
                        )
                    )
            week += timedelta(days=7)
        return intervals

    def _attendance_intervals_batch(
        self,
        start_dt: datetime,
        end_dt: datetime,
        resources: ResourceResource | None = None,
        domain: list | None = None,
        tz: ZoneInfo | str | None = None,
        lunch: bool = False,
    ) -> dict[int | bool, Intervals]:
        if not (start_dt.tzinfo and end_dt.tzinfo):
            raise ValueError("start_dt and end_dt must be timezone-aware")
        if not self:
            raise ValueError(
                "_attendance_intervals_batch requires a calendar; a resource"
                " without one is fully flexible and has no attendance lines"
            )
        self.check_singleton()
        if isinstance(tz, str):
            tz = timezone(tz)
        if not resources:
            resources = self.env["resource.resource"]
            resources_list = [resources]
        else:
            resources_list = list(resources) + [self.env["resource.resource"]]

        if self.schedule_type != "fully_fixed":
            if lunch:
                return {
                    resource.id: Intervals([], keep_distinct=True)
                    for resource in resources_list
                }
            return self._schedule_intervals_batch(start_dt, end_dt, resources_list, tz)

        domain = Domain.AND(
            [
                Domain(domain or Domain.TRUE),
                Domain("calendar_id", "=", self.id),
                Domain("display_type", "=", False),
                Domain("day_period", "!=" if not lunch else "=", "lunch"),
            ]
        )

        calendar_attendances = self.env["resource.calendar.attendance"].search_fetch(
            domain,
            ["dayofweek", "week_type", "hour_from", "hour_to"],
        )
        resources_per_tz = defaultdict(list)
        for resource in resources_list:
            resources_per_tz[tz or timezone(self._get_tz(resource))].append(resource)
        attendances_per_day = defaultdict(
            lambda: self.env["resource.calendar.attendance"]
        )
        weekdays = set()
        for attendance in calendar_attendances:
            weekday = int(attendance.dayofweek)
            weekdays.add(weekday)
            for week_type in (
                (attendance.week_type,) if self.two_weeks_calendar else ("0", "1")
            ):
                attendances_per_day[week_type, weekday] |= attendance

        start = start_dt.astimezone(UTC)
        end = end_dt.astimezone(UTC)
        bounds_per_tz = {
            tz: (start_dt.astimezone(tz), end_dt.astimezone(tz))
            for tz in resources_per_tz
        }
        for low, high in bounds_per_tz.values():
            start = min(start, low.replace(tzinfo=UTC))
            end = max(end, high.replace(tzinfo=UTC))
        days = (
            rrule(DAILY, start.date(), until=end.date(), byweekday=weekdays)
            if weekdays
            else ()
        )
        base_result = []
        for day in days:
            attendances = attendances_per_day[week_type_of(day), day.weekday()]
            for attendance in attendances:
                day_from = wall_at(day, attendance.hour_from)
                day_to = wall_at(day, attendance.hour_to)
                base_result.append((day_from, day_to, attendance))

        result_per_tz = {
            tz: [
                (
                    max(bounds_per_tz[tz][0], val[0].replace(tzinfo=tz)),
                    min(bounds_per_tz[tz][1], val[1].replace(tzinfo=tz)),
                    val[2],
                )
                for val in base_result
            ]
            for tz in resources_per_tz
        }
        result_per_resource_id = {}
        for tz, tz_resources in resources_per_tz.items():
            intervals = Intervals(result_per_tz[tz], keep_distinct=True)
            for resource in tz_resources:
                result_per_resource_id[resource.id] = intervals
        return result_per_resource_id

    def _schedule_intervals_batch(
        self, start_dt, end_dt, resources_list, tz
    ) -> dict[int | bool, Intervals]:
        read = (
            self._get_fully_flexible_intervals
            if self.schedule_type == "fully_flexible"
            else self._get_flexible_intervals
        )
        result = {}
        by_zone = {}
        for resource in resources_list:
            zone = tz or timezone(self._get_tz(resource))
            if zone not in by_zone:
                by_zone[zone] = Intervals(
                    read(start_dt.astimezone(zone), end_dt.astimezone(zone), zone),
                    keep_distinct=True,
                )
            result[resource.id] = by_zone[zone]
        return result

    def _handle_flexible_leave_interval(
        self, dt0: datetime, dt1: datetime, leave: Any
    ) -> tuple[datetime, datetime]:
        if dt1 <= dt0:
            return dt0, dt1
        tz = dt0.tzinfo
        last_day = (dt1 - timedelta(microseconds=1)).date()
        dt0 = datetime.combine(dt0.date(), time.min).replace(tzinfo=tz)
        dt1 = datetime.combine(last_day + timedelta(days=1), time.min).replace(
            tzinfo=tz
        )
        return dt0, dt1

    def _get_domain_exceptions(self, domain: list | None) -> Domain:
        given = Domain(domain or Domain.TRUE)
        if any(
            condition.field_expr.startswith("time_type_id")
            for condition in given.iter_conditions()
        ):
            return given
        return given & Domain("time_type_id.is_work", "=", False)

    def _leave_intervals_batch(
        self,
        start_dt: datetime,
        end_dt: datetime,
        resources: ResourceResource | None = None,
        domain: list | None = None,
        tz: ZoneInfo | str | None = None,
    ) -> dict[int | bool, Intervals]:
        if not (start_dt.tzinfo and end_dt.tzinfo):
            raise ValueError("start_dt and end_dt must be timezone-aware")

        if isinstance(tz, str):
            tz = timezone(tz)

        domain = self._get_domain_exceptions(domain)

        resources_list = list(resources) if resources else []

        resources_list.append(self.env["resource.resource"])
        schedule_wide = Domain("resource_id", "=", False) & Domain(
            "calendar_id", "in", [False, *self.ids]
        )
        domain = (
            domain
            & (Domain("resource_id", "!=", False) | schedule_wide)
            & Domain("resource_id", "in", [False] + [r.id for r in resources_list])
            & Domain("date_from", "<=", end_dt.astimezone(UTC).replace(tzinfo=None))
            & Domain("date_to", ">=", start_dt.astimezone(UTC).replace(tzinfo=None))
        )

        window_per_resource = [
            (
                resource,
                resource_tz := tz or timezone(self._get_tz(resource)),
                start_dt.astimezone(resource_tz),
                end_dt.astimezone(resource_tz),
            )
            for resource in resources_list
        ]

        window_by_resource = {window[0].id: window for window in window_per_resource}
        windows_by_company = defaultdict(list)
        windows_of_no_company = []
        for window in window_per_resource:
            resource = window[0]
            if resource and resource.company_id:
                windows_by_company[resource.company_id.id].append(window)
            else:
                windows_of_no_company.append(window)

        result = defaultdict(list)
        for leave in self.env["resource.schedule.exception"].search(domain):
            leave_date_from = leave.date_from.replace(tzinfo=UTC)
            leave_date_to = leave.date_to.replace(tzinfo=UTC)
            if leave.resource_id:
                windows = [window_by_resource[leave.resource_id.id]]
            elif leave.company_id:
                windows = (
                    windows_by_company[leave.company_id.id] + windows_of_no_company
                )
            else:
                windows = window_per_resource
            bounds_per_tz = {}
            for resource, resource_tz, start, end in windows:
                if resource_tz not in bounds_per_tz:
                    dt0 = leave_date_from.astimezone(resource_tz)
                    dt1 = leave_date_to.astimezone(resource_tz)
                    if leave.resource_id and self.schedule_type != "fully_fixed":
                        dt0, dt1 = self._handle_flexible_leave_interval(dt0, dt1, leave)
                    bounds_per_tz[resource_tz] = (dt0, dt1)
                dt0, dt1 = bounds_per_tz[resource_tz]
                result[resource.id].append((max(start, dt0), min(end, dt1), leave))

        return {r.id: Intervals(result[r.id]) for r in resources_list}

    def _work_intervals_batch(
        self,
        start_dt: datetime,
        end_dt: datetime,
        resources: ResourceResource | None = None,
        domain: list | None = None,
        tz: ZoneInfo | str | None = None,
        compute_leaves: bool = True,
        exclude_bookings: bool = False,
    ) -> dict[int | bool, Intervals]:
        if not resources:
            resources = self.env["resource.resource"]
            resources_list = [resources]
        else:
            resources_list = list(resources) + [self.env["resource.resource"]]

        if compute_leaves and self.schedule_type == "flexible":
            work = self._flexible_work_intervals_batch(
                start_dt, end_dt, resources, resources_list, domain, tz
            )
        else:
            attendance_intervals = self._attendance_intervals_batch(
                start_dt,
                end_dt,
                resources,
                tz=tz,
            )
            if not compute_leaves:
                return {r.id: attendance_intervals[r.id] for r in resources_list}
            leave_intervals = self._leave_intervals_batch(
                start_dt, end_dt, resources, domain, tz=tz
            )
            work = {
                r.id: attendance_intervals[r.id] - leave_intervals[r.id]
                for r in resources_list
            }
        if exclude_bookings:
            booked = self.env[
                "resource.reservation"
            ]._get_enforced_booking_intervals_batch(start_dt, end_dt, resources)
            work = {
                resource_id: intervals - booked[resource_id]
                for resource_id, intervals in work.items()
            }
        return work

    def _flexible_work_intervals_batch(
        self, start_dt, end_dt, resources, resources_list, domain, tz
    ) -> dict[int | bool, Intervals]:
        if isinstance(tz, str):
            tz = timezone(tz)
        zones = {r.id: tz or timezone(self._get_tz(r)) for r in resources_list}
        week_start = self.company_id._get_resource_week_start()
        bounds = []
        for zone in set(zones.values()):
            local_start, local_end = start_dt.astimezone(zone), end_dt.astimezone(zone)
            first = week_of(local_start.date(), week_start)
            last = week_of(last_day_of(local_start, local_end), week_start)
            bounds += [
                datetime.combine(first, time.min, zone),
                datetime.combine(last + timedelta(days=7), time.min, zone),
            ]
        leaves = self._leave_intervals_batch(
            min(bounds), max(bounds), resources, domain, tz=tz
        )
        work = {}
        for resource in resources_list:
            zone = zones[resource.id]
            leave_hours, leave_windows = self._get_flexible_leave_hours(
                leaves[resource.id], zone
            )
            blocks = Intervals(
                self._get_flexible_intervals(
                    start_dt.astimezone(zone),
                    end_dt.astimezone(zone),
                    zone,
                    leave_hours,
                    leave_windows,
                ),
                keep_distinct=True,
            )
            work[resource.id] = blocks - leaves[resource.id]
        return work

    def _unavailable_intervals(
        self,
        start_dt: datetime,
        end_dt: datetime,
        resource: ResourceResource | None = None,
        domain: list | None = None,
        tz: ZoneInfo | str | None = None,
        exclude_bookings: bool = True,
    ) -> list[tuple[datetime, datetime]]:
        if resource is None:
            resource = self.env["resource.resource"]
        return self._unavailable_intervals_batch(
            start_dt,
            end_dt,
            resources=resource,
            domain=domain,
            tz=tz,
            exclude_bookings=exclude_bookings,
        )[resource.id]

    def _unavailable_intervals_batch(
        self,
        start_dt: datetime,
        end_dt: datetime,
        resources: ResourceResource | None = None,
        domain: list | None = None,
        tz: ZoneInfo | str | None = None,
        exclude_bookings: bool = True,
    ) -> dict[int | bool, list[tuple[datetime, datetime]]]:
        empty = self.env["resource.resource"]
        resources_list = list(resources) if resources else [empty]
        by_leaves = self.schedule_type != "fully_fixed"
        flexible = empty.union(*(r for r in resources_list if r and by_leaves))
        fixed = [] if by_leaves else resources_list

        def to_utc(intervals):
            return [
                (start.astimezone(UTC), stop.astimezone(UTC))
                for start, stop in intervals
                if start < stop
            ]

        result = {}
        if by_leaves:
            leaves = self._leave_intervals_batch(
                start_dt, end_dt, flexible, domain, tz=tz
            )
            if exclude_bookings and flexible:
                booked = self.env[
                    "resource.reservation"
                ]._get_enforced_booking_intervals_batch(start_dt, end_dt, flexible)
                leaves |= {
                    resource.id: leaves[resource.id] | booked[resource.id]
                    for resource in flexible
                }
            for resource in resources_list:
                result[resource.id] = to_utc(
                    (start, stop) for start, stop, _meta in leaves[resource.id]
                )
        if fixed:
            work_intervals = self._work_intervals_batch(
                start_dt,
                end_dt,
                empty.union(*fixed),
                domain,
                tz,
                exclude_bookings=exclude_bookings,
            )
            for resource in fixed:
                bounds = [start_dt]
                for start, stop, _meta in work_intervals[resource.id]:
                    bounds += [start, stop]
                bounds.append(end_dt)
                result[resource.id] = to_utc(
                    zip(bounds[0::2], bounds[1::2], strict=True)
                )
        return result

    def _check_overlap(self, attendance_ids: ResourceCalendarAttendance) -> None:
        timed_attendances = [
            attendance
            for attendance in attendance_ids
            if attendance.hour_to > attendance.hour_from
        ]
        result = [
            (
                int(attendance.dayofweek) * 24 + attendance.hour_from + 0.000001,
                int(attendance.dayofweek) * 24 + attendance.hour_to,
                attendance,
            )
            for attendance in timed_attendances
        ]

        if len(Intervals(result)) != len(result):
            raise ValidationError(self.env._("Attendances can't overlap."))

    @api.model
    def _get_fully_flexible_calendar(self) -> Self:
        return self.env.ref("base.resource_calendar_fully_flexible")

    @api.model
    def _get_company_calendar(self, company) -> Self:
        return company.resource_calendar_id or self._get_fully_flexible_calendar()

    @api.model
    def _normalize_calendar_vals(self, vals: ValuesType, fname: str) -> ValuesType:
        if fname in vals and not vals[fname]:
            vals = dict(vals, **{fname: self._get_fully_flexible_calendar().id})
        return vals

    def _get_hours_by_day(self, intervals: Intervals) -> dict[date, float]:
        return hours_by_day(intervals)

    def _get_duration_data(self, attendance_intervals: Intervals) -> dict[str, float]:
        day_hours = self._get_hours_by_day(attendance_intervals)
        day_days = defaultdict(float)
        if len(self) == 1 and self.schedule_type != "fully_fixed":
            hours_per_day = self.hours_per_day or HOURS_PER_DAY
            for day, hours in day_hours.items():
                day_days[day] = min(1.0, hours / hours_per_day)
        else:
            for start, stop, meta in split_at_midnight(attendance_intervals):
                total_duration_hours = sum(meta.mapped("duration_hours"))
                if total_duration_hours:
                    day_days[start.date()] += (
                        sum(meta.mapped("duration_days"))
                        * elapsed_hours(start, stop)
                        / total_duration_hours
                    )

        return {
            "days": float_round(sum(day_days.values()), precision_rounding=0.001),
            "hours": sum(day_hours.values()),
        }

    def _get_days_per_week(self) -> float:
        self.check_singleton()
        if self.schedule_type != "fully_fixed":
            hours_per_day = self.hours_per_day or HOURS_PER_DAY
            return self._get_flexible_hours_per_week() / hours_per_day
        attendances = self._get_global_attendances()
        if self.two_weeks_calendar:
            number_of_days = len(
                set(
                    attendances.filtered(lambda cal: cal.week_type == "1").mapped(
                        "dayofweek"
                    )
                )
            )
            number_of_days += len(
                set(
                    attendances.filtered(lambda cal: cal.week_type == "0").mapped(
                        "dayofweek"
                    )
                )
            )
        else:
            number_of_days = len(set(attendances.mapped("dayofweek")))
        return number_of_days / 2 if self.two_weeks_calendar else number_of_days

    def _get_hours_per_week(self) -> float:
        self.check_singleton()
        hour_count = 0.0
        for attendance in self._get_global_attendances():
            if self.duration_based:
                hour_count += attendance.duration_hours
            else:
                hour_count += attendance.hour_to - attendance.hour_from
        return hour_count / 2 if self.two_weeks_calendar else hour_count

    def _get_hours_per_day(self) -> float:
        hour_per_week = self._get_hours_per_week()
        number_of_days = self._get_days_per_week()
        return hour_per_week / number_of_days if number_of_days else 0

    def _get_global_attendances(self):
        return self.attendance_ids.filtered(
            lambda attendance: (
                attendance.day_period != "lunch" and not attendance.display_type
            )
        )

    def _get_unusual_days(self, start_dt, end_dt, company=False):
        if not self:
            return {}
        self.check_singleton()
        first_day, last_day = start_dt.date(), end_dt.date()
        tz = timezone(self._get_tz())
        start = datetime.combine(first_day, time.min, tz)
        stop = datetime.combine(last_day + timedelta(days=1), time.min, tz)
        days = [
            first_day + timedelta(days=offset)
            for offset in range((last_day - first_day).days + 1)
        ]
        domain = [("company_id", "in", (company.id, False))] if company else None
        if self.schedule_type != "fully_fixed":
            off = set()
            for leave_start, leave_stop, _leave in self._leave_intervals_batch(
                start, stop, domain=domain
            )[False]:
                day = leave_start.date()
                while day <= last_day_of(leave_start, leave_stop):
                    off.add(day)
                    day += timedelta(days=1)
            return {fields.Date.to_string(day): day in off for day in days}
        worked = {
            work_start.date()
            for work_start, _stop, _meta in self._work_intervals_batch(
                start, stop, domain=domain
            )[False]
        }
        return {fields.Date.to_string(day): day not in worked for day in days}

    def _prepare_default_attendance_commands(self, company_id=None) -> list:
        return [
            Command.create(vals)
            for vals in self._prepare_default_attendance_vals(company_id)
        ]

    def _prepare_two_weeks_attendance_commands(self, attendance_vals=None):
        if attendance_vals is None:
            attendance_vals = [
                attendance._copy_attendance_vals() for attendance in self.attendance_ids
            ]
        second_week_seq = len(attendance_vals) + 1
        final_attendances = [
            Command.create(
                {
                    "name": "First week",
                    "dayofweek": "0",
                    "sequence": 0,
                    "hour_from": 0,
                    "day_period": "morning",
                    "week_type": "0",
                    "hour_to": 0,
                    "display_type": "line_section",
                }
            ),
            Command.create(
                {
                    "name": "Second week",
                    "dayofweek": "0",
                    "sequence": second_week_seq,
                    "hour_from": 0,
                    "day_period": "morning",
                    "week_type": "1",
                    "hour_to": 0,
                    "display_type": "line_section",
                }
            ),
        ]
        for idx, vals in enumerate(attendance_vals):
            final_attendances.append(
                Command.create(dict(vals, week_type="0", sequence=idx + 1))
            )
            final_attendances.append(
                Command.create(
                    dict(vals, week_type="1", sequence=second_week_seq + idx + 1)
                )
            )
        return final_attendances

    def get_work_hours_count(
        self,
        start_dt: datetime,
        end_dt: datetime,
        compute_leaves: bool = True,
        domain: list | None = None,
    ) -> float:
        self.check_singleton()
        return self.get_work_duration_data(start_dt, end_dt, compute_leaves, domain)[
            "hours"
        ]

    def get_work_duration_data(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
        compute_leaves: bool = True,
        domain: list | None = None,
        tz: ZoneInfo | str | None = None,
    ) -> dict[str, float]:
        if not compute_leaves:
            return self.get_attendance_duration_data(from_datetime, to_datetime, tz=tz)
        intervals = self._work_intervals_batch(
            localized(from_datetime), localized(to_datetime), domain=domain, tz=tz
        )[False]
        return self._get_duration_data(intervals)

    def get_attendance_duration_data(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
        domain: list | None = None,
        tz: ZoneInfo | str | None = None,
    ) -> dict[str, float]:
        intervals = self._attendance_intervals_batch(
            localized(from_datetime), localized(to_datetime), domain=domain, tz=tz
        )[False]
        return self._get_duration_data(intervals)

    def _get_hours_for_date(
        self, target_date: date, day_period: str | None = None
    ) -> tuple[float, float]:
        self.check_singleton()
        if not target_date:
            err = "Target Date cannot be empty"
            raise ValueError(err)
        if self.schedule_type == "fully_flexible":
            return {"morning": (0.0, 12.0), "afternoon": (12.0, 24.0)}.get(
                day_period, (0.0, 24.0)
            )
        if self.schedule_type == "flexible":
            datetimes = [
                12.0 - self.hours_per_day / 2.0,
                12.0,
                12.0 + self.hours_per_day / 2.0,
            ]
            if day_period:
                return (
                    (datetimes[0], datetimes[1])
                    if day_period == "morning"
                    else (datetimes[1], datetimes[2])
                )
            return (datetimes[0], datetimes[2])

        domain = [
            ("calendar_id", "=", self.id),
            ("display_type", "=", False),
            ("day_period", "!=", "lunch"),
        ]

        init_attendances = self.env["resource.calendar.attendance"]._read_group(
            domain=domain,
            groupby=["week_type", "dayofweek", "day_period"],
            aggregates=["hour_from:min", "hour_to:max"],
            order="dayofweek,hour_from:min",
        )

        init_attendances = [
            DummyAttendance(hour_from, hour_to, dayofweek, day_period, week_type)
            for week_type, dayofweek, day_period, hour_from, hour_to in init_attendances
        ]

        if day_period:
            attendances = [
                att for att in init_attendances if att.day_period == day_period
            ]
            attendances.extend(
                attendance._replace(
                    hour_from=(
                        attendance.hour_from
                        if day_period == "morning"
                        else (attendance.hour_from + attendance.hour_to) / 2
                    ),
                    hour_to=(
                        attendance.hour_to
                        if day_period == "afternoon"
                        else (attendance.hour_from + attendance.hour_to) / 2
                    ),
                )
                for attendance in init_attendances
                if attendance.day_period == "full_day"
            )

        else:
            attendances = init_attendances

        week_envelope_from, week_envelope_to = self._week_hours_envelope(attendances)

        week_type = False
        if self.two_weeks_calendar:
            week_type = week_type_of(target_date)

        filtered_attendances = [
            att
            for att in attendances
            if (not self.two_weeks_calendar or att.week_type == week_type)
            and int(att.dayofweek) == target_date.weekday()
        ]
        hour_from = min(
            (att.hour_from for att in filtered_attendances), default=week_envelope_from
        )
        hour_to = max(
            (att.hour_to for att in filtered_attendances), default=week_envelope_to
        )

        return (hour_from, hour_to)

    def _get_working_days(self):
        self.check_singleton()

        working_days = defaultdict(lambda: defaultdict(lambda: False))
        for attendance in self._get_global_attendances():
            week_type = attendance.week_type if self.two_weeks_calendar else False
            working_days[week_type][attendance.dayofweek] = True
        return working_days

    def _iter_plan_intervals(
        self,
        day_dt: datetime,
        forward: bool,
        compute_leaves: bool,
        domain: list | None,
        resource: ResourceResource,
    ):
        if compute_leaves:
            get_intervals = partial(
                self._work_intervals_batch,
                domain=domain,
                resources=resource,
                exclude_bookings=True,
            )
        else:
            get_intervals = partial(
                self._attendance_intervals_batch, resources=resource
            )
        resource_id = resource.id
        horizon = _PLAN_WINDOW * _PLAN_MAX_ITERATIONS
        offset, width = timedelta(0), _PLAN_WINDOW
        while offset < horizon:
            width = min(width, horizon - offset)
            if forward:
                dt = day_dt + offset
                yield from get_intervals(dt, dt + width)[resource_id]
            else:
                dt = day_dt - offset
                yield from reversed(get_intervals(dt - width, dt)[resource_id])
            offset += width
            width *= 2

    def plan_hours(
        self,
        hours: float,
        day_dt: datetime,
        compute_leaves: bool = False,
        domain: list | None = None,
        resource: ResourceResource | None = None,
    ) -> datetime | None:
        revert = to_timezone(day_dt.tzinfo)
        day_dt = localized(day_dt)
        if resource is None:
            resource = self.env["resource.resource"]
        forward = hours >= 0
        hours = abs(hours)
        for start, stop, _meta in self._iter_plan_intervals(
            day_dt, forward, compute_leaves, domain, resource
        ):
            interval_hours = elapsed_hours(start, stop)
            if hours <= interval_hours:
                if forward:
                    return revert(start.astimezone(UTC) + timedelta(hours=hours))
                return revert(stop.astimezone(UTC) - timedelta(hours=hours))
            hours -= interval_hours
        return None

    def plan_days(
        self,
        days: int,
        day_dt: datetime,
        compute_leaves: bool = False,
        domain: list | None = None,
        resource: ResourceResource | None = None,
    ) -> datetime | None:
        revert = to_timezone(day_dt.tzinfo)
        day_dt = localized(day_dt)
        if resource is None:
            resource = self.env["resource.resource"]
        if not days:
            return revert(day_dt)
        forward = days > 0
        days = abs(days)
        found = set()
        boundary = None
        for start, stop, _meta in self._iter_plan_intervals(
            day_dt, forward, compute_leaves, domain, resource
        ):
            if start.date() not in found:
                if len(found) == days:
                    return revert(boundary)
                found.add(start.date())
            boundary = stop if forward else start
        return None

    def _prepare_default_attendance_vals(self, company_id=None) -> list:
        if company_id and (
            attendances := company_id.resource_calendar_id.attendance_ids
        ):
            return [attendance._copy_attendance_vals() for attendance in attendances]
        default_days = (
            (
                "0",
                self.env._("Monday Morning"),
                self.env._("Monday Lunch"),
                self.env._("Monday Afternoon"),
            ),
            (
                "1",
                self.env._("Tuesday Morning"),
                self.env._("Tuesday Lunch"),
                self.env._("Tuesday Afternoon"),
            ),
            (
                "2",
                self.env._("Wednesday Morning"),
                self.env._("Wednesday Lunch"),
                self.env._("Wednesday Afternoon"),
            ),
            (
                "3",
                self.env._("Thursday Morning"),
                self.env._("Thursday Lunch"),
                self.env._("Thursday Afternoon"),
            ),
            (
                "4",
                self.env._("Friday Morning"),
                self.env._("Friday Lunch"),
                self.env._("Friday Afternoon"),
            ),
        )
        periods = (("morning", 8, 12), ("lunch", 12, 13), ("afternoon", 13, 17))
        return [
            {
                "name": name,
                "dayofweek": dayofweek,
                "hour_from": hour_from,
                "hour_to": hour_to,
                "day_period": day_period,
            }
            for dayofweek, *names in default_days
            for (day_period, hour_from, hour_to), name in zip(
                periods, names, strict=True
            )
        ]

    @staticmethod
    def _get_single_week_attendance_vals(attendance_vals) -> list:
        return [
            dict(vals, week_type=False)
            for vals in attendance_vals
            if not vals.get("display_type") and vals.get("week_type") != "1"
        ]

    def _is_working_day(self, day: date) -> bool:
        self.check_singleton()
        if self.schedule_type != "fully_fixed":
            return True
        working_days = self._get_working_days()
        dayofweek = str(day.weekday())
        if self.two_weeks_calendar:
            weektype = week_type_of(day)
            return working_days[weektype][dayofweek]
        return working_days[False][dayofweek]

    @staticmethod
    def _week_hours_envelope(attendances) -> tuple[float, float]:
        return (
            min((att.hour_from for att in attendances), default=0.0),
            max((att.hour_to for att in attendances), default=0.0),
        )
