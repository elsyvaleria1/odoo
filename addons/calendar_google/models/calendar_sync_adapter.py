from dateutil.parser import parse

from odoo import api, models

from odoo.addons.calendar_google.utils.calendar_google import (
    GoogleCalendarService,
    InvalidSyncToken,
)
from odoo.addons.calendar_sync.remote import (
    CalendarSyncError,
    ErrorKind,
    RemoteChanges,
    RemoteEvent,
    RemoteKind,
)


class CalendarSyncAdapterGoogle(models.AbstractModel):
    _name = "calendar.sync.adapter.google"
    _inherit = "calendar.sync.adapter"
    _description = "Google Calendar Synchronization Adapter"

    @api.model
    def _list_changes(self, account, token):
        connection = account.user_id._calendar_sync_connection("google")
        try:
            events, next_token, default_reminders = GoogleCalendarService(
                self.env
            ).get_events(token, connection=connection)
        except InvalidSyncToken as error:
            raise CalendarSyncError(ErrorKind.TOKEN_INVALID) from error
        return self._changes(events, default_reminders, next_token, full=not token)

    @api.model
    def _changes(self, gevents, default_reminders=(), next_token=None, full=False):
        """Google's events as the engine reads them: the series first, then
        the events, each rescheduled instance followed by the cancellation of
        the instance it replaces."""
        series, events = [], []
        for gevent in gevents:
            remote = self._remote(gevent, default_reminders)
            if remote.kind == RemoteKind.SERIES:
                series.append(remote)
                continue
            events.append(remote)
            # Google gives an instance of a split series (ID_RANGE) a new id
            # (ID_TIMESTAMP) when it is rescheduled: the old one is gone
            if (
                not remote.cancelled
                and not gevent.is_recurrence_follower()
                and (replaced := gevent.full_recurring_event_id())
                and replaced != gevent.id
            ):
                events.append(RemoteEvent(replaced, cancelled=True))
        return RemoteChanges(tuple(series + events), next_token, full)

    @api.model
    def _remote(self, gevent, default_reminders) -> RemoteEvent:
        cancelled = gevent.is_cancelled()
        return RemoteEvent(
            gevent.id,
            # a cancelled item says nothing of being a series: its link does
            kind=(
                RemoteKind.SERIES
                if not cancelled and gevent.is_recurrence()
                else RemoteKind.SINGLE
            ),
            universal_id=gevent.iCalUID,
            cancelled=cancelled,
            updated=gevent.updated and parse(gevent.updated),
            etag=gevent.etag,
            odoo_hint=gevent._meta_odoo_id(self.env.cr.dbname),
            payload={"event": gevent, "default_reminders": default_reminders},
        )

    @api.model
    def _odoo_values(self, remote, model_name, record):
        return dict(
            self.env["calendar.event"]._odoo_values(
                remote.payload["event"],
                remote.payload["default_reminders"],
                event=record,
            ),
            need_sync=False,
        )

    @api.model
    def _apply_series(self, account, master, occurrences, recurrence):
        gevent = master.payload["event"]
        Recurrence = self.env["calendar.recurrence"].with_context(
            dont_notify=True, google_calendar_syncing=True
        )
        values = dict(Recurrence._odoo_values(gevent), need_sync=False)
        if recurrence:
            recurrence.with_env(Recurrence.env)._write_from_google(gevent, values)
        else:
            recurrence = Recurrence._create_from_google(gevent, [values])
        return recurrence, {}
