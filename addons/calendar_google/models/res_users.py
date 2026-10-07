import logging

from odoo import models

from odoo.addons.calendar_google.utils.calendar_google import GoogleCalendarService

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    def _has_pending_odoo_records(self) -> bool:
        """Returns True if sync is active and there are records to be synchronized to Google."""
        if self._calendar_sync_status("google") != "sync_active":
            return False
        pending_events = self.env["calendar.event"]._check_any_records_to_sync()
        pending_recurrences = self.env[
            "calendar.recurrence"
        ]._check_any_records_to_sync()
        return bool(pending_events or pending_recurrences)

    def _sync_google_calendar(self, calendar_service: GoogleCalendarService) -> bool:
        self.check_singleton()
        account = self._calendar_sync_account("google")._as_engine()
        read = account._read()
        if read is None:
            return False
        changes, applied = read
        if not changes.events and not self._has_pending_odoo_records():
            return False
        Event, Recurrence = self.env["calendar.event"], self.env["calendar.recurrence"]
        synced_events = Event.union(
            *(record for record in applied if record._name == Event._name)
        ).exists()
        synced_recurrences = Recurrence.union(
            *(record for record in applied if record._name == Recurrence._name)
        ).exists()

        # Odoo -> Google
        send_updates = not changes.full
        recurrences = Recurrence._get_records_to_sync(full_sync=changes.full)
        recurrences -= synced_recurrences
        recurrences.with_context(send_updates=send_updates)._sync_odoo2google(
            calendar_service
        )
        synced_events |= recurrences.calendar_event_ids - recurrences._get_outliers()
        synced_events |= (
            synced_recurrences.calendar_event_ids - synced_recurrences._get_outliers()
        )
        events = Event._get_records_to_sync(full_sync=changes.full)
        (events - synced_events).with_context(
            send_updates=send_updates
        )._sync_odoo2google(calendar_service)

        return bool(events | synced_events) or bool(recurrences | synced_recurrences)

    def _calendar_sync_run(self, code: str) -> bool:
        if code != "google":
            return super()._calendar_sync_run(code)
        return self._sync_google_calendar(GoogleCalendarService(self.env))

    def _calendar_sync_restart(self, code: str) -> None:
        super()._calendar_sync_restart(code)
        if code == "google":
            self.env["calendar.recurrence"]._restart_google_sync()
            self.env["calendar.event"]._restart_google_sync()
