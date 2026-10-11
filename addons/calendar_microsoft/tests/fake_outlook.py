"""Outlook, as the contract suite speaks to it through Graph: every calendar
holds its own copy of an item, under an id of its own and the item's
iCalendar UID."""

import itertools
import re
from datetime import UTC, datetime
from unittest.mock import patch

import requests
from dateutil.parser import parse

from odoo.libs.json import dumps as json_dumps

from odoo.addons.calendar_microsoft.utils.calendar_microsoft import (
    MicrosoftCalendarService,
)
from odoo.addons.calendar_sync.tests.contract import FakeCalendarServer

DELTA = "/v1.0/me/calendarView/delta"
BY_UID = re.compile(r"^/v1\.0/me/events\?\$filter=iCalUId eq '(?P<uid>[^']+)'$")
EVENT = re.compile(
    r"^/v1\.0/me/calendar/events(?:/(?P<id>[^/]+))?(?:/(?P<answer>\w+))?$"
)
ANSWERS = {
    "accept": "accepted",
    "decline": "declined",
    "tentativelyAccept": "tentativelyAccepted",
}
STATES = {
    "accepted": "accepted",
    "declined": "declined",
    "tentativelyaccepted": "tentative",
    "organizer": "accepted",
}


def refusal(status, code="", message=""):
    response = requests.Response()
    response.status_code = status
    response._content = json_dumps(
        {"error": {"code": code, "message": message}}
    ).encode()
    return requests.HTTPError(f"{status} refused", response=response)


def utc(when) -> datetime:
    moment = parse(when["dateTime"])
    if moment.tzinfo:
        return moment.astimezone(UTC).replace(tzinfo=None)
    return moment


