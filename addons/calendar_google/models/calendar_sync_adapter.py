import requests
from dateutil.parser import parse

from odoo import api, models

from odoo.addons.calendar_google.utils.calendar_google import (
    TIMEOUT,
    GoogleCalendarService,
)
from odoo.addons.calendar_sync.remote import (
    CalendarSyncError,
    ErrorKind,
    RemoteChanges,
    RemoteEvent,
    RemoteKind,
)
from odoo.addons.calendar_sync.service import InvalidSyncToken


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
        return self.env["calendar.event"]._odoo_values(
            remote.payload["event"],
            remote.payload["default_reminders"],
            event=record,
        )

    @api.model
    def _apply_series(self, account, master, occurrences, recurrence):
        gevent = master.payload["event"]
        Recurrence = self.env["calendar.recurrence"].with_context(
            dont_notify=True, google_calendar_syncing=True
        )
        values = Recurrence._odoo_values(gevent)
        if recurrence:
            recurrence.with_env(Recurrence.env)._write_from_google(gevent, values)
        else:
            recurrence = Recurrence._create_from_google(gevent, [values])
        # the series' instances take their ids from the series' own
        self.env["calendar.sync.link"]._engine()._adopt(account, recurrence, master)
        recurrence.calendar_event_ids._google_link_instances()
        return recurrence, {}

    # -- sending -------------------------------------------------------------

    @api.model
    def _service(self, record=None) -> GoogleCalendarService:
        """The calendar API, mailing the attendees unless the push is quiet or
        the event is over."""
        send_updates = not self.env.context.get("calendar_sync_quiet") and not (
            record and record._is_event_over()
        )
        return GoogleCalendarService(
            self.env(context={**self.env.context, "send_updates": send_updates})
        )

    @api.model
    def _timeout(self) -> int:
        # an edit in the interface waits for its push
        return 3 if self.env.context.get("calendar_sync_interactive") else TIMEOUT

    @api.model
    def _insert(self, account, record, values, insert_id):
        response = self._service(record).insert(
            dict(values, id=insert_id),
            connection=account.user_id._calendar_sync_connection("google"),
            timeout=self._timeout(),
            need_video_call=record._is_video_call_required(),
        )
        response = response or {}
        return RemoteEvent(
            response.get("id") or insert_id,
            universal_id=response.get("iCalUID"),
            etag=response.get("etag"),
            payload={"request": values, "response": response},
        )

    @api.model
    def _patch(self, account, remote_id, record, values):
        # the version Google answers is Odoo's own: a later read of it must
        # not overwrite an edit Odoo still owes
        response = self._service(record).patch(
            remote_id,
            values,
            connection=account.user_id._calendar_sync_connection("google"),
            timeout=self._timeout(),
        )
        return RemoteEvent(remote_id, etag=(response or {}).get("etag"))

    @api.model
    def _delete(self, account, remote_id):
        GoogleCalendarService(
            self.env(context={**self.env.context, "is_recurrence": False})
        ).delete(
            remote_id,
            connection=account.user_id._calendar_sync_connection("google"),
            timeout=self._timeout(),
        )

    @api.model
    def _after_insert(self, account, record, remote):
        if values := record._prepare_post_sync_vals(
            remote.payload["request"], remote.payload["response"]
        ):
            record.with_context(
                calendar_sync_applying="google", dont_notify=True
            ).write(values)
        if record._name == "calendar.recurrence":
            record.calendar_event_ids._google_link_instances()

    @api.model
    def _classify(self, error):
        if not isinstance(error, requests.HTTPError) or error.response is None:
            return super()._classify(error)
        response = error.response
        try:
            message = response.json()["error"].get("message") or response.text
        except ValueError, KeyError, TypeError, AttributeError:
            message = response.text
        status = response.status_code
        if status in (404, 410):
            kind = ErrorKind.GONE
        elif status == 409:
            kind = ErrorKind.CONFLICT
        elif status == 412:
            kind = ErrorKind.PRECONDITION
        elif status == 429 or (status == 403 and "RateLimitExceeded" in response.text):
            kind = ErrorKind.THROTTLED
        elif status == 401:
            kind = ErrorKind.AUTH
        elif status == 403:
            kind = ErrorKind.FORBIDDEN
            if "forbiddenForNonOrganizer" in response.text:
                message = self.env._(
                    "You don't seem to have permission to modify this event on "
                    "Google Calendar."
                )
        elif status == 400:
            kind = ErrorKind.INVALID
        else:
            kind = ErrorKind.TRANSIENT
        return CalendarSyncError(kind, message)

    # -- conversion, Odoo to Google -------------------------------------------

    @api.model
    def _synced_fields(self, model_name):
        return frozenset(self.env[model_name]._get_fields_google_synced())

    @api.model
    def _remote_values(self, record, account):
        return record._google_values()
