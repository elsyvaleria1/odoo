from dateutil import rrule

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.calendar.models.calendar_recurrence import (
    LAST_DAY_OF_MONTH,
    RRULE_WEEKDAYS,
    weekday_to_field,
)

_debug = DebugLog(__name__)

MICROSOFT_SIMPLE_PATTERN = {"day": "daily", "week": "weekly"}
MICROSOFT_PERIOD_PATTERN = {"month": "Monthly", "year": "Yearly"}
MICROSOFT_WEEKDAYS = {
    "mon": "monday",
    "tue": "tuesday",
    "wed": "wednesday",
    "thu": "thursday",
    "fri": "friday",
    "sat": "saturday",
    "sun": "sunday",
}
MICROSOFT_INDEX = {
    "1": "first",
    "2": "second",
    "3": "third",
    "4": "fourth",
    "-1": "last",
}
MICROSOFT_RELATIVE_FREQ = {
    "relativeMonthly": rrule.MONTHLY,
    "relativeYearly": rrule.YEARLY,
}


class CalendarRecurrence(models.Model):
    _name = "calendar.recurrence"
    _inherit = ["calendar.recurrence", "mixin.microsoft.calendar.sync"]

    def _compute_rrule(self) -> None:
        for recurrence in self:
            if recurrence.rrule != recurrence._rrule_serialize():
                recurrence.write({"rrule": recurrence._rrule_serialize()})

    def _inverse_rrule(self) -> None:
        for recurrence in self.filtered("rrule"):
            values = self._rrule_parse(
                recurrence.rrule,
                recurrence.dtstart,
                tz=recurrence._get_timezone(),
                allday=recurrence._is_allday(),
            )
            recurrence.with_context(
                dont_notify=True, microsoft_calendar_syncing=True
            ).write(values)

    def _get_fields_microsoft_synced(self):
        return {"rrule"} | self.env["calendar.event"]._get_fields_microsoft_synced()

    def _has_base_event_time_fields_changed(self, new) -> bool:

        def _convert(value, to_convert):
            return value.date() if to_convert else value

        old = (
            self.base_event_id
            and self.base_event_id.read(["start", "stop", "allday"])[0]
        )
        return bool(
            old
            and (
                old["allday"] != new["allday"]
                or any(
                    _convert(new[f], new["allday"]) != _convert(old[f], old["allday"])
                    for f in ("start", "stop")
                )
            )
        )

    def _write_from_microsoft(self, microsoft_event, vals) -> None:
        current_rrule = self.rrule
        vals["event_tz"] = microsoft_event.start.get("timeZone")
        self.write(vals)
        new_event_values = self.env["calendar.event"]._microsoft_to_odoo_values(
            microsoft_event
        )
        if self._has_base_event_time_fields_changed(new_event_values) and (
            new_event_values["start"] >= self.base_event_id.start
        ):
            base_event_id = self.base_event_id
            (self.calendar_event_ids - base_event_id)._microsoft_forget()
            (self.calendar_event_ids - base_event_id).unlink()
            base_event_id.with_context(
                dont_notify=True, microsoft_calendar_syncing=True
            ).write(new_event_values)
            if self.rrule == current_rrule:
                self.with_context(
                    dont_notify=True, microsoft_calendar_syncing=True
                )._apply_recurrence()
        else:
            time_fields = (
                self.env["calendar.event"]._get_fields_time()
                | self.env["calendar.event"]._get_fields_recurrent()
            )
            self.with_context(
                dont_notify=True, microsoft_calendar_syncing=True
            )._write_events(
                {
                    field: value
                    for field, value in new_event_values.items()
                    if field not in time_fields
                }
            )
        if self.rrule != current_rrule:
            detached_events = self._apply_recurrence()
            detached_events._microsoft_forget()
            detached_events.unlink()

    @api.model
    def _microsoft_to_odoo_values(self, microsoft_recurrence, event=None):
        values = microsoft_recurrence.get_recurrence()
        if values:
            values["custom_rrule"] = self._get_custom_rrule_from_microsoft(
                microsoft_recurrence.recurrence["pattern"]
            )
        return values

    @api.model
    def _get_custom_rrule_from_microsoft(self, pattern) -> str | None:
        days = {day[:3] for day in pattern.get("daysOfWeek") or ()}
        freq = MICROSOFT_RELATIVE_FREQ.get(pattern["type"])
        if not freq or not 1 < len(days) < len(MICROSOFT_WEEKDAYS):
            return None
        position = {name: index for index, name in MICROSOFT_INDEX.items()}
        rule = rrule.rrule(
            freq,
            interval=pattern["interval"],
            bysetpos=int(position[pattern["index"]]),
            byweekday=[getattr(rrule, RRULE_WEEKDAYS[day.upper()]) for day in days],
            bymonth=pattern["month"] if freq == rrule.YEARLY else None,
        )
        return self._rrule_value(str(rule))

    def _get_microsoft_custom_pattern(self) -> dict | None:
        self.check_singleton()
        rule = rrule.rrulestr(
            self.custom_rrule, dtstart=self._get_local_start() or fields.Datetime.now()
        )
        period = {rrule.MONTHLY: "Monthly", rrule.YEARLY: "Yearly"}.get(rule._freq)
        given = set(rule._original_rule)
        positions = rule._bysetpos or ()
        weekdays = rule._byweekday or ()
        yearly = rule._freq == rrule.YEARLY
        if (
            not period
            or given - {"byweekday", "bysetpos", "bymonth"}
            or ("bymonth" in given) != yearly
            or (yearly and len(rule._bymonth) != 1)
            or rule._bynweekday
            or len(weekdays) < 2
            or len(positions) != 1
            or str(positions[0]) not in MICROSOFT_INDEX
        ):
            return None
        pattern = {
            "type": "relative" + period,
            "interval": rule._interval,
            "daysOfWeek": [
                MICROSOFT_WEEKDAYS[weekday_to_field(day)] for day in sorted(weekdays)
            ],
            "index": MICROSOFT_INDEX[str(positions[0])],
        }
        if yearly:
            pattern["month"] = rule._bymonth[0]
        return pattern

    def _get_microsoft_pattern(self):
        self.check_singleton()
        if self.custom_rrule:
            return self._get_microsoft_custom_pattern()
        pattern = {"interval": self.repeat_interval}
        if self.repeat_unit in MICROSOFT_SIMPLE_PATTERN:
            pattern["type"] = MICROSOFT_SIMPLE_PATTERN[self.repeat_unit]
        elif (
            self.repeat_unit == "month"
            and self.month_by == "date"
            and self.day == LAST_DAY_OF_MONTH
        ):
            pattern["type"] = "relativeMonthly"
            pattern["daysOfWeek"] = list(MICROSOFT_WEEKDAYS.values())
            pattern["index"] = MICROSOFT_INDEX[str(LAST_DAY_OF_MONTH)]
            _debug.logic("microsoft.recurrence_last_day_as_relative", record=self.id)
        else:
            relative = self.month_by == "day"
            period = MICROSOFT_PERIOD_PATTERN.get(self.repeat_unit)
            pattern["type"] = (
                period and ("relative" if relative else "absolute") + period
            )
            if relative:
                pattern["daysOfWeek"] = [MICROSOFT_WEEKDAYS[self.weekday.lower()]]
                pattern["index"] = MICROSOFT_INDEX[self.byday]
            elif self.repeat_unit == "month":
                pattern["dayOfMonth"] = self.day
            if self.repeat_unit == "year":
                local_start = self._get_local_start() or fields.Datetime.now()
                pattern["month"] = local_start.month
                if not relative:
                    pattern["dayOfMonth"] = local_start.day
                _debug.logic(
                    "microsoft.recurrence_yearly_pattern",
                    record=self.id,
                    relative=relative,
                    month=local_start.month,
                )
        if self.repeat_unit == "week":
            pattern["daysOfWeek"] = [
                name for field, name in MICROSOFT_WEEKDAYS.items() if self[field]
            ]
            pattern["firstDayOfWeek"] = MICROSOFT_WEEKDAYS[self.week_start.lower()]
        return pattern

    def _microsoft_values(
        self, fields_to_sync, initial_values=(), series_master_id=None
    ):
        return self.base_event_id._microsoft_values(
            fields_to_sync,
            initial_values={**dict(initial_values), "type": "seriesMaster"},
        )

    def _microsoft_refusal(self):
        self.check_singleton()
        if self.custom_rrule and not self._get_microsoft_custom_pattern():
            return self.env._(
                "Outlook cannot hold the rule of this series, %(rule)s.",
                rule=self.custom_rrule,
            )
        for event in self.calendar_event_ids.filtered("active"):
            if refusal := event._microsoft_refusal():
                return refusal
        return None

    def _split_from(self, event, recurrence_values=None):
        new_recurrence = super()._split_from(event, recurrence_values)
        if new_recurrence:
            new_recurrence.base_event_id._microsoft_tombstone()
        return new_recurrence
