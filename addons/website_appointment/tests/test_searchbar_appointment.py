from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestSearchbarAppointments(HttpCase):
    def test_search_within_appointments(self):
        self.env["appointment.type"].create(
            {
                "appointment_tz": "UTC",
                "is_auto_assign": True,
                "min_schedule_hours": 1.0,
                "max_schedule_days": 8,
                "min_cancellation_hours": 2,
                "name": "yoga session",
                "manage_capacity": True,
                "schedule_based_on": "resources",
                "is_published": True,
            }
        )
        self.start_tour(
            self.env["website"].get_client_action_url("/"),
            "test_searchbar_within_appointments",
            login="admin",
        )

    def test_appointments_search_in_place(self):
        self.env["appointment.type"].create(
            [
                {"name": name, "appointment_tz": "UTC", "is_published": True}
                for name in ("PN Yoga", "PN Pilates")
            ]
        )
        self.start_tour("/appointment", "appointments_partial_navigation")
