from datetime import datetime

from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSchedulingCalendarResolution(TransactionCase):
    """Which working calendar governs a record being scheduled.

    ``_scheduling_resolve_calendar`` walks a three-step fallback: the record's
    own calendar, its company's, then the current company's. Everything scheduled on the record -- when work may start,
    which hours count -- follows from the answer.
    """

    MODEL_NAME = "resource.scheduling.test"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Calendar = cls.env["resource.calendar"]
        cls.resource_calendar = Calendar.create({"name": "Resource hours", "tz": "UTC"})
        cls.record_calendar = Calendar.create({"name": "Record hours", "tz": "UTC"})
        cls.company_calendar = cls.env.company.resource_calendar_id

        cls.resource_with_hours = cls.env["resource.resource"].create(
            {"name": "Staffed", "calendar_id": cls.resource_calendar.id}
        )

    def _record(self, calendar=None):
        record = self.env[self.MODEL_NAME].create({"name": "Scheduled work"})
        record.resource_calendar_id = calendar or False
        return record

    def test_the_record_keeps_its_own_hours_when_no_resource_is_given(self):
        """Asked on its own, the record answers with its calendar."""
        record = self._record(self.record_calendar)
        self.assertEqual(record._scheduling_resolve_calendar(), self.record_calendar)

    def test_a_record_without_hours_falls_back_to_its_company(self):
        """Nothing set on the record means the company's working hours."""
        record = self._record()
        self.assertFalse(record.resource_calendar_id)
        self.assertEqual(record._scheduling_resolve_calendar(), self.company_calendar)

    def test_the_fallback_never_answers_with_nothing(self):
        """The chain always ends on a calendar, never on an empty one.

        A record with no hours anywhere would silently schedule nothing.
        """
        record = self._record()
        self.assertTrue(record._scheduling_resolve_calendar())

    def test_an_explicit_schedule_decides_the_hours_of_a_fixed_resource(self):
        mornings = self.env["resource.calendar"].create(
            {
                "name": "Mornings",
                "tz": "UTC",
                "attendance_ids": [Command.clear()]
                + [
                    Command.create(
                        {
                            "name": f"Day {day}",
                            "dayofweek": str(day),
                            "hour_from": 8,
                            "hour_to": 12,
                        }
                    )
                    for day in range(5)
                ],
            }
        )
        record = self._record()
        start, stop = datetime(2025, 1, 6), datetime(2025, 1, 7)
        resource = self.resource_with_hours
        self.assertEqual(
            record._scheduling_get_work_hours(start, stop, resource=resource), 8.0
        )
        self.assertEqual(
            record._scheduling_get_work_hours(
                start, stop, resource=resource, calendar=mornings
            ),
            4.0,
        )
