import re
from datetime import UTC, datetime, time
from itertools import islice
from typing import TYPE_CHECKING, cast

from dateutil import rrule
from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.datetime import timezone, wall_to_utc
from odoo.libs.debug_log import DebugLog
from odoo.tools import format_date, get_lang
from odoo.tools.misc import clean_context

from odoo.addons.base.models.mixin_recurrence_rule import (
    REPEAT_TYPE_COUNT,
    REPEAT_TYPE_SELECTION,
    WEEKDAY_SELECTION,
)
from odoo.addons.base.models.res_partner import _selection_timezones

if TYPE_CHECKING:
    from datetime import date

    from odoo.addons.base.models.res_users import ResUsers
    from odoo.addons.calendar.models.calendar_event import CalendarEvent
    from odoo.addons.calendar.models.mixin_calendar_privacy import MixinCalendarPrivacy

_debug = DebugLog(__name__)

REPEAT_TYPE_SELECTION_RRULE = [*REPEAT_TYPE_SELECTION, REPEAT_TYPE_COUNT]

MAX_RECURRENT_OCCURRENCES = 720

SELECT_FREQ_TO_RRULE = {
    "day": rrule.DAILY,
    "week": rrule.WEEKLY,
    "month": rrule.MONTHLY,
    "year": rrule.YEARLY,
}

RRULE_FREQ_TO_SELECT = {v: k for k, v in SELECT_FREQ_TO_RRULE.items()}

RRULE_WEEKDAY_TO_FIELD = {
    rrule.MO.weekday: "mon",
    rrule.TU.weekday: "tue",
    rrule.WE.weekday: "wed",
    rrule.TH.weekday: "thu",
    rrule.FR.weekday: "fri",
    rrule.SA.weekday: "sat",
    rrule.SU.weekday: "sun",
}

RRULE_WEEKDAYS = {
    "SUN": "SU",
    "MON": "MO",
    "TUE": "TU",
    "WED": "WE",
    "THU": "TH",
    "FRI": "FR",
    "SAT": "SA",
}

LAST_DAY_OF_MONTH = -1

RULE_FIELDS = frozenset(
    {
        "repeat_unit",
        "repeat_interval",
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
        "month_by",
        "day",
        "weekday",
        "byday",
        "week_start",
    }
)

MONTH_BY_SELECTION = [
    ("date", "Date of month"),
    ("day", "Day of month"),
]

BYDAY_SELECTION = [
    ("1", "First"),
    ("2", "Second"),
    ("3", "Third"),
    ("4", "Fourth"),
    ("-1", "Last"),
]


def freq_to_select(rrule_freq):
    return RRULE_FREQ_TO_SELECT[rrule_freq]


def freq_to_rrule(freq):
    return SELECT_FREQ_TO_RRULE[freq]


def weekday_to_field(weekday_index):
    return RRULE_WEEKDAY_TO_FIELD.get(weekday_index)


