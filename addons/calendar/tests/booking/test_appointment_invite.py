from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo.tests import Form, users

from odoo.addons.calendar.tests.booking.common import AppointmentCommon


class AppointmentInviteTest(AppointmentCommon):
    @users("apt_manager")
    def test_acquire_share_url_creates_and_reuses_invitation(self):
        appointment_type = self.apt_type_bxls_2days.copy({"name": "Share acquisition"})
        invitations = self.env["appointment.invite"]
        domain = [("appointment_type_ids", "in", appointment_type.ids)]
        self.assertFalse(invitations.search(domain))
        url = appointment_type.acquire_share_url()
        invitation = invitations.search(domain)
        self.assertEqual(len(invitation), 1)
        self.assertEqual(invitation.resources_choice, "all_assigned_resources")
        self.assertEqual(url, invitation.book_url)
        self.assertEqual(appointment_type.acquire_share_url(), url)
        self.assertEqual(invitations.search(domain), invitation)

    def test_gc_appointment_invite(self):
        appt_invite = self.env["appointment.invite"].create(
            {
                "appointment_type_ids": [(4, self.apt_type_bxls_2days.id)],
                "create_date": self.reference_now - relativedelta(months=8),
            }
        )
        meeting_1, meeting_2 = self._create_meetings(
            self.staff_user_bxls,
            [
                (
                    self.reference_now - relativedelta(months=5, hours=1),
                    self.reference_now - relativedelta(months=5),
                    False,
                ),
                (
                    self.reference_now - relativedelta(months=7, hours=1),
                    self.reference_now - relativedelta(months=7),
                    False,
                ),
            ],
        )
        (meeting_1 | meeting_2).appointment_invite_id = appt_invite.id

        with freeze_time(self.reference_now):
            self.env["appointment.invite"]._gc_appointment_invite()
        self.assertTrue(appt_invite.exists())

        meeting_1.unlink()
        with freeze_time(self.reference_now):
            self.env["appointment.invite"]._gc_appointment_invite()
        self.assertFalse(appt_invite.exists())

    @users("apt_manager")
    def test_short_code_generation(self):
        apt_users = self.apt_manager + self.staff_users
        appointment_types = self.env["appointment.type"].create(
            [
                {
                    "name": f"Test Users {i}",
                    "schedule_based_on": "users",
                    "staff_user_ids": apt_users.ids,
                }
                for i in range(2)
            ]
        )

        AppointmentInvite1 = self.env["appointment.invite"].with_context(
            default_appointment_type_ids=[appointment_types[0].id]
        )
        AppointmentInvite2 = self.env["appointment.invite"].with_context(
            default_appointment_type_ids=[appointment_types[1].id]
        )
        with Form(AppointmentInvite1) as appointment_invite:
            self.assertEqual(
                appointment_invite.short_code,
                "test-users-0",
                "Appointment name based short_code should be generated",
            )
            appointment_invite.short_code = "code-to-reuse"

        appointment_invite_reuse = Form(AppointmentInvite1)
        self.assertEqual(
            appointment_invite_reuse.short_code,
            "code-to-reuse",
            "The existing short_code should be retrieved",
        )

        with Form(AppointmentInvite2) as appointment_invite_other_config:
            appointment_invite_other_config.resources_choice = "all_assigned_resources"
            self.assertEqual(appointment_invite_other_config.short_code, "test-users-1")

        appointment_invite_different_config = Form(AppointmentInvite2)
        self.assertNotEqual(
            appointment_invite_different_config.short_code,
            "test-users-1",
            "The random short_code should be generated",
        )

        appointment_invite_change_config = Form(AppointmentInvite1)
        self.assertEqual(appointment_invite_change_config.short_code, "code-to-reuse")
        appointment_invite_change_config.resources_choice = "all_assigned_resources"
        self.assertNotEqual(
            appointment_invite_change_config.short_code,
            "code-to-reuse",
            "The random short_code should be generated when config changes",
        )

        with Form(AppointmentInvite1) as appointment_invite_change_code:
            appointment_invite_change_code.short_code = "custom-code"
        self.assertEqual(
            appointment_invite_change_code.short_code,
            "custom-code",
            "A new share link should be created",
        )
