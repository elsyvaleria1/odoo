from odoo.tests import common


class TestRecurrentEventLegacy(common.TransactionCase):
    def setUp(self):
        super().setUp()

        self.CalendarEvent = self.env["calendar.event"]

    def test_recurrent_meeting1(self):
        self.CalendarEvent.create(
            {
                "repeat_number": 5,
                "start": "2011-04-13 11:04:00",
                "stop": "2011-04-13 12:04:00",
                "duration": 1.0,
                "name": "Test Meeting",
                "recurrency": True,
                "repeat_unit": "day",
            }
        )
        meetings_count = self.CalendarEvent.with_context(
            {"virtual_id": True}
        ).search_count([("start", ">=", "2011-03-13"), ("stop", "<=", "2011-05-13")])
        self.assertEqual(meetings_count, 5, "Recurrent daily meetings are not created!")

    def test_recurrent_meeting2(self):
        self.CalendarEvent.create(
            {
                "start": "2011-04-18 11:47:00",
                "stop": "2011-04-18 12:47:00",
                "day": 1,
                "duration": 1.0,
                "repeat_until": "2011-04-30",
                "repeat_type": "until",
                "fri": True,
                "mon": True,
                "thu": True,
                "tue": True,
                "wed": True,
                "name": "Review code with programmer",
                "recurrency": True,
                "repeat_unit": "week",
            }
        )

        meetings_count = self.CalendarEvent.search_count(
            [("start", ">=", "2011-03-13"), ("stop", "<=", "2011-05-13")]
        )
        self.assertEqual(
            meetings_count, 10, "Recurrent weekly meetings are not created!"
        )
