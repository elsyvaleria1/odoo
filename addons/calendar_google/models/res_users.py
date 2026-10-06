import logging

from odoo import models
from odoo.exceptions import LockError

from odoo.addons.calendar_google.models.mixin_google_calendar_sync import (
    google_calendar_connection,
)
from odoo.addons.calendar_google.utils.calendar_google import (
    GoogleCalendarService,
    InvalidSyncToken,
)

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
        results = self._sync_request(calendar_service)
        if not results or (
            not results.get("events") and not self._has_pending_odoo_records()
        ):
            return False
        events, default_reminders, full_sync = results.values()
        # Google -> Odoo
        send_updates = not full_sync
        events.clear_type_ambiguity(self.env)
        recurrences = events.filter(lambda e: e.is_recurrence())

        # We apply Google updates only if their write date is later than the write date in Odoo.
        # It's possible that multiple updates affect the same record, maybe not directly.
        # To handle this, we preserve the write dates in Odoo before applying any updates,
        # and use these dates instead of the current live dates.
        odoo_events = self.env["calendar.event"].browse(
            (events - recurrences).odoo_ids(self.env)
        )
        odoo_recurrences = self.env["calendar.recurrence"].browse(
            recurrences.odoo_ids(self.env)
        )
        recurrences_write_dates = {r.id: r.write_date for r in odoo_recurrences}
        events_write_dates = {e.id: e.write_date for e in odoo_events}
        synced_recurrences = self.env["calendar.recurrence"]._sync_google2odoo(
            recurrences, recurrences_write_dates
        )
        synced_events = self.env["calendar.event"]._sync_google2odoo(
            events - recurrences,
            events_write_dates,
            default_reminders=default_reminders,
        )

        # Odoo -> Google
        recurrences = self.env["calendar.recurrence"]._get_records_to_sync(
            full_sync=full_sync
        )
        recurrences -= synced_recurrences
        recurrences.with_context(send_updates=send_updates)._sync_odoo2google(
            calendar_service
        )
        synced_events |= recurrences.calendar_event_ids - recurrences._get_outliers()
        synced_events |= (
            synced_recurrences.calendar_event_ids - synced_recurrences._get_outliers()
        )
        events = self.env["calendar.event"]._get_records_to_sync(full_sync=full_sync)
        (events - synced_events).with_context(
            send_updates=send_updates
        )._sync_odoo2google(calendar_service)

        return bool(results) and (
            bool(events | synced_events) or bool(recurrences | synced_recurrences)
        )

    def _sync_request(self, calendar_service) -> dict | None:
        if self._calendar_sync_status("google") != "sync_active":
            return None
        self.check_singleton()
        account = self._calendar_sync_account("google")
        # don't attempt to sync when another sync is already in progress, as we wouldn't be
        # able to commit the transaction anyway (row is locked)
        try:
            account.lock_for_update(allow_referencing=True)
        except LockError:
            _logger.info("skipping calendar sync, locked account of %s", self.login)
            return None

        full_sync = not account.sync_token
        with google_calendar_connection(self) as connection:
            try:
                events, next_sync_token, default_reminders = (
                    calendar_service.get_events(
                        account.sync_token, connection=connection
                    )
                )
            except InvalidSyncToken:
                events, next_sync_token, default_reminders = (
                    calendar_service.get_events(connection=connection)
                )
                full_sync = True
        if next_sync_token:
            account.sync_token = next_sync_token
        return {
            "events": events,
            "default_reminders": default_reminders,
            "full_sync": full_sync,
        }

    def _calendar_sync_run(self, code: str) -> bool:
        if code != "google":
            return super()._calendar_sync_run(code)
        return self._sync_google_calendar(GoogleCalendarService(self.env))

    def _calendar_sync_restart(self, code: str) -> None:
        super()._calendar_sync_restart(code)
        if code == "google":
            self.env["calendar.recurrence"]._restart_google_sync()
            self.env["calendar.event"]._restart_google_sync()
