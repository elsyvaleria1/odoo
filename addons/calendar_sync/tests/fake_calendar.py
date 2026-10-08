"""A provider the engine suite drives: calendars held in memory, with ids per
calendar (as Outlook gives them) or one id in every calendar (as Google)."""

import itertools
from datetime import datetime

from odoo.addons.calendar_sync.remote import (
    CalendarSyncError,
    ErrorKind,
    RemoteChanges,
    RemoteEvent,
    RemoteKind,
)

UPDATED = datetime(2000, 1, 1)
SYNCED = ("name", "start", "stop")


class FakeCalendars:
    def __init__(self, code: str, shared_ids: bool) -> None:
        self.code = code
        self.shared_ids = shared_ids
        self.calendars: dict[int, dict[str, dict]] = {}
        self.changed: dict[int, list[str]] = {}
        self.sent: list[tuple[str, int, str]] = []
        # (account id, record id) the engine said it inserted
        self.inserted: list[tuple[int, int]] = []
        # the context of each insert and patch, as the adapter sees it
        self.contexts: list[dict] = []
        # {operation: kind} fails every call; once=True only the next one
        self.failing: dict[str, tuple[ErrorKind, bool]] = {}
        # an insert that lands, then loses its answer
        self.lose_insert_answers = 0
        # {record id: why}: what the provider would refuse before any request
        self.refusals: dict[int, str] = {}
        self._ids = itertools.count(1)
        self._tokens = itertools.count(1)

    def calendar(self, account) -> dict[str, dict]:
        return self.calendars.setdefault(account.id, {})

    def add(self, account, remote_id=None, **values) -> str:
        """An item someone created in `account`'s calendar."""
        remote_id = remote_id or f"{self.code}-{next(self._ids)}"
        self.calendar(account)[remote_id] = {
            "uid": f"uid-{remote_id}",
            "etag": "1",
            "updated": UPDATED,
            "cancelled": False,
            "hint": None,
            "kind": RemoteKind.SINGLE,
            "master": None,
            **values,
        }
        self.changed.setdefault(account.id, []).append(remote_id)
        return remote_id

    def change(self, account, remote_id, **values) -> None:
        item = self.calendar(account)[remote_id]
        item.update(values, etag=str(int(item["etag"]) + 1))
        self.changed.setdefault(account.id, []).append(remote_id)

    def fail(self, operation: str, kind: ErrorKind, once=False) -> None:
        self.failing[operation] = (kind, once)

    def _check(self, operation: str) -> None:
        if failure := self.failing.get(operation):
            kind, once = failure
            if once:
                del self.failing[operation]
            raise CalendarSyncError(kind, f"{operation} refused: {kind}")

    def remote(self, remote_id: str, item: dict) -> RemoteEvent:
        return RemoteEvent(
            remote_id,
            kind=item.get("kind", RemoteKind.SINGLE),
            master_id=item.get("master"),
            universal_id=item["uid"],
            cancelled=item["cancelled"],
            updated=item["updated"],
            etag=item["etag"],
            odoo_hint=item["hint"],
            payload={key: item[key] for key in SYNCED if key in item},
        )


