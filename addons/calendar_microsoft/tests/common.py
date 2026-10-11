import itertools
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time
from markupsafe import Markup

from odoo import fields
from odoo.tests.common import HttpCase

from odoo.addons.calendar_microsoft.utils.calendar_microsoft import CALENDAR_SCOPE
from odoo.addons.calendar_microsoft.utils.microsoft_event import MicrosoftEvent


def distinct_inserts(prefix):
    numbers = itertools.count(1)

    def insert(*args, **kwargs):
        number = next(numbers)
        return {"id": f"{prefix}_{number}", "iCalUId": f"{prefix}_uid_{number}"}

    return insert


def mock_get_connection(user, code=None):
    return code in (None, "microsoft") and f"TOKEN_FOR_USER_{user.id}"


def authorize_microsoft_calendar(
    user, access_token="an-access", refresh_token="a-refresh"
):
    env = user.env
    connection = env["integration.connection"]._personal(
        env.ref("integration_microsoft.service_microsoft"), user, scope=CALENDAR_SCOPE
    )
    connection._oauth_store_tokens(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": 3600,
        },
        "https://odoo.example/integration/oauth/callback",
    )
    return connection


def _modified_date_in_the_future(event):
    return (event.write_date + timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestCommon(HttpCase):
    def setUp(self):
        super().setUp()
        self.env["calendar.sync.account"]._set_paused("microsoft", False)

        self.organizer_user = self.env["res.users"].search(
            [("name", "=", "Mike Organizer")]
        )
        if not self.organizer_user:
            partner = self.env["res.partner"].create(
                {"name": "Mike Organizer", "email": "mike@organizer.com"}
            )
            self.organizer_user = self.env["res.users"].create(
                {
                    "name": "Mike Organizer",
                    "login": "mike@organizer.com",
                    "partner_id": partner.id,
                }
            )

        self.attendee_user = self.env["res.users"].search(
            [("name", "=", "John Attendee")]
        )
        if not self.attendee_user:
            partner = self.env["res.partner"].create(
                {"name": "John Attendee", "email": "john@attendee.com"}
            )
            self.attendee_user = self.env["res.users"].create(
                {
                    "name": "John Attendee",
                    "login": "john@attendee.com",
                    "partner_id": partner.id,
                }
            )

        self.start_date = datetime(2021, 9, 22, 10, 0, 0, 0)
        self.end_date = datetime(2021, 9, 22, 11, 0, 0, 0)
        self.recurrent_event_interval = 2
        self.recurrent_events_count = 7
        self.recurrence_end_date = self.end_date + timedelta(
            days=self.recurrent_event_interval * self.recurrent_events_count
        )

        self.simple_event_values = {
            "name": "simple_event",
            "description": "my simple event",
            "active": True,
            "start": self.start_date,
            "stop": self.end_date,
            "partner_ids": [
                (4, self.organizer_user.partner_id.id),
                (4, self.attendee_user.partner_id.id),
            ],
        }
        self.recurrent_event_values = {
            "name": "recurring_event",
            "description": "a recurring event",
            "partner_ids": [(4, self.attendee_user.partner_id.id)],
            "recurrency": True,
            "follow_recurrence": True,
            "start": self.start_date.strftime("%Y-%m-%d %H:%M:%S"),
            "stop": self.end_date.strftime("%Y-%m-%d %H:%M:%S"),
            "event_tz": "Europe/London",
            "recurrence_update": "this",
            "repeat_unit": "day",
            "repeat_interval": self.recurrent_event_interval,
            "repeat_number": self.recurrent_events_count,
            "repeat_type": "count",
            "duration": 1,
            "byday": "-1",
            "day": 22,
            "wed": True,
            "weekday": "WED",
        }


        self.simple_event_ms_values = {
            "subject": self.simple_event_values["name"],
            "body": {
                "content": self.simple_event_values["description"],
                "contentType": "text",
            },
            "start": {
                "dateTime": self.simple_event_values["start"]
                .replace(tzinfo=UTC)
                .isoformat(),
                "timeZone": "Europe/London",
            },
            "end": {
                "dateTime": self.simple_event_values["stop"]
                .replace(tzinfo=UTC)
                .isoformat(),
                "timeZone": "Europe/London",
            },
            "isAllDay": False,
            "organizer": {
                "emailAddress": {
                    "address": self.organizer_user.email,
                    "name": self.organizer_user.display_name,
                }
            },
            "isOrganizer": True,
            "sensitivity": "normal",
            "showAs": "busy",
            "attendees": [
                {
                    "emailAddress": {
                        "address": self.attendee_user.email,
                        "name": self.attendee_user.display_name,
                    },
                    "status": {"response": "notresponded"},
                }
            ],
            "isReminderOn": False,
            "location": {"displayName": ""},
            "reminderMinutesBeforeStart": 0,
        }

        self.recurrent_event_ms_values = {
            "subject": self.recurrent_event_values["name"],
            "body": {
                "content": Markup(
                    "<p>%s</p>" % self.recurrent_event_values["description"]
                ),
                "contentType": "html",
            },
            "start": {
                "dateTime": self.start_date.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "timeZone": "Europe/London",
            },
            "end": {
                "dateTime": self.end_date.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "timeZone": "Europe/London",
            },
            "isAllDay": False,
            "isOrganizer": True,
            "isReminderOn": False,
            "reminderMinutesBeforeStart": 0,
            "sensitivity": "normal",
            "showAs": "busy",
            "type": "seriesMaster",
            "attendees": [
                {
                    "emailAddress": {
                        "address": self.attendee_user.email,
                        "name": self.attendee_user.display_name,
                    },
                    "status": {"response": "notresponded"},
                }
            ],
            "location": {"displayName": ""},
            "organizer": {
                "emailAddress": {
                    "address": self.organizer_user.email,
                    "name": self.organizer_user.display_name,
                },
            },
            "recurrence": {
                "pattern": {
                    "interval": self.recurrent_event_interval,
                    "type": "daily",
                },
                "range": {
                    "numberOfOccurrences": self.recurrent_events_count,
                    "startDate": self.start_date.strftime("%Y-%m-%d"),
                    "type": "numbered",
                },
            },
        }


        self.simple_event_from_outlook_organizer = {
            "type": "singleInstance",
            "seriesMasterId": None,
            "id": "123",
            "iCalUId": "456",
            "subject": "simple_event",
            "body": {
                "content": "my simple event",
                "contentType": "text",
            },
            "start": {
                "dateTime": self.start_date.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": self.end_date.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                "timeZone": "UTC",
            },
            "attendees": [
                {
                    "type": "required",
                    "status": {"response": "none", "time": "0001-01-01T00:00:00Z"},
                    "emailAddress": {
                        "name": self.attendee_user.display_name,
                        "address": self.attendee_user.email,
                    },
                }
            ],
            "isAllDay": False,
            "isCancelled": False,
            "sensitivity": "normal",
            "showAs": "busy",
            "isOnlineMeeting": False,
            "onlineMeetingUrl": None,
            "isOrganizer": True,
            "isReminderOn": True,
            "location": {"displayName": ""},
            "organizer": {
                "emailAddress": {
                    "address": self.organizer_user.email,
                    "name": self.organizer_user.display_name,
                },
            },
            "reminderMinutesBeforeStart": 15,
            "responseRequested": True,
            "responseStatus": {
                "response": "organizer",
                "time": "0001-01-01T00:00:00Z",
            },
        }

        self.simple_event_from_outlook_attendee = dict(
            self.simple_event_from_outlook_organizer, isOrganizer=False
        )


        self.expected_odoo_event_from_outlook = {
            "name": "simple_event",
            "description": Markup("<p>my simple event</p>"),
            "active": True,
            "start": self.start_date,
            "stop": self.end_date,
            "user_id": self.organizer_user,
            "microsoft_id": "123",
            "ms_universal_event_id": "456",
            "partner_ids": [
                self.organizer_user.partner_id.id,
                self.attendee_user.partner_id.id,
            ],
        }
        self.expected_odoo_recurrency_from_outlook = {
            "active": True,
            "byday": "1",
            "repeat_number": 0,
            "day": 0,
            "display_name": "Every %s Days until %s"
            % (
                self.recurrent_event_interval,
                self.recurrence_end_date.strftime("%Y-%m-%d"),
            ),
            "dtstart": self.start_date,
            "repeat_type": "until",
            "event_tz": False,
            "fri": False,
            "repeat_interval": self.recurrent_event_interval,
            "month_by": "date",
            "microsoft_id": "REC123",
            "ms_universal_event_id": "REC456",
            "name": "Every %s Days until %s"
            % (
                self.recurrent_event_interval,
                self.recurrence_end_date.strftime("%Y-%m-%d"),
            ),
            "rrule": "FREQ=DAILY;INTERVAL=%s;UNTIL=%s"
            % (
                self.recurrent_event_interval,
                self.recurrence_end_date.strftime("%Y%m%dT235959"),
            ),
            "repeat_unit": "day",
            "repeat_until": self.recurrence_end_date.date(),
            "weekday": False,
        }

        self.recurrent_event_from_outlook_organizer = [
            {
                "attendees": [
                    {
                        "emailAddress": {
                            "address": self.attendee_user.email,
                            "name": self.attendee_user.display_name,
                        },
                        "status": {"response": "none", "time": "0001-01-01T00:00:00Z"},
                        "type": "required",
                    }
                ],
                "body": {
                    "content": "my recurrent event",
                    "contentType": "text",
                },
                "start": {
                    "dateTime": self.start_date.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": self.end_date.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                },
                "id": "REC123",
                "iCalUId": "REC456",
                "isAllDay": False,
                "isCancelled": False,
                "isOnlineMeeting": False,
                "isOrganizer": True,
                "isReminderOn": True,
                "location": {"displayName": ""},
                "organizer": {
                    "emailAddress": {
                        "address": self.organizer_user.email,
                        "name": self.organizer_user.display_name,
                    }
                },
                "recurrence": {
                    "pattern": {
                        "dayOfMonth": 0,
                        "firstDayOfWeek": "sunday",
                        "index": "first",
                        "interval": self.recurrent_event_interval,
                        "month": 0,
                        "type": "daily",
                    },
                    "range": {
                        "startDate": self.start_date.strftime("%Y-%m-%d"),
                        "endDate": self.recurrence_end_date.strftime("%Y-%m-%d"),
                        "numberOfOccurrences": 0,
                        "recurrenceTimeZone": "Romance Standard Time",
                        "type": "endDate",
                    },
                },
                "reminderMinutesBeforeStart": 15,
                "responseRequested": True,
                "responseStatus": {
                    "response": "organizer",
                    "time": "0001-01-01T00:00:00Z",
                },
                "sensitivity": "normal",
                "seriesMasterId": None,
                "showAs": "busy",
                "subject": "recurrent event",
                "type": "seriesMaster",
            }
        ]
        self.recurrent_event_from_outlook_organizer += [
            {
                "attendees": [
                    {
                        "emailAddress": {
                            "address": self.attendee_user.email,
                            "name": self.attendee_user.display_name,
                        },
                        "status": {"response": "none", "time": "0001-01-01T00:00:00Z"},
                        "type": "required",
                    }
                ],
                "body": {
                    "content": "my recurrent event",
                    "contentType": "text",
                },
                "start": {
                    "dateTime": (
                        self.start_date
                        + timedelta(days=i * self.recurrent_event_interval)
                    ).strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": (
                        self.end_date
                        + timedelta(days=i * self.recurrent_event_interval)
                    ).strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                },
                "id": f"REC123_EVENT_{i + 1}",
                "iCalUId": f"REC456_EVENT_{i + 1}",
                "seriesMasterId": "REC123",
                "isAllDay": False,
                "isCancelled": False,
                "isOnlineMeeting": False,
                "isOrganizer": True,
                "isReminderOn": True,
                "location": {"displayName": ""},
                "organizer": {
                    "emailAddress": {
                        "address": self.organizer_user.email,
                        "name": self.organizer_user.display_name,
                    }
                },
                "recurrence": None,
                "reminderMinutesBeforeStart": 15,
                "responseRequested": True,
                "responseStatus": {
                    "response": "organizer",
                    "time": "0001-01-01T00:00:00Z",
                },
                "sensitivity": "normal",
                "showAs": "busy",
                "subject": "recurrent event",
                "type": "occurrence",
            }
            for i in range(self.recurrent_events_count)
        ]
        self.recurrent_event_from_outlook_attendee = [
            dict(
                d,
                isOrganizer=False,
                attendees=[
                    {
                        "emailAddress": {
                            "address": self.organizer_user.email,
                            "name": self.organizer_user.display_name,
                        },
                        "status": {"response": "none", "time": "0001-01-01T00:00:00Z"},
                        "type": "required",
                    },
                    {
                        "emailAddress": {
                            "address": self.attendee_user.email,
                            "name": self.attendee_user.display_name,
                        },
                        "status": {"response": "none", "time": "0001-01-01T00:00:00Z"},
                        "type": "required",
                    },
                ],
            )
            for d in self.recurrent_event_from_outlook_organizer
        ]

        self.expected_odoo_recurrency_events_from_outlook = [
            {
                "name": "recurrent event",
                "user_id": self.organizer_user,
                "partner_ids": [
                    self.organizer_user.partner_id.id,
                    self.attendee_user.partner_id.id,
                ],
                "start": self.start_date
                + timedelta(days=i * self.recurrent_event_interval),
                "stop": self.end_date
                + timedelta(days=i * self.recurrent_event_interval),
                "repeat_until": self.recurrence_end_date.date(),
                "microsoft_recurrence_master_id": "REC123",
                "microsoft_id": f"REC123_EVENT_{i + 1}",
                "ms_universal_event_id": f"REC456_EVENT_{i + 1}",
                "recurrency": True,
                "follow_recurrence": True,
                "active": True,
            }
            for i in range(self.recurrent_events_count)
        ]
        self.env.cr.postcommit.clear()

    @contextmanager
    def mock_datetime_and_now(self, mock_dt):
        now_dt = (
            fields.Datetime.to_datetime(mock_dt)
            if isinstance(mock_dt, str)
            else mock_dt
        )
        if now_dt.tzinfo is not None:
            now_dt = now_dt.astimezone(UTC).replace(tzinfo=None)
        with freeze_time(now_dt), patch.object(self.env.cr, "now", lambda: now_dt):
            yield

    def sync_odoo_recurrences_with_outlook_feature(self):
        return False

    def create_events_for_tests(self):


        self.simple_event = self.env["calendar.event"].search(
            [("name", "=", "simple_event")]
        )
        if not self.simple_event:
            self.simple_event = self.link_microsoft(
                self.env["calendar.event"]
                .with_user(self.organizer_user)
                .create(self.simple_event_values),
                self.organizer_user,
                "123",
                "456",
            )

        self.several_events = self.env["calendar.event"].search(
            [("name", "like", "event%")]
        )
        if not self.several_events:
            self.several_events = (
                self.env["calendar.event"]
                .with_user(self.organizer_user)
                .create(
                    [
                        dict(self.simple_event_values, name=f"event{i}")
                        for i in range(1, 4)
                    ]
                )
            )
            for i, event in enumerate(self.several_events, start=1):
                self.link_microsoft(event, self.organizer_user, f"e{i}", f"u{i}")

        self.recurrent_base_event = self.env["calendar.event"].search(
            [("name", "=", "recurrent_event")],
            order="id",
            limit=1,
        )
        already_created = self.recurrent_base_event

        sync_previous_state = self.env.user._calendar_sync_account("microsoft").stopped
        self.env.user._calendar_sync_account("microsoft").stopped = False

        if not already_created:
            self.recurrent_base_event = (
                self.env["calendar.event"]
                .with_context(dont_notify=True, calendar_sync_applying="microsoft")
                .with_user(self.organizer_user)
                .create(self.recurrent_event_values)
            )
        self.recurrence = self.env["calendar.recurrence"].search(
            [("base_event_id", "=", self.recurrent_base_event.id)]
        )

        if not already_created:
            self.env.flush_all()
            self.link_microsoft(
                self.recurrence, self.organizer_user, "REC123", "REC456"
            )
            for i, e in enumerate(
                self.recurrence.calendar_event_ids.sorted(key=lambda r: r.start)
            ):
                self.link_microsoft(
                    e,
                    self.organizer_user,
                    f"REC123_EVENT_{i + 1}",
                    f"REC456_EVENT_{i + 1}",
                    master_id="REC123",
                )
            self.recurrence.invalidate_recordset()
            self.recurrence.calendar_event_ids.invalidate_recordset()

            self.recurrent_events = self.recurrence.calendar_event_ids.sorted(
                key=lambda r: r.start
            )
            self.recurrent_events_count = len(self.recurrent_events)

        self.env.user._calendar_sync_account("microsoft").stopped = sync_previous_state

    def assert_odoo_event(self, odoo_event, expected_values):
        self.assertTrue(expected_values)
        expected_values = self._assert_held_ids(odoo_event, expected_values)

        odoo_event_values = odoo_event.read(list(expected_values.keys()))[0]
        for k, v in expected_values.items():
            if k in ("user_id", "recurrence_id"):
                v = (v.id, v.name) if v else False

            if isinstance(v, list):
                self.assertListEqual(
                    sorted(v), sorted(odoo_event_values.get(k)), msg=f"'{k}' mismatch"
                )
            else:
                self.assertEqual(v, odoo_event_values.get(k), msg=f"'{k}' mismatch")

    def assert_odoo_recurrence(self, odoo_recurrence, expected_values):
        expected_values = self._assert_held_ids(odoo_recurrence, expected_values)
        odoo_recurrence_values = odoo_recurrence.read(list(expected_values.keys()))[0]

        for k, v in expected_values.items():
            self.assertEqual(v, odoo_recurrence_values.get(k), msg=f"'{k}' mismatch")

    def _assert_held_ids(self, record, expected_values):
        held = {
            "microsoft_id": "remote_id",
            "ms_universal_event_id": "universal_id",
            "microsoft_recurrence_master_id": "remote_master_id",
        }
        for key, field in held.items():
            if key in expected_values:
                self.assertEqual(
                    self.held_id(record, field),
                    expected_values[key],
                    f"'{key}' mismatch",
                )
        return {k: v for k, v in expected_values.items() if k not in held}

    def assert_dict_equal(self, dict1, dict2):

        keys = set(dict1.keys()) ^ set(dict2.keys())
        self.assertFalse(
            keys, msg="Following keys are not in both dicts: %s" % ", ".join(keys)
        )

        for k, v in dict1.items():
            self.assertEqual(v, dict2.get(k), f"'{k}' mismatch")

    def call_post_commit_hooks(self):
        self.env.flush_all()
        funcs = self.env.cr.postcommit._funcs
        while funcs:
            funcs.popleft()()
        self.env.invalidate_all()

    def apply_microsoft(self, items, user):
        user = user._calendar_sync_as_owner()
        account = user._calendar_sync_account("microsoft")._as_engine()
        changes = self.env["calendar.sync.adapter.microsoft"]._changes(
            MicrosoftEvent(items)
        )
        return account._pull(changes)

    def sync_microsoft(self, user):
        user.with_user(user).sudo()._calendar_sync_run("microsoft")
        self.call_post_commit_hooks()

    def link_microsoft(
        self, record, user, remote_id, universal_id=None, master_id=None
    ):
        Link = self.env["calendar.sync.link"]._engine()
        account = self.env["calendar.sync.account"]._for(user, "microsoft")
        field = Link._field_of(record)
        Link.search([("account_id", "=", account.id), (field, "=", record.id)]).unlink()
        Link.create(
            {
                "account_id": account.id,
                field: record.id,
                "remote_id": remote_id,
                "universal_id": universal_id,
                "remote_master_id": master_id,
            }
        )
        record.invalidate_recordset()
        return record

    def held_id(self, record, field="remote_id"):
        links = self.env["calendar.sync.link"]._of(record, "microsoft")
        organizer = (
            record.user_id
            if record._name == "calendar.event"
            else record.base_event_id.user_id
        )
        link = links.filtered(lambda link: link.account_id.user_id == organizer)
        return (link or links)[:1][field]

    def find_microsoft(self, model, operator, value, field="remote_id"):
        Link = self.env["calendar.sync.link"]._engine()
        fk = Link._field_of(self.env[model])
        links = Link.search(
            [
                ("account_id.provider", "=", "microsoft"),
                (field, operator, value),
                (fk, "!=", False),
            ]
        )
        return self.env[model].search([("id", "in", links[fk].ids)])

    def microsoft_id(self, record, user):
        return self.microsoft_link(record, user).remote_id

    def microsoft_link(self, record, user):
        Link = self.env["calendar.sync.link"]._engine()
        return Link.search(
            [
                ("account_id.user_id", "=", user.id),
                ("account_id.provider", "=", "microsoft"),
                (Link._field_of(record), "=", record.id),
            ]
        )

    def assert_patched(self, mock_patch, remote_id, values, user):
        mock_patch.assert_called_once()
        (sent_id, sent), kwargs = mock_patch.call_args
        self.assertEqual(sent_id, remote_id)
        self.assertEqual({key: sent.get(key) for key in values}, values)
        self.assertEqual(kwargs["connection"], mock_get_connection(user))

    def awaits_push(self, record):
        links = self.env["calendar.sync.link"]._of(record, "microsoft")
        return bool(links.filtered("pending")) or (not links and record.active)
