from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.base.models.mixin_recurrence_rrule import LAST_DAY_OF_MONTH

_debug = DebugLog(__name__)

# Outlook's words for a recurrence pattern. These were read straight off the
# Odoo value, which worked only while `rrule_type` happened to be spelled the
# way Outlook spells it -- `"daily"`, and `"monthly"` capitalised into
# `absoluteMonthly`. The shared vocabulary says `day` and `month`, so the
# translation is explicit and is the inverse of `MicrosoftEvent.get_recurrence`.
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
                recurrence.rrule, recurrence.dtstart, tz=recurrence._get_timezone()
            )
            recurrence.with_context(
                dont_notify=True, microsoft_calendar_syncing=True
            ).write(values)

    def _get_fields_microsoft_synced(self):
        return {"rrule"} | self.env["calendar.event"]._get_fields_microsoft_synced()

    def _has_base_event_time_fields_changed(self, new) -> bool:
        """
        Indicates if at least one time field of the base event has changed, based
        on provided `new` values.
        Note: for all day event comparison, hours/minutes are ignored.
        """

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
        # event_tz is written on event in Microsoft but on recurrence in Odoo
        vals["event_tz"] = microsoft_event.start.get("timeZone")
        self.write(vals)
        new_event_values = self.env["calendar.event"]._microsoft_to_odoo_values(
            microsoft_event
        )
        # Edge case:  if the base event was deleted manually in 'this' update, skip applying recurrence.
        if self._has_base_event_time_fields_changed(new_event_values) and (
            new_event_values["start"] >= self.base_event_id.start
        ):
            # we need to recreate the recurrence, time_fields were modified.
            base_event_id = self.base_event_id
            # We archive the old events to recompute the recurrence. These events are already deleted on Microsoft side.
            # We can't call _cancel because events without user_id would not be deleted
            (self.calendar_event_ids - base_event_id)._microsoft_forget()
            (self.calendar_event_ids - base_event_id).unlink()
            base_event_id.with_context(
                dont_notify=True, microsoft_calendar_syncing=True
            ).write(new_event_values)
            if self.rrule == current_rrule:
                # if the rrule has changed, it will be recalculated below
                # There is no detached event now
                self.with_context(
                    dont_notify=True, microsoft_calendar_syncing=True
                )._apply_recurrence()
        else:
            time_fields = (
                self.env["calendar.event"]._get_fields_time()
                | self.env["calendar.event"]._get_fields_recurrent()
            )
            # We avoid to write time_fields because they are not shared between events.
            self.with_context(
                dont_notify=True, microsoft_calendar_syncing=True
            )._write_events(
                {
                    field: value
                    for field, value in new_event_values.items()
                    if field not in time_fields
                }
            )
        # We apply the rrule check after the time_field check because the microsoft ids are generated according
        # to base_event start datetime.
        if self.rrule != current_rrule:
            detached_events = self._apply_recurrence()
            detached_events._microsoft_forget()
            detached_events.unlink()

    @api.model
    def _microsoft_to_odoo_values(self, microsoft_recurrence, event=None):
        return microsoft_recurrence.get_recurrence()

    def _get_microsoft_pattern(self):
        self.check_singleton()
        pattern = {"interval": self.repeat_interval}
        if self.repeat_unit in MICROSOFT_SIMPLE_PATTERN:
            pattern["type"] = MICROSOFT_SIMPLE_PATTERN[self.repeat_unit]
        elif (
            self.repeat_unit == "month"
            and self.month_by == "date"
            and self.day == LAST_DAY_OF_MONTH
        ):
            # Outlook has no day number for the end of the month; its own "last
            # day" is the last of any weekday.
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
            pattern["firstDayOfWeek"] = "sunday"
        return pattern

    def _microsoft_values(
        self, fields_to_sync, initial_values=(), series_master_id=None
    ):
        """
        Get values to update the whole Outlook event recurrence.
        (done through the first event of the Outlook recurrence).
        """
        return self.base_event_id._microsoft_values(
            fields_to_sync,
            initial_values={**dict(initial_values), "type": "seriesMaster"},
        )

    def _microsoft_refusal(self):
        self.check_singleton()
        for event in self.calendar_event_ids.filtered("active"):
            if refusal := event._microsoft_refusal():
                return refusal
        return None

    def _split_from(self, event, recurrence_values=None):
        """The base event of the new series may be in Outlook already: it
        leaves, the new series takes its place."""
        new_recurrence = super()._split_from(event, recurrence_values)
        if new_recurrence:
            new_recurrence.base_event_id._microsoft_tombstone()
        return new_recurrence
