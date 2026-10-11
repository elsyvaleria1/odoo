from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGoogleMeetStaffMessage(TransactionCase):
    def test_the_message_computes_for_several_appointment_types_at_once(self):
        appointment_types = self.env["appointment.type"].create(
            [
                {"name": "Meet A", "event_videocall_source": "google_meet"},
                {"name": "Meet B", "event_videocall_source": "google_meet"},
            ]
        )
        appointment_types.invalidate_recordset(["users_wo_google_calendar_msg"])

        appointment_types.mapped("users_wo_google_calendar_msg")
