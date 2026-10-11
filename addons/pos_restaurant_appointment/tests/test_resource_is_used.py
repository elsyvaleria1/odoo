from datetime import datetime

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestResourceIsUsed(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.appointment_type = cls.env["appointment.type"].create(
            {
                "name": "Table Booking",
                "schedule_based_on": "resources",
                "manage_capacity": True,
                "event_videocall_source": False,
            }
        )
        cls.table = cls.env["resource.resource"].create(
            {
                "name": "Table 1",
                "type": "material",
                "capacity": 4,
                "appointment_type_ids": [(6, 0, cls.appointment_type.ids)],
            }
        )
        cls.env["calendar.event"].create(
            {
                "name": "Dinner",
                "start": datetime(2026, 10, 5, 1, 30),
                "stop": datetime(2026, 10, 5, 3, 0),
                "appointment_type_id": cls.appointment_type.id,
                "booking_line_ids": [
                    (0, 0, {"resource_id": cls.table.id, "capacity_reserved": 2})
                ],
            }
        )

    def _is_used(self, start_date):
        return self.table.with_context(
            start_date=start_date, tz="America/Mexico_City"
        ).is_used

    def test_an_evening_booking_counts_on_the_users_local_day(self):
        is_used = self._is_used("2026-10-04 18:00:00")

        self.assertEqual(is_used["event_start"], "2026-10-05 01:30:00")
        self.assertEqual(is_used["capacity"], 2)

    def test_the_next_local_day_does_not_see_it(self):
        self.assertFalse(self._is_used("2026-10-05 18:00:00"))

    def test_no_start_date_means_no_usage(self):
        self.assertFalse(self.table.with_context(start_date=False).is_used)
