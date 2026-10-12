import requests
from dateutil.parser import parse

from odoo import Command, api, models

from odoo.addons.calendar.models.calendar_recurrence import MAX_RECURRENT_OCCURRENCES
from odoo.addons.calendar_microsoft.utils.calendar_microsoft import (
    TIMEOUT,
    MicrosoftCalendarService,
)
from odoo.addons.calendar_microsoft.utils.microsoft_event import MicrosoftEvent
from odoo.addons.calendar_sync.remote import (
    CalendarSyncError,
    ErrorKind,
    RemoteChanges,
    RemoteEvent,
    RemoteKind,
)
from odoo.addons.calendar_sync.service import InvalidSyncToken

ANSWERS = {
    "accepted": "accept",
    "declined": "decline",
    "tentative": "tentativelyAccept",
}


class CalendarSyncAdapterMicrosoft(models.AbstractModel):
    _name = "calendar.sync.adapter.microsoft"
    _inherit = "calendar.sync.adapter"
    _description = "Outlook Calendar Synchronization Adapter"

    @api.model
    def _service(self) -> MicrosoftCalendarService:
        return MicrosoftCalendarService(self.env)

    @api.model
    def _connection(self, account):
        return account.user_id._calendar_sync_connection("microsoft")

    @api.model
    def _timeout(self) -> int:
        if self.env.context.get("calendar_sync_interactive"):
            return self.env["calendar.event"]._get_microsoft_graph_timeout()
        return TIMEOUT

    @api.model
    def _list_changes(self, account, token):
        try:
            events, next_token = self._service().get_events(
                token, connection=self._connection(account)
            )
        except InvalidSyncToken as error:
            raise CalendarSyncError(ErrorKind.TOKEN_INVALID) from error
        return self._changes(events, next_token, full=not token)

    @api.model
    def _changes(self, mevents, next_token=None, full=False) -> RemoteChanges:
        return RemoteChanges(
            tuple(self._remote(mevent) for mevent in mevents), next_token, full
        )

    @api.model
    def _remote(self, mevent) -> RemoteEvent:
        if mevent.is_recurrence():
            kind = RemoteKind.SERIES
        elif mevent.seriesMasterId:
            kind = RemoteKind.OCCURRENCE
        else:
            kind = RemoteKind.SINGLE
        return RemoteEvent(
            mevent.id,
            kind=kind,
            universal_id=mevent.iCalUId,
            master_id=mevent.seriesMasterId,
            cancelled=mevent.is_cancelled(),
            updated=mevent.lastModifiedDateTime and parse(mevent.lastModifiedDateTime),
            etag=mevent.changeKey,
            insert_id=mevent.transactionId,
            payload={"event": mevent},
        )

    @api.model
    def _find(self, account, universal_id):
        found, data = self._service()._get_single_event(
            universal_id, connection=self._connection(account)
        )
        values = (data or {}).get("value") or []
        if not found or len(values) != 1:
            return None
        return self._remote(MicrosoftEvent(values))

    @api.model
    def _insert(self, account, record, values, insert_id):
        event = self._service().insert(
            dict(values, transactionId=insert_id),
            connection=self._connection(account),
            timeout=self._timeout(),
        )
        return RemoteEvent(
            event["id"], universal_id=event.get("iCalUId"), etag=event.get("changeKey")
        )

    @api.model
    def _patch(self, account, remote_id, record, values):
        values = {
            key: value
            for key, value in values.items()
            if key not in ("isOnlineMeeting", "onlineMeetingProvider")
        }
        event = self._service().patch(
            remote_id,
            values,
            connection=self._connection(account),
            timeout=self._timeout(),
        )
        if event is None:
            raise CalendarSyncError(ErrorKind.GONE)
        return RemoteEvent(remote_id, etag=event.get("changeKey"))

    @api.model
    def _delete(self, account, remote_id):
        self._service().delete(
            remote_id, connection=self._connection(account), timeout=self._timeout()
        )

    @api.model
    def _answer(self, account, remote_id, state):
        if answer := ANSWERS.get(state):
            self._service().answer(
                remote_id,
                answer,
                {"comment": "", "sendResponse": True},
                connection=self._connection(account),
                timeout=self._timeout(),
            )

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
        elif status == 429:
            kind = ErrorKind.THROTTLED
        elif status == 401:
            kind = ErrorKind.AUTH
        elif status == 403:
            kind = ErrorKind.FORBIDDEN
        elif status == 400:
            kind = ErrorKind.INVALID
        else:
            kind = ErrorKind.TRANSIENT
        return CalendarSyncError(kind, message)

    @api.model
    def _synced_fields(self, model_name):
        return frozenset(self.env[model_name]._get_fields_microsoft_synced())

    @api.model
    def _check_record(self, record):
        return record._microsoft_refusal()

    @api.model
    def _remote_values(self, record, account):
        own = record._microsoft_links().filtered(
            lambda link: link.account_id == account
        )
        return record._microsoft_values(
            record._get_fields_microsoft_synced(),
            series_master_id=own.remote_master_id,
        )

    @api.model
    def _odoo_values(self, remote, model_name, record):
        mevent = remote.payload["event"]
        Event = self.env["calendar.event"]
        if record and record._name == "calendar.event" and mevent.type == "occurrence":
            return Event._microsoft_to_odoo_recurrence_values(mevent)
        return self.env[model_name]._microsoft_to_odoo_values(mevent, event=record)

    @api.model
    def _apply_series(self, account, master, occurrences, recurrence):
        Event = self.env["calendar.event"]
        Recurrence = self.env["calendar.recurrence"]
        if master and not recurrence:
            return self._create_series(master, occurrences)
        recurrence = recurrence.with_env(self.env)
        if master:
            mevent = master.payload["event"]
            recurrence._write_from_microsoft(
                mevent, Recurrence._microsoft_to_odoo_values(mevent)
            )
        if recurrence.repeat_type in ("count", "forever"):
            occurrences = occurrences[:MAX_RECURRENT_OCCURRENCES]
        links = self.env["calendar.sync.link"]._engine()._match(account, occurrences)
        events = {}
        timeslots = {}
        for remote in occurrences:
            mevent = remote.payload["event"]
            link = links.get(remote.remote_id)
            event = link.event_id.with_env(self.env) if link else Event
            if event or mevent.type != "occurrence":
                values = Event._microsoft_to_odoo_values(mevent, event=event)
            else:
                values = Event._microsoft_to_odoo_recurrence_values(mevent)
            if not event:
                event = recurrence.calendar_event_ids._filtered_matching_timeslot(
                    values["start"], values["stop"], mevent.isAllDay
                )[:1]
                if not event:
                    continue
                values.pop("start")
                values.pop("stop")
            elif master:
                timeslots[(recurrence.id, values["start"], values["stop"])] = values
            event.write(values)
            events[remote.remote_id] = event
        if master:
            detached = recurrence._apply_recurrence(timeslots)
            detached._microsoft_forget()
            detached.unlink()
        return recurrence, events

    @api.model
    def _create_series(self, master, occurrences):
        Event = self.env["calendar.event"]
        mevent = master.payload["event"]
        values = self.env["calendar.recurrence"]._microsoft_to_odoo_values(mevent)
        if values.get("repeat_type") in ("count", "forever"):
            occurrences = occurrences[:MAX_RECURRENT_OCCURRENCES]
        base_values = Event._microsoft_to_odoo_values(mevent)
        events_values = [
            Event._microsoft_to_odoo_recurrence_values(
                remote.payload["event"], dict(base_values)
            )
            if remote.payload["event"].type == "occurrence"
            else Event._microsoft_to_odoo_values(remote.payload["event"])
            for remote in occurrences
        ]
        recurrence = self.env["calendar.recurrence"].create(
            {
                **values,
                "calendar_event_ids": [Command.create(v) for v in events_values],
            }
        )
        events = recurrence.calendar_event_ids.sorted("id")
        recurrence.base_event_id = recurrence.calendar_event_ids[:1]
        return recurrence, {
            remote.remote_id: event
            for remote, event in zip(occurrences, events, strict=True)
        }
