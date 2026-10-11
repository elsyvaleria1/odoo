from datetime import UTC, datetime

from dateutil.relativedelta import relativedelta

from odoo.addons.calendar_microsoft.tests.common import TestCommon
from odoo.addons.calendar_microsoft.utils.microsoft_event import MicrosoftEvent


class TestMicrosoftEvent(TestCommon):
    """How the items of an Outlook calendar find their Odoo records: by this
    calendar's id, else by the iCalendar UID another calendar's link holds,
    whereupon this calendar gets a link of its own."""

    def setUp(self):
        super().setUp()
        self.create_events_for_tests()

    def match(self, user, items):
        account = self.env["calendar.sync.account"]._for(user, "microsoft")
        changes = self.env["calendar.sync.adapter.microsoft"]._changes(
            MicrosoftEvent(items)
        )
        return self.env["calendar.sync.link"]._engine()._match(account, changes.events)

    def test_an_item_is_found_by_this_calendars_id(self):
        found = self.match(
            self.organizer_user, [{"type": "singleInstance", "id": "123"}]
        )
        self.assertEqual(found["123"].event_id, self.simple_event)

    def test_another_calendars_copy_is_found_by_its_universal_id(self):
        found = self.match(
            self.attendee_user,
            [{"type": "singleInstance", "id": "attendee_123", "iCalUId": "456"}],
        )
        self.assertEqual(found["attendee_123"].event_id, self.simple_event)
        self.assertEqual(
            self.microsoft_id(self.simple_event, self.attendee_user), "attendee_123"
        )
        self.assertEqual(
            self.microsoft_id(self.simple_event, self.organizer_user),
            "123",
            "the organizer's calendar keeps its own id",
        )

    def test_a_link_found_by_universal_id_takes_this_calendars_id(self):
        self.link_microsoft(self.simple_event, self.attendee_user, "stale", "456")
        self.match(
            self.attendee_user,
            [{"type": "singleInstance", "id": "attendee_123", "iCalUId": "456"}],
        )
        self.assertEqual(
            self.microsoft_id(self.simple_event, self.attendee_user), "attendee_123"
        )

    def test_another_calendars_id_alone_finds_nothing(self):
        self.assertFalse(
            self.match(self.attendee_user, [{"type": "singleInstance", "id": "123"}])
        )

    def test_a_series_is_found_as_a_recurrence(self):
        found = self.match(
            self.organizer_user,
            [{"type": "seriesMaster", "id": "REC123", "iCalUId": "REC456"}],
        )
        self.assertEqual(found["REC123"].recurrence_id, self.recurrence)

    def test_a_deleted_series_is_found_though_untyped(self):
        found = self.match(
            self.organizer_user, [{"@removed": {"reason": "deleted"}, "id": "REC123"}]
        )
        self.assertEqual(found["REC123"].recurrence_id, self.recurrence)

    def test_events_and_series_are_found_together(self):
        found = self.match(
            self.organizer_user,
            [
                {"type": "singleInstance", "id": "123", "iCalUId": "456"},
                {"@removed": {"reason": "deleted"}, "id": "REC123"},
            ],
        )
        self.assertEqual(found["123"].event_id, self.simple_event)
        self.assertEqual(found["REC123"].recurrence_id, self.recurrence)

    def test_an_unknown_item_is_not_found(self):
        self.assertFalse(
            self.match(
                self.organizer_user,
                [{"type": "singleInstance", "id": "UNKNOWN", "iCalUId": "UNKNOWN"}],
            )
        )

    def test_microsoft_event_readonly(self):
        event = MicrosoftEvent()
        with self.assertRaises(TypeError):
            event._events["foo"] = "bar"
        with self.assertRaises(AttributeError):
            event._events.update({"foo": "bar"})
        with self.assertRaises(TypeError):
            dict.update(event._events, {"foo": "bar"})

    def test_matching_many_items(self):

        start_date = datetime(2023, 9, 25, 17, 25)
        record_count = 10000
        single_event_data = [
            {
                "@odata.type": "#microsoft.graph.event",
                "@odata.etag": f'W/"AAAAAA{x}"',
                "type": "singleInstance",
                "createdDateTime": (start_date + relativedelta(minutes=x)).isoformat(),
                "lastModifiedDateTime": (
                    datetime.now().astimezone(UTC) + relativedelta(days=3)
                ).isoformat(),
                "changeKey": f"ZS2uEVAVyU6BMZ3m6cH{x}mtgAADI/Dig==",
                "categories": [],
                "originalStartTimeZone": "Romance Standard Time",
                "originalEndTimeZone": "Romance Standard Time",
                "id": f"AA{x}",
                "subject": f"Subject of {x}",
                "bodyPreview": f"Body of {x}",
                "start": {
                    "dateTime": (start_date + relativedelta(minutes=x)).isoformat(),
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": (start_date + relativedelta(minutes=x)).isoformat(),
                    "timeZone": "UTC",
                },
                "isOrganizer": True,
                "organizer": {
                    "emailAddress": {
                        "name": f"outlook_{x}@outlook.com",
                        "address": f"outlook_{x}@outlook.com",
                    }
                },
            }
            for x in range(record_count)
        ]

        self.assertFalse(
            self.match(self.organizer_user, single_event_data),
            "No odoo record should correspond to the microsoft values",
        )

        recurring_event_data = [
            {
                "@odata.type": "#microsoft.graph.event",
                "@odata.etag": f'W/"{x}IaZKQ=="',
                "createdDateTime": (
                    start_date + relativedelta(minutes=(2 * x))
                ).isoformat(),
                "lastModifiedDateTime": (
                    datetime.now().astimezone(UTC) + relativedelta(days=3)
                ).isoformat(),
                "changeKey": "ZS2uEVAVyU6BMZ3m6cHmtgAADIaZKQ==",
                "categories": [],
                "originalStartTimeZone": "Romance Standard Time",
                "originalEndTimeZone": "Romance Standard Time",
                "iCalUId": f"XX{x}",
                "id": f"AAA{x}",
                "reminderMinutesBeforeStart": 15,
                "isReminderOn": True,
                "hasAttachments": False,
                "subject": f"My recurrent event {x}",
                "bodyPreview": "",
                "importance": "normal",
                "sensitivity": "normal",
                "isAllDay": False,
                "isCancelled": False,
                "isOrganizer": True,
                "IsRoomRequested": False,
                "AutoRoomBookingStatus": "None",
                "responseRequested": True,
                "seriesMasterId": None,
                "showAs": "busy",
                "type": "seriesMaster",
                "webLink": f"https://outlook.live.com/owa/?itemid={x}&exvsurl=1&path=/calendar/item",
                "onlineMeetingUrl": None,
                "isOnlineMeeting": False,
                "onlineMeetingProvider": "unknown",
                "AllowNewTimeProposals": True,
                "IsDraft": False,
                "responseStatus": {
                    "response": "organizer",
                    "time": "0001-01-01T00:00:00Z",
                },
                "body": {"contentType": "html", "content": ""},
                "start": {"dateTime": "2020-05-03T14:30:00.0000000", "timeZone": "UTC"},
                "end": {"dateTime": "2020-05-03T16:00:00.0000000", "timeZone": "UTC"},
                "location": {
                    "displayName": "",
                    "locationType": "default",
                    "uniqueIdType": "unknown",
                    "address": {},
                    "coordinates": {},
                },
                "locations": [],
                "recurrence": {
                    "pattern": {
                        "type": "daily",
                        "interval": 1,
                        "month": 0,
                        "dayOfMonth": 0,
                        "firstDayOfWeek": "sunday",
                        "index": "first",
                    },
                    "range": {
                        "type": "endDate",
                        "startDate": "2020-05-03",
                        "endDate": "2020-05-05",
                        "recurrenceTimeZone": "Romance Standard Time",
                        "numberOfOccurrences": 0,
                    },
                },
                "attendees": [],
                "organizer": {
                    "emailAddress": {
                        "name": f"outlook_{x}@outlook.com",
                        "address": f"outlook_{x}@outlook.com",
                    }
                },
            }
            for x in range(record_count)
        ]

        self.assertFalse(
            self.match(self.organizer_user, recurring_event_data),
            "No odoo record should correspond to the microsoft values",
        )