class CalendarRecurrence(models.Model):
    _name = "calendar.recurrence"
    _inherit = ["mixin.calendar.privacy", "mixin.recurrence.rule"]
    _description = "Event Recurrence Rule"

    _privacy_event_fname = "calendar_event_ids"
    _search_visibility_fields = ("calendar_event_ids",)

    base_event_id = fields.Many2one(
        comodel_name="calendar.event",
        copy=False,
        ondelete="set null",
    )
    calendar_event_ids = fields.One2many(
        comodel_name="calendar.event",
        inverse_name="recurrence_id",
    )
    trigger_id = fields.Many2one(comodel_name="ir.cron.trigger")

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    event_tz = fields.Selection(
        selection=_selection_timezones,
        string="Timezone",
        default=lambda self: self.env.context.get("tz") or self.env.user.tz,
    )
    rrule = fields.Char(
        compute="_compute_rrule",
        inverse="_inverse_rrule",
        store=True,
    )
    dtstart = fields.Datetime(compute="_compute_dtstart")
    repeat_type = fields.Selection(
        selection_add=[REPEAT_TYPE_COUNT],
        default="count",
        ondelete={REPEAT_TYPE_COUNT[0]: "set default"},
    )
    repeat_number = fields.Integer(
        string="Number of Repetitions",
        default=1,
    )
    mon = fields.Boolean()
    tue = fields.Boolean()
    wed = fields.Boolean()
    thu = fields.Boolean()
    fri = fields.Boolean()
    sat = fields.Boolean()
    sun = fields.Boolean()
    month_by = fields.Selection(
        selection=MONTH_BY_SELECTION,
        default="date",
    )
    day = fields.Integer(default=1)
    weekday = fields.Selection(selection=WEEKDAY_SELECTION)
    byday = fields.Selection(
        selection=BYDAY_SELECTION,
        string="By day",
    )
    week_start = fields.Selection(
        selection=WEEKDAY_SELECTION,
        string="Week Start",
        default=lambda self: self._default_week_start(),
        required=True,
    )
    custom_rrule = fields.Char(
        string="Custom Rule",
        help="The rule this recurrence follows when its options cannot express it.",
    )

    _month_day = models.Constraint(
        """CHECK (
        repeat_unit NOT IN ('month', 'year')
        OR (repeat_unit = 'year' AND month_by != 'day')
        OR (repeat_unit = 'month' AND month_by = 'date'
            AND (day = %s OR (day >= 1 AND day <= 31)))
        OR (month_by = 'day'
            AND weekday IS NOT NULL AND weekday IN %s
            AND byday IS NOT NULL AND byday IN %s))"""
        % (
            LAST_DAY_OF_MONTH,
            tuple(wd[0] for wd in WEEKDAY_SELECTION),
            tuple(bd[0] for bd in BYDAY_SELECTION),
        ),
        "The day must be between 1 and 31, or the last day of the month",
    )

    def _has_other_event_owner(self, sender_user: ResUsers) -> bool:
        self.check_singleton()
        has_base_event = self.base_event_id
        has_different_owner = (
            cast("CalendarEvent", self.base_event_id).user_id
            and cast("CalendarEvent", self.base_event_id).user_id != sender_user
        )
        return bool(has_base_event and has_different_owner)

    @api.model
    def _get_domain_privacy(self):
        events = self.env["calendar.event"].with_context(active_test=False)
        visible = events._search(
            Domain(events._get_domain_default_privacy()),
            active_test=False,
        )
        return Domain("calendar_event_ids", "=", False) | Domain(
            "id", "in", visible.select("recurrence_id")
        )

    def _check_calendar_privacy_write_permissions(self) -> None:
        if self.env.su:
            return
        hidden = cast("MixinCalendarPrivacy", self)._privacy_hidden()
        if hidden:
            raise self.env["ir.access"]._prepare_record_access_error(hidden[0], "write")

    @api.model_create_multi
    def create(self, vals_list):
        recurrences = super().create(vals_list)
        recurrences._check_calendar_privacy_write_permissions()
        return recurrences

    def write(self, vals):
        self._check_calendar_privacy_write_permissions()
        return super().write(self._prepare_rule_vals(vals))

    def unlink(self):
        self._check_calendar_privacy_write_permissions()
        return super().unlink()

    @api.depends("calendar_event_ids.start")
    def _compute_dtstart(self) -> None:
        groups = self.env["calendar.event"]._read_group(
            [("recurrence_id", "in", self.ids)], ["recurrence_id"], ["start:min"]
        )
        start_mapping = {recurrence.id: start_min for recurrence, start_min in groups}
        for recurrence in self:
            recurrence.dtstart = start_mapping.get(recurrence.id)

    def _get_local_start(self):
        if not self.dtstart or self._is_allday():
            return self.dtstart or None
        return (
            self.dtstart.replace(tzinfo=UTC)
            .astimezone(self._get_timezone())
            .replace(tzinfo=None)
        )

    def _get_position_labels(self) -> tuple:
        weekday_selection = dict(
            self._fields["weekday"]._description_selection(self.env)
        )
        byday_selection = dict(self._fields["byday"]._description_selection(self.env))
        return byday_selection[self.byday], weekday_selection[self.weekday]

    def _get_daily_recurrence_name(self) -> str:
        if self.repeat_type == "count":
            return self.env._(
                "Every %(interval)s Days for %(count)s events",
                interval=self.repeat_interval,
                count=self.repeat_number,
            )
        if self.repeat_type == "until":
            return self.env._(
                "Every %(interval)s Days until %(until)s",
                interval=self.repeat_interval,
                until=self.repeat_until,
            )
        return self.env._("Every %(interval)s Days", interval=self.repeat_interval)

    def _get_weekly_recurrence_name(self) -> str:
        weekday_selection = dict(
            self._fields["weekday"]._description_selection(self.env)
        )
        weekdays = self._get_week_days()
        weekdays = [str(w) for w in weekdays]
        week_map = {v: k for k, v in RRULE_WEEKDAYS.items()}
        weekday_short = [week_map[w] for w in weekdays]
        day_strings = [weekday_selection[day] for day in weekday_short]
        days = ", ".join(day_strings)

        if self.repeat_type == "count":
            return self.env._(
                "Every %(interval)s Weeks on %(days)s for %(count)s events",
                interval=self.repeat_interval,
                days=days,
                count=self.repeat_number,
            )
        if self.repeat_type == "until":
            return self.env._(
                "Every %(interval)s Weeks on %(days)s until %(until)s",
                interval=self.repeat_interval,
                days=days,
                until=self.repeat_until,
            )
        return self.env._(
            "Every %(interval)s Weeks on %(days)s",
            interval=self.repeat_interval,
            days=days,
        )

    def _get_monthly_recurrence_name(self) -> str:
        if self.month_by == "day":
            position_label, weekday_label = self._get_position_labels()

            if self.repeat_type == "count":
                return self.env._(
                    "Every %(interval)s Months on the %(position)s %(weekday)s for %(count)s events",
                    interval=self.repeat_interval,
                    position=position_label,
                    weekday=weekday_label,
                    count=self.repeat_number,
                )
            if self.repeat_type == "until":
                return self.env._(
                    "Every %(interval)s Months on the %(position)s %(weekday)s until %(until)s",
                    interval=self.repeat_interval,
                    position=position_label,
                    weekday=weekday_label,
                    until=self.repeat_until,
                )
            return self.env._(
                "Every %(interval)s Months on the %(position)s %(weekday)s",
                interval=self.repeat_interval,
                position=position_label,
                weekday=weekday_label,
            )
        if self.day == LAST_DAY_OF_MONTH:
            if self.repeat_type == "count":
                return self.env._(
                    "Every %(interval)s Months on the last day for %(count)s events",
                    interval=self.repeat_interval,
                    count=self.repeat_number,
                )
            if self.repeat_type == "until":
                return self.env._(
                    "Every %(interval)s Months on the last day until %(until)s",
                    interval=self.repeat_interval,
                    until=self.repeat_until,
                )
            return self.env._(
                "Every %(interval)s Months on the last day",
                interval=self.repeat_interval,
            )
        else:
            if self.repeat_type == "count":
                return self.env._(
                    "Every %(interval)s Months day %(day)s for %(count)s events",
                    interval=self.repeat_interval,
                    day=self.day,
                    count=self.repeat_number,
                )
            if self.repeat_type == "until":
                return self.env._(
                    "Every %(interval)s Months day %(day)s until %(until)s",
                    interval=self.repeat_interval,
                    day=self.day,
                    until=self.repeat_until,
                )
            return self.env._(
                "Every %(interval)s Months day %(day)s",
                interval=self.repeat_interval,
                day=self.day,
            )

    def _get_yearly_recurrence_name(self) -> str:
        local_start = self.month_by == "day" and self._get_local_start()
        if local_start:
            position_label, weekday_label = self._get_position_labels()
            month_label = format_date(self.env, local_start.date(), date_format="MMMM")
            if self.repeat_type == "count":
                return self.env._(
                    "Every %(interval)s Years on the %(position)s %(weekday)s of %(month)s for %(count)s events",
                    interval=self.repeat_interval,
                    position=position_label,
                    weekday=weekday_label,
                    month=month_label,
                    count=self.repeat_number,
                )
            if self.repeat_type == "until":
                return self.env._(
                    "Every %(interval)s Years on the %(position)s %(weekday)s of %(month)s until %(until)s",
                    interval=self.repeat_interval,
                    position=position_label,
                    weekday=weekday_label,
                    month=month_label,
                    until=self.repeat_until,
                )
            return self.env._(
                "Every %(interval)s Years on the %(position)s %(weekday)s of %(month)s",
                interval=self.repeat_interval,
                position=position_label,
                weekday=weekday_label,
                month=month_label,
            )
        if self.repeat_type == "count":
            return self.env._(
                "Every %(interval)s Years for %(count)s events",
                interval=self.repeat_interval,
                count=self.repeat_number,
            )
        if self.repeat_type == "until":
            return self.env._(
                "Every %(interval)s Years until %(until)s",
                interval=self.repeat_interval,
                until=self.repeat_until,
            )
        return self.env._("Every %(interval)s Years", interval=self.repeat_interval)

    def get_recurrence_name(self):
        _debug.logic(
            "recurrence.name",
            record=self.id,
            unit=self.repeat_unit,
            repeat_type=self.repeat_type,
        )
        if self.custom_rrule:
            return self.env._("Custom rule: %(rule)s", rule=self.rrule)
        if self.repeat_unit == "day":
            return self._get_daily_recurrence_name()
        if self.repeat_unit == "week":
            return self._get_weekly_recurrence_name()
        if self.repeat_unit == "month":
            return self._get_monthly_recurrence_name()
        if self.repeat_unit == "year":
            return self._get_yearly_recurrence_name()
        return None

    @api.depends("rrule")
    def _compute_name(self):
        for recurrence in self:
            recurrence.name = recurrence.get_recurrence_name()

    @api.depends(
        "byday",
        "repeat_until",
        "repeat_unit",
        "month_by",
        "repeat_interval",
        "repeat_number",
        "repeat_type",
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
        "day",
        "weekday",
        "week_start",
        "custom_rrule",
    )
    def _compute_rrule(self) -> None:
        for recurrence in self:
            current_rule = recurrence._rrule_serialize()
            if recurrence.rrule != current_rule:
                _debug.lifecycle(
                    "recurrence.rrule_changed",
                    record=recurrence.id,
                    unit=recurrence.repeat_unit,
                    interval=recurrence.repeat_interval,
                    repeat_type=recurrence.repeat_type,
                    had_rule=bool(recurrence.rrule),
                )
                recurrence.rrule = current_rule

    @api.model
    def _prepare_rule_vals(self, vals):
        if "custom_rrule" in vals or "rrule" in vals or not RULE_FIELDS & vals.keys():
            return vals
        return {**vals, "custom_rrule": False}

    def _inverse_rrule(self) -> None:
        for recurrence in self:
            if _debug.logic.enabled and not recurrence.rrule:
                _debug.logic(
                    "recurrence.rrule_inverse_skipped",
                    record=recurrence.id,
                    reason="empty_rule",
                )
            if recurrence.rrule:
                values = self._rrule_parse(
                    recurrence.rrule,
                    recurrence.dtstart,
                    recurrence._get_timezone(),
                    allday=recurrence._is_allday(),
                )
                _debug.pipeline(
                    "recurrence.rrule_inverse",
                    record=recurrence.id,
                    keys=",".join(sorted(values)),
                )
                recurrence.with_context(dont_notify=True).write(values)

    def _rrule_serialize(self):
        if self.repeat_interval <= 0:
            _debug.logic(
                "recurrence.serialize_rejected",
                record=self.id,
                reason="interval_not_positive",
            )
            raise UserError(self.env._("The interval cannot be negative."))
        if self.repeat_type == "count" and self.repeat_number <= 0:
            _debug.logic(
                "recurrence.serialize_rejected",
                record=self.id,
                reason="count_not_positive",
            )
            raise UserError(self.env._("The number of repetitions cannot be negative."))
        if (
            self.repeat_type == "count"
            and self.repeat_number > MAX_RECURRENT_OCCURRENCES
        ):
            _debug.logic(
                "recurrence.serialize_rejected",
                record=self.id,
                reason="count_over_maximum",
                count=self.repeat_number,
                maximum=MAX_RECURRENT_OCCURRENCES,
            )
            raise UserError(
                self.env._(
                    "A recurrence cannot repeat more than %(maximum)s times.",
                    maximum=MAX_RECURRENT_OCCURRENCES,
                )
            )

        if self.repeat_type == "until" and not self.repeat_until:
            _debug.logic(
                "recurrence.serialize_rejected",
                record=self.id,
                reason="until_without_date",
            )
            raise UserError(
                self.env._("A recurrence that repeats until a date needs that date.")
            )

        if not self.repeat_unit:
            _debug.logic("recurrence.serialize.empty", record=self.id)
            return ""
        return self._rrule_value(
            str(self._get_rrule(dtstart=self._get_local_start(), bounded=False))
        )

    @api.model
    def _rrule_value(self, rule_str):
        lines = [line.strip() for line in (rule_str or "").splitlines() if line.strip()]
        for line in lines:
            if line.startswith("RRULE:"):
                return line[len("RRULE:") :]
        _debug.logic("recurrence.rrule_value_bare", lines=len(lines))
        return next((line for line in lines if not line.startswith("DTSTART:")), "")

    @api.model
    def _rrule_parse(self, rule_str, date_start, tz=None, allday=False):
        data = {}
        day_list = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        stripped = len(rule_str)
        rule_str = (
            re.sub(r";?X-[-\w]+=[^;:]*", "", rule_str).replace(":;", ":").lstrip(":;")
        )
        stripped -= len(rule_str)

        utc_marked = "Z" in rule_str
        local_start = date_start
        if (
            tz
            and not allday
            and isinstance(date_start, datetime)
            and not date_start.tzinfo
        ):
            local_start = date_start.replace(tzinfo=UTC).astimezone(tz)
        rule_start = local_start
        if rule_start and not utc_marked and local_start is not date_start:
            rule_start = rule_start.replace(tzinfo=None)
        elif rule_start and utc_marked and not rule_start.tzinfo:
            rule_start = rule_start.replace(tzinfo=UTC)
        rule = rrule.rrulestr(rule_str, dtstart=rule_start)
        _debug.logic(
            "recurrence.rrule_parsed",
            freq=rule._freq,
            interval=rule._interval,
            count=rule._count,
            until=rule._until is not None,
            byweekday=len(rule._byweekday or ()),
            bynweekday=len(rule._bynweekday or ()),
            bymonthday=len(rule._bymonthday or ()),
            x_stripped=stripped,
            utc_marked=utc_marked,
        )

        data["repeat_unit"] = freq_to_select(rule._freq)
        data["repeat_number"] = rule._count
        data["repeat_interval"] = rule._interval
        until = rule._until
        if until and until.tzinfo:
            local_until = until.astimezone(tz or UTC)
            _debug.logic(
                "recurrence.until_localized",
                utc_date=until.astimezone(UTC).date(),
                local_date=local_until.date(),
                tz=str(tz or UTC),
            )
            until = local_until
        data["repeat_until"] = until and until.date()

        weekdays, nweekdays = rule._byweekday, rule._bynweekday
        if (
            rule._freq in (rrule.MONTHLY, rrule.YEARLY)
            and len(rule._bysetpos or ()) == 1
            and len(weekdays or ()) == 1
        ):
            nweekdays = ((weekdays[0], rule._bysetpos[0]),)
            weekdays = None
            _debug.logic("recurrence.setpos_as_nth_weekday", nth=rule._bysetpos[0])
        if rule._freq == rrule.YEARLY:
            data["month_by"] = "date"
            start_month = local_start and local_start.month
            if (
                not weekdays
                and len(nweekdays or ()) == 1
                and str(nweekdays[0][1]) in dict(BYDAY_SELECTION)
                and rule._bymonth == (start_month,)
            ):
                data["month_by"] = "day"
                data["weekday"] = day_list[nweekdays[0][0]].upper()
                data["byday"] = str(nweekdays[0][1])
                _debug.logic(
                    "recurrence.yearly_nth_weekday_parsed",
                    month=start_month,
                    weekday=data["weekday"],
                    byday=data["byday"],
                )
            elif weekdays or nweekdays:
                _debug.logic(
                    "recurrence.rrule_parts_dropped",
                    freq="yearly",
                    parts=["byweekday" if weekdays else "bynweekday"],
                    bymonth=rule._bymonth,
                    start_month=start_month,
                    reason="yearly_repeats_on_start_date",
                )
            weekdays = nweekdays = None
        if (
            rule._freq == rrule.MONTHLY
            and weekdays
            and (rule._interval != 1 or rule._bysetpos)
        ):
            _debug.logic(
                "recurrence.rrule_parts_dropped",
                freq="monthly",
                parts=["byweekday", *(["bysetpos"] if rule._bysetpos else [])],
                interval=rule._interval,
                reason="monthly_repeats_on_start_date",
            )
            weekdays = None
            data["month_by"] = "date"
            if local_start:
                data["day"] = local_start.day

        if weekdays:
            for weekday in day_list:
                data[weekday] = False
            for weekday_index in weekdays:
                weekday = rrule.weekday(weekday_index)
                data[weekday_to_field(weekday.weekday)] = True
                data["repeat_unit"] = "week"

        if nweekdays:
            data["weekday"] = day_list[next(iter(nweekdays))[0]].upper()
            data["byday"] = str(next(iter(nweekdays))[1])
            data["month_by"] = "day"
            data["repeat_unit"] = "month"

        last_day = (
            data["repeat_unit"] == "month"
            and not rule._bymonthday
            and rule._bynmonthday == (LAST_DAY_OF_MONTH,)
        )
        if rule._bymonthday and data["repeat_unit"] == "month":
            data["day"] = next(iter(rule._bymonthday))
            data["month_by"] = "date"
        elif last_day:
            data["day"] = LAST_DAY_OF_MONTH
            data["month_by"] = "date"
            _debug.logic("recurrence.last_day_of_month_parsed")
        dropped = [
            part
            for part, present in (
                ("bynmonthday", rule._bynmonthday and not last_day),
                ("bysetpos", len(rule._bysetpos or ()) > 1),
                ("bynweekday", len(nweekdays or ()) > 1),
                (
                    "bymonthday",
                    data["repeat_unit"] == "month" and len(rule._bymonthday or ()) > 1,
                ),
            )
            if present
        ]
        if dropped:
            _debug.logic(
                "recurrence.rrule_parts_dropped",
                freq=data["repeat_unit"],
                parts=dropped,
                reason="not_representable",
            )

        if data.get("repeat_until"):
            data["repeat_type"] = "until"
        elif data.get("repeat_number"):
            data["repeat_type"] = "count"
        else:
            data["repeat_type"] = "forever"
        if data["repeat_unit"] == "week":
            data["week_start"] = WEEKDAY_SELECTION[rule._wkst][0]
        data["custom_rrule"] = self._get_custom_rrule(rule, data)
        return data

    @api.model
    def _get_custom_rrule(self, rule, values) -> str | None:
        pattern = rule.replace(count=None, until=None)
        expected = list(islice(pattern, MAX_RECURRENT_OCCURRENCES))
        options = self.new(
            {**values, "repeat_type": "forever", "custom_rrule": False}
        )._get_rrule(dtstart=rule._dtstart, bounded=False)
        if list(islice(options, len(expected))) == expected:
            return None
        _debug.logic("recurrence.custom_rule_kept", freq=rule._freq)
        return self._rrule_value(str(pattern))

    def _default_week_start(self):
        lang = get_lang(self.env, self.env.user.lang)
        return WEEKDAY_SELECTION[int(lang.week_start) - 1][0]

    def _get_week_start(self):
        return getattr(rrule, RRULE_WEEKDAYS[self.week_start])

    def _get_start_of_period(self, dt):
        if self.custom_rrule:
            start = dt
        elif self.repeat_unit == "week":
            start = dt + relativedelta(weekday=self._get_week_start()(-1))
        elif self.repeat_unit == "month":
            start = dt + relativedelta(day=1)
        else:
            start = dt
        if isinstance(dt, datetime):
            tz = self._get_timezone()
            dst_dt = dt.replace(tzinfo=tz).dst()
            dst_start = start.replace(tzinfo=tz).dst()
            if dst_dt != dst_start:
                _debug.logic(
                    "recurrence.period_start_kept",
                    record=self.id,
                    unit=self.repeat_unit,
                    reason="dst_boundary",
                )
                start = dt
        return start

    def _range_calculation(self, start, duration):
        self.check_singleton()

        def only_future(ranges):
            return {
                (occurrence_start, occurrence_stop)
                for occurrence_start, occurrence_stop in ranges
                if occurrence_start.date() >= start.date()
                and occurrence_stop.date() >= start.date()
            }

        with _debug.perf("recurrence.ranges", record=self.id, unit=self.repeat_unit):
            ranges = only_future(self._get_ranges(start, duration))
        original_count = self.repeat_type == "count" and self.repeat_number
        if original_count and len(ranges) < original_count:
            inflated_count = (2 * original_count) - len(ranges)
            past = len(ranges)
            ranges = only_future(
                self._get_ranges(start, duration, count=inflated_count)
            )
            _debug.logic(
                "recurrence.ranges_inflated",
                record=self.id,
                wanted=original_count,
                first_pass=past,
                inflated_count=inflated_count,
                got=len(ranges),
            )
        return ranges

    def _get_ranges(self, start, occurrence_duration, count=None):
        return (
            (occurrence_start, occurrence_start + occurrence_duration)
            for occurrence_start in self._get_occurrences(start, count=count)
        )

    def _get_timezone(self):
        return timezone(self.event_tz or self.env.context.get("tz") or "UTC")

    def _get_occurrences(self, dtstart, count=None):
        self.check_singleton()
        if self._is_allday():
            _debug.logic(
                "recurrence.occurrences", record=self.id, allday=True, count=count
            )
            return self._get_rrule(
                dtstart=self._get_start_of_period(dtstart), count=count
            )

        tz = self._get_timezone()
        _debug.logic(
            "recurrence.occurrences",
            record=self.id,
            allday=False,
            tz=str(tz),
            count=count,
        )
        local_start = dtstart.replace(tzinfo=UTC).astimezone(tz).replace(tzinfo=None)
        period_start = self._get_start_of_period(local_start)
        _debug.logic(
            "recurrence.period_start",
            record=self.id,
            utc_start=dtstart,
            local_start=local_start,
            period_start=period_start,
        )
        occurences = self._get_rrule(dtstart=period_start, count=count)

        return (wall_to_utc(occurrence, tz) for occurrence in occurences)

    def _get_week_days(self):
        return tuple(
            rrule.weekday(weekday_index)
            for weekday_index, weekday in {
                rrule.MO.weekday: self.mon,
                rrule.TU.weekday: self.tue,
                rrule.WE.weekday: self.wed,
                rrule.TH.weekday: self.thu,
                rrule.FR.weekday: self.fri,
                rrule.SA.weekday: self.sat,
                rrule.SU.weekday: self.sun,
            }.items()
            if weekday
        )

    def _get_nth_weekday(self):
        return getattr(rrule, RRULE_WEEKDAYS[self.weekday])(int(self.byday))

    def _get_rrule(self, dtstart=None, bounded=True, count=None):
        self.check_singleton()
        termination = self._get_rrule_termination(bounded, count)
        if self.custom_rrule:
            return rrule.rrulestr(self.custom_rrule, dtstart=dtstart).replace(
                **termination
            )
        freq = self.repeat_unit
        rrule_params = {
            "dtstart": dtstart,
            "interval": self.repeat_interval,
        }
        if freq == "month" and self.month_by == "date":
            rrule_params["bymonthday"] = self.day
        elif freq == "month" and self.month_by == "day":
            rrule_params["byweekday"] = self._get_nth_weekday()
        elif freq == "year" and self.month_by == "day":
            if dtstart:
                rrule_params["bymonth"] = dtstart.month
                rrule_params["byweekday"] = self._get_nth_weekday()
            _debug.logic(
                "recurrence.yearly_nth_weekday",
                record=self.id,
                month=dtstart and dtstart.month,
                weekday=self.weekday,
                byday=self.byday,
                anchored=bool(dtstart),
            )
        elif freq == "week":
            weekdays = self._get_week_days()
            if not weekdays:
                _debug.logic(
                    "recurrence.rrule_rejected", record=self.id, reason="no_weekday"
                )
                raise UserError(
                    self.env._("You have to choose at least one day in the week")
                )
            rrule_params["byweekday"] = weekdays
            rrule_params["wkst"] = self._get_week_start()

        _debug.logic(
            "recurrence.rrule_built",
            record=self.id,
            freq=freq,
            repeat_type=self.repeat_type,
            bounded=bounded,
            count=termination["count"],
            has_until=termination["until"] is not None,
        )
        return rrule.rrule(freq_to_rrule(freq), **rrule_params, **termination)

    def _get_rrule_termination(self, bounded, count) -> dict:
        termination = {"count": None, "until": None}
        if self.repeat_type == "count":
            effective_count = self.repeat_number if count is None else count
            termination["count"] = (
                min(effective_count, MAX_RECURRENT_OCCURRENCES)
                if bounded
                else effective_count
            )
        elif self.repeat_type == "forever" and bounded:
            termination["count"] = MAX_RECURRENT_OCCURRENCES
        elif self.repeat_type == "until":
            termination["until"] = datetime.combine(self.repeat_until, time.max)
        return termination

    def _reconcile_events(self, ranges) -> tuple:
        ranges = set(ranges)

        synced_events = self.calendar_event_ids.filtered(lambda e: e._range() in ranges)

        existing_ranges = {event._range() for event in synced_events}
        ranges_to_create = (
            event_range for event_range in ranges if event_range not in existing_ranges
        )
        return synced_events, ranges_to_create

    def _select_new_base_event(self) -> None:
        for recurrence in self:
            recurrence.base_event_id = recurrence._get_first_event()

    def _apply_recurrence(
        self,
        specific_values_creation=None,
        no_send_edit=False,
        generic_values_creation=None,
    ):
        event_vals = []
        keep = self.env["calendar.event"]
        if specific_values_creation is None:
            specific_values_creation = {}

        for recurrence in self.filtered("base_event_id"):
            recurrence.calendar_event_ids |= recurrence.base_event_id
            event = recurrence.base_event_id
            duration = event.stop - event.start
            if specific_values_creation:
                ranges = {
                    (x[1], x[2])
                    for x in specific_values_creation
                    if x[0] == recurrence.id
                }
            else:
                ranges = recurrence._range_calculation(event.start, duration)

            events_to_keep, ranges = recurrence._reconcile_events(ranges)
            keep |= events_to_keep
            [base_values] = event.copy_data()
            values = []
            for start, stop in ranges:
                value = dict(
                    base_values,
                    start=start,
                    stop=stop,
                    recurrence_id=recurrence.id,
                    follow_recurrence=True,
                )
                if (recurrence.id, start, stop) in specific_values_creation:
                    value.update(specific_values_creation[(recurrence.id, start, stop)])
                if generic_values_creation and recurrence.id in generic_values_creation:
                    value.update(generic_values_creation[recurrence.id])
                values += [value]
            event_vals += values

        events = self.calendar_event_ids - keep
        detached_events = self._detach_events(events)
        context = {
            **clean_context(self.env.context),
            "no_mail_to_attendees": True,
            "mail_create_nolog": True,
        }
        self.env["calendar.event"].with_context(context).create(event_vals)
        return detached_events

    def _schedule_next_occurrence_alarm(self, recurrence_update=False) -> None:
        now = self.env.context.get("date") or fields.Datetime.now()
        self.env["calendar.event"].flush_model(fnames=["recurrence_id", "start"])
        if not self.calendar_event_ids.ids:
            return

        self.env.cr.execute(
            """
            SELECT DISTINCT ON (recurrence_id) id event_id, recurrence_id
                    FROM calendar_event
                   WHERE start > %s
                     AND id = ANY(%s)
                ORDER BY recurrence_id,start ASC;
        """,
            (now, list(self.calendar_event_ids.ids)),
        )
        result = self.env.cr.dictfetchall()
        if not result:
            return
        events = self.env["calendar.event"].browse(
            value["event_id"] for value in result
        )
        triggers_by_events = cast("CalendarEvent", events)._setup_alarms()
        for vals in result:
            trigger_id = triggers_by_events.get(vals["event_id"])
            if not trigger_id:
                continue
            recurrence = self.env["calendar.recurrence"].browse(vals["recurrence_id"])
            cast("CalendarRecurrence", recurrence).trigger_id = trigger_id

    def _split_from(self, event, recurrence_values=None):
        if recurrence_values is None:
            recurrence_values = {}
        event.check_singleton()
        if not self:
            return None
        [values] = self.copy_data()
        detached_events = self._stop_at(event)

        repeat_number = recurrence_values.get("repeat_number", 0) or len(
            detached_events
        )
        return self.create(
            {
                **values,
                **recurrence_values,
                "base_event_id": event.id,
                "calendar_event_ids": [Command.set(detached_events.ids)],
                "repeat_number": max(repeat_number, 1),
            }
        )

    def _stop_at(self, event):
        self.check_singleton()
        events = self._get_events_from(event.start)
        detached_events = self._detach_events(events)
        if not self.calendar_event_ids:
            self.with_context(archive_on_error=True).unlink()
            return detached_events

        if event.allday:
            until = self._get_start_of_period(event.start_date)
        else:
            local_start = (
                event.start.replace(tzinfo=UTC)
                .astimezone(self._get_timezone())
                .replace(tzinfo=None)
            )
            until = self._get_start_of_period(local_start).date()
        _debug.logic(
            "recurrence.stopped",
            recurrence=self.id,
            event=event.id,
            allday=event.allday,
            until=until - relativedelta(days=1),
            detached=len(detached_events),
        )
        self.write(
            {
                "repeat_type": "until",
                "repeat_until": until - relativedelta(days=1),
            }
        )
        return detached_events

    @api.model
    def _detach_events(self, events):
        events.with_context(dont_notify=True).write(
            {
                "recurrence_id": False,
                "recurrency": True,
            }
        )
        return events

    def _write_events(self, values, dtstart=None):
        events = self._get_events_from(dtstart) if dtstart else self.calendar_event_ids
        return events.with_context(no_mail_to_attendees=True, dont_notify=True).write(
            dict(values, recurrence_update="this")
        )

    def _get_first_event(self, include_outliers=False):
        if not self.calendar_event_ids:
            return self.env["calendar.event"]
        events = self.calendar_event_ids.sorted("start")
        if not include_outliers:
            events -= self._get_outliers()
        return events[:1]

    def _get_outliers(self):
        synced_events = self.env["calendar.event"]
        for recurrence in self:
            if recurrence.calendar_event_ids:
                synced_events |= recurrence._get_synced_events()
        return self.calendar_event_ids - synced_events

    def _get_synced_events(self):
        self.check_singleton()
        start = min(self.calendar_event_ids.mapped("start"))
        starts = set(self._get_occurrences(start))
        return self.calendar_event_ids.filtered(lambda e: e.start in starts)

    def _get_events_from(self, dtstart):
        events = self.with_context(active_test=False).calendar_event_ids
        return (
            self.env["calendar.event"]
            .with_context(active_test=False)
            .search([("id", "in", events.ids), ("start", ">=", dtstart)])
        )

    def _is_allday(self) -> bool:
        score: int = sum(
            1 if e.allday else -1
            for e in cast("CalendarEvent", self.calendar_event_ids)
        )
        return score >= 0

    def _is_event_over(self) -> bool:
        self.check_singleton()
        if not self.calendar_event_ids:
            return False

        now = fields.Datetime.now()
        today = fields.Date.today()

        return all(
            (
                cast("date", event.stop_date) < today
                if event.allday
                else cast("datetime", event.stop) < now
            )
            for event in cast("CalendarEvent", self.calendar_event_ids)
        )

    def _is_video_call_required(self) -> bool:
        self.check_singleton()
        return not self.base_event_id or self.base_event_id._is_video_call_required()
