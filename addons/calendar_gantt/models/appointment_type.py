from datetime import UTC, datetime

from odoo import models


class AppointmentType(models.Model):
    _inherit = "appointment.type"

    def _get_booking_view_types(self) -> list:
        return ["gantt", *super()._get_booking_view_types()]

    def _get_calendar_booking_action(self, schedule_based_on):
        action = super()._get_calendar_booking_action(schedule_based_on)
        offers = self or self.search([("schedule_based_on", "=", schedule_based_on)])
        action["context"]["default_scale"] = offers._get_gantt_scale()
        return action

    def action_calendar_meetings(self, calendar_event_domain=False):
        action = super().action_calendar_meetings(calendar_event_domain)
        action["context"]["default_start_date"] = datetime.today()
        return action

    def action_calendar_event_view_request(self):
        action = super().action_calendar_event_view_request()
        action["context"]["default_start_date"] = action["context"]["initial_date"]
        return action

    def _get_gantt_scale(self) -> str:
        """Return the default scale to show related meetings in gantt.

        :rtype: str
        """
        # The scale is derived from the last available meeting, to show a relevant time frame:
        # if that meeting is in the current week, a week suffices instead of an entire year.
        now = datetime.now(UTC)
        last_meeting_values = self.env["calendar.event"].search_read(
            [
                ("appointment_type_id", "in", self.ids),
                ("resource_ids", "!=", False),
                ("stop", ">=", now.date()),
            ],
            ["stop"],
            limit=1,
            order="stop desc",
        )
        last_meeting_end = (
            last_meeting_values[0]["stop"] if last_meeting_values else False
        )
        if not last_meeting_end or now.date() == last_meeting_end.date():
            return "day"
        # Compare the full ISO (year, week) pair: the ISO week number alone repeats
        # every year, and gating the week test on `same_month` used to send two
        # consecutive days that straddle a month boundary all the way to 'year'.
        same_week = now.isocalendar()[:2] == last_meeting_end.isocalendar()[:2]
        if same_week:
            return "week"
        if now.year == last_meeting_end.year and now.month == last_meeting_end.month:
            return "month"
        return "year"
