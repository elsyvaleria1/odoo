from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.calendar_sync.models.calendar_sync_account import (
    CalendarSyncAccount,
)
from odoo.addons.calendar_sync.models.res_users import ResUsers as CalendarSyncUsers


@tagged("post_install", "-at_install")
@patch.object(CalendarSyncAccount, "_has_client", lambda account, code: True)
class TestAppointmentConnectors(TransactionCase):
    """An appointment type offers every provider a staff member may connect
    their calendar to, one engine for all of them."""

    def setUp(self):
        super().setUp()
        Account = self.env["calendar.sync.account"]
        for code in ("google", "microsoft"):
            Account._set_paused(code, False)
        self.appointment_type = self.env["appointment.type"].create(
            {"name": "Consultation"}
        )

    def test_every_provider_with_a_client_is_offered(self):
        self.assertEqual(
            [c["code"] for c in self.appointment_type.calendar_sync_connectors],
            ["google", "microsoft"],
        )
        outlook = self.appointment_type.calendar_sync_connectors[1]
        self.assertEqual(outlook["label"], "Outlook")
        self.assertTrue(outlook["icon"].endswith("outlook-calendar.svg"))

    def test_a_paused_provider_is_not_offered(self):
        self.env["calendar.sync.account"]._set_paused("microsoft", True)
        self.assertEqual(
            self.appointment_type._get_calendars_possible_to_setup(), ["google"]
        )

    def test_a_connected_calendar_is_set_up(self):
        with patch.object(
            CalendarSyncUsers,
            "_calendar_sync_connection",
            lambda user, code: code == "microsoft" and "a-connection",
        ):
            self.assertEqual(
                self.appointment_type._get_calendars_already_setup(), ["microsoft"]
            )