class FakeAdapter:
    """The adapter interface of calendar.sync.adapter, over FakeCalendars."""

    def __init__(self, server: FakeCalendars) -> None:
        self.server = server

    def _list_changes(self, account, token):
        server = self.server
        server._check("list")
        calendar = server.calendar(account)
        if token == "stale":
            raise CalendarSyncError(ErrorKind.TOKEN_INVALID)
        ids = server.changed.pop(account.id, []) if token else list(calendar)
        if not token:
            server.changed.pop(account.id, None)
        return RemoteChanges(
            tuple(server.remote(rid, calendar[rid]) for rid in dict.fromkeys(ids)),
            next_token=f"token-{next(server._tokens)}",
            full=not token,
        )

    def _find(self, account, universal_id):
        for remote_id, item in self.server.calendar(account).items():
            if item["uid"] == universal_id and not item["cancelled"]:
                return self.server.remote(remote_id, item)
        return None

    def _insert(self, account, record, values, insert_id):
        server = self.server
        server._check("insert")
        calendar = server.calendar(account)
        if server.shared_ids:
            if insert_id in calendar:
                raise CalendarSyncError(ErrorKind.CONFLICT)
            remote_id = insert_id
        else:
            for remote_id, item in calendar.items():
                if item.get("insert_id") == insert_id:
                    return server.remote(remote_id, item)
            remote_id = f"{server.code}-{next(server._ids)}"
        calendar[remote_id] = {
            **values,
            "uid": f"uid-{remote_id}",
            "etag": "1",
            "updated": UPDATED,
            "cancelled": False,
            "hint": record.id,
            "insert_id": insert_id,
        }
        server.sent.append(("insert", account.id, remote_id))
        server.contexts.append(dict(account.env.context))
        if server.lose_insert_answers:
            server.lose_insert_answers -= 1
            raise CalendarSyncError(ErrorKind.TRANSIENT, "the answer was lost")
        return server.remote(remote_id, calendar[remote_id])

    def _patch(self, account, remote_id, record, values):
        server = self.server
        server._check("patch")
        calendar = server.calendar(account)
        if remote_id not in calendar:
            raise CalendarSyncError(ErrorKind.GONE)
        item = calendar[remote_id]
        item.update(values, etag=str(int(item["etag"]) + 1))
        server.sent.append(("patch", account.id, remote_id))
        server.contexts.append(dict(account.env.context))
        return server.remote(remote_id, item)

    def _delete(self, account, remote_id):
        server = self.server
        server._check("delete")
        if server.calendar(account).pop(remote_id, None) is None:
            raise CalendarSyncError(ErrorKind.GONE)
        server.sent.append(("delete", account.id, remote_id))

    def _answer(self, account, remote_id, state):
        server = self.server
        server._check("answer")
        if remote_id not in server.calendar(account):
            raise CalendarSyncError(ErrorKind.GONE)
        server.sent.append(("answer", account.id, remote_id, state))

    def _check_record(self, record):
        return self.server.refusals.get(record.id)

    def _after_insert(self, account, record, remote):
        self.server.inserted.append((account.id, record.id))

    def _classify(self, error):
        return CalendarSyncError(ErrorKind.TRANSIENT, str(error))

    def _synced_fields(self, model_name):
        if model_name == "calendar.recurrence":
            return frozenset({"rrule"})
        return frozenset({*SYNCED, "active"})

    def _remote_values(self, record, account):
        return {key: record[key] for key in SYNCED}

    def _odoo_values(self, remote, model_name, record):
        return dict(remote.payload)

    def _apply_series(self, account, master, occurrences, recurrence):
        occurrences = sorted(occurrences, key=lambda remote: remote.payload["start"])
        if not master:
            # occurrences alone, each found in the series by its start
            events = {}
            for remote in occurrences:
                event = recurrence.calendar_event_ids.filtered(
                    lambda event, remote=remote: event.start == remote.payload["start"]
                )
                event.write(dict(remote.payload))
                events[remote.remote_id] = event
            return recurrence, events
        if not recurrence:
            event = account.env["calendar.event"].create(
                {**master.payload, "recurrency": True}
            )
            event._apply_recurrence_values(
                {
                    "repeat_unit": "day",
                    "repeat_interval": 1,
                    "repeat_number": len(occurrences),
                    "event_tz": "UTC",
                }
            )
            recurrence = account.env["calendar.recurrence"].search(
                [("base_event_id", "=", event.id)]
            )
        events = recurrence.calendar_event_ids.sorted("start")
        return recurrence, {
            remote.remote_id: event
            for remote, event in zip(occurrences, events, strict=True)
        }