class FakeOutlook(FakeCalendarServer):
    def __init__(self, env) -> None:
        super().__init__(env)
        self.meetings: dict[str, dict] = {}
        self.calendars: dict[int, dict[str, str]] = {}
        self.changed: dict[int, list] = {}
        self.removed: dict[int, set] = {}
        self.tokens: dict[int, str] = {}
        self.transactions: dict[tuple[int, str], str] = {}
        self._ids = itertools.count(1)
        self._versions = itertools.count(1)

    def patched(self):
        server = self

        def request(
            service,
            connection,
            method,
            path,
            *,
            params=None,
            json=None,
            headers=None,
            timeout,
        ):
            return server.request(
                server.user_of(connection), method, path, params, json
            )

        return patch.object(MicrosoftCalendarService, "_request", request)


    def request(self, user, method, path, params, body):
        if method == "GET" and path == DELTA:
            return self._delta(user, (params or {}).get("$deltatoken"))
        if method == "GET" and (match := BY_UID.match(path)):
            copy = self._copy_of(user, match.group("uid"))
            return 200, {"value": [self._view(user, copy)] if copy else []}
        match = EVENT.match(path)
        if not match:
            raise AssertionError(f"unexpected {method} {path}")
        copy_id, answer = match.group("id"), match.group("answer")
        if method == "POST" and answer:
            return self._answer(user, copy_id, answer)
        if method == "POST":
            return self._insert(user, body)
        if method == "PATCH":
            return self._patch(user, copy_id, body)
        if method == "DELETE":
            return self._delete_copy(user, copy_id)
        raise AssertionError(f"unexpected {method} {path}")

    def _refuse(self, operation):
        if status := self.refusals.pop(operation, None):
            raise refusal(status, message=f"{operation} refused")

    def _delta(self, user, token):
        if token and token != self.tokens.get(user.id):
            raise refusal(410, code="fullSyncRequired")
        calendar = self.calendars.get(user.id, {})
        if token:
            ids = list(dict.fromkeys(self.changed.pop(user.id, [])))
            removed = self.removed.pop(user.id, set())
        else:
            ids, removed = list(calendar), set()
            self.changed.pop(user.id, None)
            self.removed.pop(user.id, None)
        value = [
            {"id": copy_id, "@removed": {"reason": "deleted"}}
            if copy_id in removed
            else self._view(user, copy_id)
            for copy_id in ids
            if copy_id in removed or copy_id in calendar
        ]
        self.tokens[user.id] = token = f"delta{next(self._versions)}"
        return 200, {
            "value": value,
            "@odata.deltaLink": f"https://graph.microsoft.com{DELTA}?$deltatoken={token}",
        }

    def _insert(self, user, body):
        self._refuse("insert")
        key = (user.id, body.get("transactionId"))
        if body.get("transactionId") and key in self.transactions:
            copy_id = self.transactions[key]
        else:
            uid = f"uid{next(self._ids)}"
            self.meetings[uid] = {
                "organizer": user.id,
                "subject": body.get("subject"),
                "start": utc(body["start"]),
                "end": utc(body["end"]),
                "transactionId": body.get("transactionId"),
                "attendees": {
                    attendee["emailAddress"]["address"]: attendee["status"]["response"]
                    for attendee in body.get("attendees", [])
                },
            }
            copy_id = self._distribute(uid)[user.id]
            self.transactions[key] = copy_id
            self.ops.append((user.id, "insert", copy_id))
        if self.lost_answers:
            self.lost_answers -= 1
            raise requests.Timeout("the answer was lost")
        return 201, self._view(user, copy_id)

    def _patch(self, user, copy_id, body):
        self._refuse("patch")
        uid = self.calendars.get(user.id, {}).get(copy_id)
        if not uid:
            return 404, {}
        meeting = self.meetings[uid]
        if "subject" in body:
            meeting["subject"] = body["subject"]
        for key in ("start", "end"):
            if key in body:
                meeting[key] = utc(body[key])
        if "attendees" in body:
            meeting["attendees"] = {
                attendee["emailAddress"]["address"]: attendee["status"]["response"]
                for attendee in body["attendees"]
            }
        self._touch(uid)
        self.ops.append((user.id, "patch", copy_id))
        return 200, self._view(user, copy_id)

    def _delete_copy(self, user, copy_id):
        self._refuse("delete")
        uid = self.calendars.get(user.id, {}).get(copy_id)
        if not uid:
            return 404, {}
        self.ops.append((user.id, "delete", copy_id))
        self.delete(user, copy_id)
        return 204, {}

    def _answer(self, user, copy_id, answer):
        uid = self.calendars.get(user.id, {}).get(copy_id)
        if not uid:
            return 404, {}
        self.meetings[uid]["attendees"][user.email] = ANSWERS[answer]
        self._touch(uid)
        self.ops.append((user.id, "answer", copy_id))
        return 202, {}


    def _distribute(self, uid) -> dict[int, str]:
        meeting = self.meetings[uid]
        Users = self.env["res.users"]
        holders = Users.browse(meeting["organizer"]) | Users.search(
            [("email", "in", list(meeting["attendees"]))]
        )
        copies = {}
        for holder in holders:
            calendar = self.calendars.setdefault(holder.id, {})
            copy_id = next((cid for cid, u in calendar.items() if u == uid), None)
            copy_id = copy_id or f"ms{next(self._ids)}-for-{holder.id}"
            calendar[copy_id] = uid
            copies[holder.id] = copy_id
        self._touch(uid)
        return copies

    def _touch(self, uid) -> None:
        version = next(self._versions)
        meeting = self.meetings[uid]
        meeting["changeKey"] = f"ck{version}"
        meeting["lastModifiedDateTime"] = self.stamp(version).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        for user_id, calendar in self.calendars.items():
            for copy_id, copy_uid in calendar.items():
                if copy_uid == uid:
                    self.changed.setdefault(user_id, []).append(copy_id)

    def _copy_of(self, user, uid):
        return next(
            (cid for cid, u in self.calendars.get(user.id, {}).items() if u == uid),
            None,
        )

    def _view(self, user, copy_id) -> dict:
        uid = self.calendars[user.id][copy_id]
        meeting = self.meetings[uid]
        organizer = self.env["res.users"].browse(meeting["organizer"])
        is_organizer = organizer == user
        return {
            "type": "singleInstance",
            "id": copy_id,
            "iCalUId": uid,
            "seriesMasterId": None,
            "transactionId": meeting["transactionId"] if is_organizer else None,
            "subject": meeting["subject"],
            "body": {"content": "", "contentType": "html"},
            "start": {"dateTime": meeting["start"].isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": meeting["end"].isoformat(), "timeZone": "UTC"},
            "attendees": [
                {
                    "type": "required",
                    "status": {"response": response if is_organizer else "none"},
                    "emailAddress": {"address": email, "name": email},
                }
                for email, response in meeting["attendees"].items()
            ],
            "isAllDay": False,
            "isCancelled": False,
            "sensitivity": "normal",
            "showAs": "busy",
            "isOnlineMeeting": False,
            "isOrganizer": is_organizer,
            "isReminderOn": False,
            "location": {"displayName": ""},
            "organizer": {
                "emailAddress": {"address": organizer.email, "name": organizer.name}
            },
            "responseStatus": {
                "response": "organizer"
                if is_organizer
                else meeting["attendees"].get(user.email, "none")
            },
            "lastModifiedDateTime": meeting["lastModifiedDateTime"],
            "changeKey": meeting["changeKey"],
        }

    def add(self, user, name, start, stop, attendees=()):
        uid = f"uid{next(self._ids)}"
        self.meetings[uid] = {
            "organizer": user.id,
            "subject": name,
            "start": start,
            "end": stop,
            "transactionId": None,
            "attendees": {attendee.email: "none" for attendee in attendees},
        }
        return self._distribute(uid)[user.id]

    def rename(self, user, remote_id, name):
        uid = self.calendars[user.id][remote_id]
        self.meetings[uid]["subject"] = name
        self._touch(uid)

    def delete(self, user, remote_id):
        uid = self.calendars[user.id][remote_id]
        if self.meetings[uid]["organizer"] == user.id:
            holders = [
                (user_id, copy_id)
                for user_id, calendar in self.calendars.items()
                for copy_id, copy_uid in calendar.items()
                if copy_uid == uid
            ]
        else:
            holders = [(user.id, remote_id)]
        for user_id, copy_id in holders:
            del self.calendars[user_id][copy_id]
            self.changed.setdefault(user_id, []).append(copy_id)
            self.removed.setdefault(user_id, set()).add(copy_id)

    def expire_token(self, user):
        self.tokens[user.id] = "expired"

    def items(self, user):
        result = {}
        for copy_id, uid in self.calendars.get(user.id, {}).items():
            meeting = self.meetings[uid]
            result[copy_id] = {
                "name": meeting["subject"],
                "start": meeting["start"],
                "stop": meeting["end"],
                "answers": {
                    email: STATES.get(response.lower(), "needsAction")
                    for email, response in meeting["attendees"].items()
                },
            }
        return result

    def copy_id(self, user, remote_id_elsewhere):
        for calendar in self.calendars.values():
            if uid := calendar.get(remote_id_elsewhere):
                return self._copy_of(user, uid)
        return None
