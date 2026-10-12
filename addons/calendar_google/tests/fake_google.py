"""Google Calendar, as the contract suite speaks to it: one item per id, which
every invited calendar shows."""

import itertools
import re
from unittest.mock import patch

import requests
from dateutil.parser import parse

from odoo.libs.json import dumps as json_dumps

from odoo.addons.calendar_google.utils.calendar_google import GoogleCalendarService
from odoo.addons.calendar_sync.tests.contract import FakeCalendarServer

EVENTS = re.compile(r"^/calendar/v3/calendars/primary/events(?:/(?P<id>[^/?]+))?")


def refusal(status, content=""):
    response = requests.Response()
    response.status_code = status
    response._content = content.encode()
    return requests.HTTPError(f"{status} refused", response=response)


class FakeGoogle(FakeCalendarServer):
    def __init__(self, env) -> None:
        super().__init__(env)
        self.events: dict[str, dict] = {}
        self.changed: dict[int, set] = {}
        self.tokens: dict[int, str] = {}
        self._ids = itertools.count(1)
        self._versions = itertools.count(1)

    def patched(self):
        server = self

        def request(
            service, connection, method, path, *, params=None, json=None, timeout
        ):
            return server.request(
                server.user_of(connection), method, path, params, json
            )

        return patch.object(GoogleCalendarService, "_request", request)

    def request(self, user, method, path, params, body):
        match = EVENTS.match(path)
        remote_id = match and match.group("id")
        if method == "GET":
            return self._list(user, (params or {}).get("syncToken"))
        if method == "POST":
            return self._insert(user, body)
        if method == "PATCH":
            return self._patch(user, remote_id, body)
        if method == "DELETE":
            return self._delete(user, remote_id)
        raise AssertionError(f"unexpected {method} {path}")

    def _list(self, user, token):
        if token and token != self.tokens.get(user.id):
            raise refusal(410, "fullSyncRequired")
        if token:
            ids = self.changed.pop(user.id, set())
        else:
            ids = {
                rid
                for rid, event in self.events.items()
                if event["status"] != "cancelled"
            }
            self.changed.pop(user.id, None)
        items = [
            self._view(user, self.events[rid])
            for rid in sorted(ids)
            if self._sees(user, self.events[rid])
        ]
        self.tokens[user.id] = token = f"token-{next(self._versions)}"
        return {"items": items, "nextSyncToken": token}

    def _refuse(self, operation):
        if status := self.refusals.pop(operation, None):
            raise refusal(
                status, json_dumps({"error": {"message": f"{operation} refused"}})
            )

    def _insert(self, user, body):
        self._refuse("insert")
        remote_id = body["id"]
        if remote_id in self.events:
            raise refusal(409, "duplicate")
        self.events[remote_id] = {
            **body,
            "iCalUID": f"{remote_id}@google.com",
            "status": "confirmed",
            "organizer": {"email": user.email},
        }
        self._touch(remote_id)
        self.ops.append((user.id, "insert", remote_id))
        if self.lost_answers:
            self.lost_answers -= 1
            raise requests.Timeout("the answer was lost")
        return self._view(user, self.events[remote_id])

    def _patch(self, user, remote_id, body):
        self._refuse("patch")
        event = self.events.get(remote_id)
        if not event or event["status"] == "cancelled":
            return False
        event.update({k: v for k, v in body.items() if k not in ("id", "organizer")})
        self._touch(remote_id)
        self.ops.append((user.id, "patch", remote_id))
        return self._view(user, event)

    def _delete(self, user, remote_id):
        self._refuse("delete")
        event = self.events.get(remote_id)
        if not event:
            return False
        event["status"] = "cancelled"
        self._touch(remote_id)
        self.ops.append((user.id, "delete", remote_id))
        return False

    def _sees(self, user, event) -> bool:
        return event["organizer"]["email"] == user.email or any(
            attendee["email"] == user.email for attendee in event.get("attendees", [])
        )

    def _touch(self, remote_id) -> None:
        event = self.events[remote_id]
        version = next(self._versions)
        event["etag"] = f'"{version}"'
        event["updated"] = self.stamp(version).isoformat() + "Z"
        for user_id in self.env["res.users"].search([]).ids:
            self.changed.setdefault(user_id, set()).add(remote_id)

    def _view(self, user, event) -> dict:
        return {
            **event,
            "organizer": {
                "email": event["organizer"]["email"],
                "self": event["organizer"]["email"] == user.email,
            },
            "reminders": event.get("reminders") or {"useDefault": False},
        }

    @staticmethod
    def _when(moment) -> dict:
        return {"dateTime": moment.isoformat() + "Z"}

    def add(self, user, name, start, stop, attendees=()):
        remote_id = f"google{next(self._ids)}"
        self.events[remote_id] = {
            "id": remote_id,
            "iCalUID": f"{remote_id}@google.com",
            "status": "confirmed",
            "summary": name,
            "start": self._when(start),
            "end": self._when(stop),
            "organizer": {"email": user.email},
            "attendees": [
                {"email": user.email, "responseStatus": "accepted", "organizer": True},
                *(
                    {"email": attendee.email, "responseStatus": "needsAction"}
                    for attendee in attendees
                ),
            ],
        }
        self._touch(remote_id)
        return remote_id

    def rename(self, user, remote_id, name):
        self.events[remote_id]["summary"] = name
        self._touch(remote_id)

    def delete(self, user, remote_id):
        event = self.events[remote_id]
        if event["organizer"]["email"] == user.email:
            event["status"] = "cancelled"
        else:
            for attendee in event["attendees"]:
                if attendee["email"] == user.email:
                    attendee["responseStatus"] = "declined"
        self._touch(remote_id)

    def expire_token(self, user):
        self.tokens[user.id] = "expired"

    def items(self, user):
        return {
            remote_id: {
                "name": event.get("summary"),
                "start": parse(event["start"]["dateTime"]).replace(tzinfo=None),
                "stop": parse(event["end"]["dateTime"]).replace(tzinfo=None),
                "answers": {
                    attendee["email"]: attendee.get("responseStatus")
                    for attendee in event.get("attendees", [])
                },
            }
            for remote_id, event in self.events.items()
            if event["status"] != "cancelled" and self._sees(user, event)
        }

    def copy_id(self, user, remote_id_elsewhere):
        return remote_id_elsewhere
