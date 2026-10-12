from datetime import datetime, timedelta

from odoo.tests import users

from odoo.addons.calendar.tests.booking.common import AppointmentCommon


class ResPartnerTest(AppointmentCommon):
    def test_availability_uses_shared_civil_day_and_attendance(self):
        partner = self.staff_user_bxls.partner_id
        partner.tz = "Pacific/Kiritimati"
        event = self.env["calendar.event"].create(
            {
                "name": "Civil day availability",
                "allday": True,
                "start_date": "2030-01-07",
                "stop_date": "2030-01-07",
                "partner_ids": [(6, 0, partner.ids)],
            }
        )
        start = datetime(2030, 1, 6, 10)
        self.assertFalse(
            partner._is_calendar_available(start, start + timedelta(minutes=30))
        )
        stop = datetime(2030, 1, 7, 10)
        self.assertTrue(
            partner._is_calendar_available(stop, stop + timedelta(minutes=30))
        )
        event.attendee_ids.do_decline()
        self.assertTrue(
            partner._is_calendar_available(start, start + timedelta(minutes=30))
        )

    @users("staff_user_bxls")
    def test__is_calendar_available(self):
        self._create_meetings(
            self.staff_user_bxls,
            [
                (
                    self.reference_monday + timedelta(days=1),
                    self.reference_monday + timedelta(days=1, hours=3),
                    False,
                ),
                (
                    self.reference_monday + timedelta(days=7, hours=8),
                    self.reference_monday + timedelta(days=7, hours=11),
                    True,
                ),
            ],
        )
        self.assertFalse(
            self.staff_user_bxls.partner_id._is_calendar_available(
                self.reference_monday + timedelta(days=1, hours=2),
                self.reference_monday + timedelta(days=1, hours=4),
            )
        )

        self.assertFalse(
            self.staff_user_bxls.partner_id._is_calendar_available(
                self.reference_monday + timedelta(days=7, hours=4),
                self.reference_monday + timedelta(days=7, hours=8),
            )
        )
        self.assertTrue(
            self.staff_user_bxls.partner_id._is_calendar_available(
                self.reference_monday + timedelta(days=8, hours=3),
                self.reference_monday + timedelta(days=8, hours=4),
            )
        )

        start = self.reference_monday + timedelta(hours=15)
        end = start + timedelta(hours=1)

        self._create_meetings(
            self.staff_user_aust,
            [(start, end, False)],
            self.apt_type_manage_capacity_users.id,
        )

        self.assertFalse(
            self.staff_user_aust.partner_id._is_calendar_available(start, end)
        )

        self.assertFalse(
            self.staff_user_aust.partner_id._is_calendar_available(
                start,
                end,
                self.apt_user_multiple_bookings,
            )
        )

        self.assertTrue(
            self.staff_user_aust.partner_id._is_calendar_available(
                start,
                end,
                self.apt_type_manage_capacity_users,
            )
        )
