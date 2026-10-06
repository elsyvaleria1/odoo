from datetime import timedelta
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tools.date_utils import utcnow

from .common import AttendanceTelegramTestCase


class TestLunchHoursComputed(AttendanceTelegramTestCase):
    def test_lunch_hours_computed_correctly(self):
        check_in = self.get_utc_datetime(-4)
        lunch_out = self.get_utc_datetime(-2)
        lunch_in = self.get_utc_datetime(-1)

        attendance = self.create_attendance(
            check_in=check_in,
            lunch_out=lunch_out,
            lunch_in=lunch_in,
        )

        self.assertAlmostEqual(attendance.lunch_hours, 1.0, places=2)

    def test_lunch_hours_90_minutes(self):
        check_in = self.get_utc_datetime(-5)
        lunch_out = self.get_utc_datetime(-3)
        lunch_in = lunch_out + timedelta(minutes=90)

        attendance = self.create_attendance(
            check_in=check_in,
            lunch_out=lunch_out,
            lunch_in=lunch_in,
        )

        self.assertAlmostEqual(attendance.lunch_hours, 1.5, places=2)

    def test_lunch_hours_zero_without_lunch_times(self):
        attendance = self.create_attendance()
        self.assertEqual(attendance.lunch_hours, 0.0)

    def test_lunch_hours_zero_with_only_lunch_out(self):
        check_in = self.get_utc_datetime(-4)
        lunch_out = self.get_utc_datetime(-1)

        attendance = self.create_attendance(
            check_in=check_in,
            lunch_out=lunch_out,
        )

        self.assertEqual(attendance.lunch_hours, 0.0)


class TestLunchTimeConstraints(AttendanceTelegramTestCase):
    def test_lunch_out_before_check_in_raises_error(self):
        check_in = self.get_utc_datetime()
        lunch_out = check_in - timedelta(hours=1)

        with self.assertRaises(ValidationError):
            self.create_attendance(
                check_in=check_in,
                lunch_out=lunch_out,
            )

    def test_lunch_out_after_check_out_raises_error(self):
        check_in = self.get_utc_datetime(-8)
        check_out = self.get_utc_datetime(-1)
        lunch_out = self.get_utc_datetime()

        with self.assertRaises(ValidationError):
            self.create_attendance(
                check_in=check_in,
                check_out=check_out,
                lunch_out=lunch_out,
            )

    def test_lunch_in_without_lunch_out_raises_error(self):
        check_in = self.get_utc_datetime(-4)
        lunch_in = self.get_utc_datetime(-1)

        with self.assertRaises(ValidationError):
            self.create_attendance(
                check_in=check_in,
                lunch_in=lunch_in,
            )

    def test_lunch_in_before_lunch_out_raises_error(self):
        check_in = self.get_utc_datetime(-4)
        lunch_out = self.get_utc_datetime(-1)
        lunch_in = self.get_utc_datetime(-2)

        with self.assertRaises(ValidationError):
            self.create_attendance(
                check_in=check_in,
                lunch_out=lunch_out,
                lunch_in=lunch_in,
            )

    def test_lunch_in_after_check_out_raises_error(self):
        check_in = self.get_utc_datetime(-8)
        lunch_out = self.get_utc_datetime(-4)
        check_out = self.get_utc_datetime(-2)
        lunch_in = self.get_utc_datetime(-1)

        with self.assertRaises(ValidationError):
            self.create_attendance(
                check_in=check_in,
                check_out=check_out,
                lunch_out=lunch_out,
                lunch_in=lunch_in,
            )

    def test_valid_lunch_times_accepted(self):
        check_in = self.get_utc_datetime(-8)
        lunch_out = self.get_utc_datetime(-4)
        lunch_in = self.get_utc_datetime(-3)
        check_out = self.get_utc_datetime(-1)

        attendance = self.create_attendance(
            check_in=check_in,
            lunch_out=lunch_out,
            lunch_in=lunch_in,
            check_out=check_out,
        )

        self.assertTrue(attendance.id)
        self.assertAlmostEqual(attendance.lunch_hours, 1.0, places=2)


class TestCronAutoCheckout(AttendanceTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.env.cr.execute("DELETE FROM hr_attendance WHERE check_out IS NULL")
        self.env["hr.attendance"].invalidate_model()

    def test_cron_closes_open_attendance_from_yesterday(self):
        yesterday = self.yesterday_utc(hour=9, minute=0)

        attendance = self.create_attendance(check_in=yesterday)
        self.assertFalse(attendance.check_out)

        self.env["hr.attendance"]._cron_auto_checkout_at_day_end()

        attendance.invalidate_recordset()
        self.assertTrue(attendance.check_out)

    def test_cron_closes_an_attendance_opened_on_a_non_working_day(self):
        uncovered = self.yesterday_utc(hour=9, minute=0)
        weekday = str(uncovered.date().weekday())
        self.test_employee.resource_calendar_id.attendance_ids.filtered(
            lambda a, wd=weekday: a.dayofweek == wd
        ).unlink()

        attendance = self.create_attendance(check_in=uncovered)
        self.assertFalse(attendance.check_out)

        self.env["hr.attendance"]._cron_auto_checkout_at_day_end()

        attendance.invalidate_recordset()
        self.assertTrue(
            attendance.check_out,
            "an attendance opened on a day the calendar does not cover used to "
            "stay open forever and be re-scanned by every cron run",
        )

    def test_cron_ignores_todays_open_attendance(self):
        today = utcnow().replace(hour=9, minute=0, second=0, microsecond=0)

        attendance = self.create_attendance(check_in=today)
        self.assertFalse(attendance.check_out)

        self.env["hr.attendance"]._cron_auto_checkout_at_day_end()

        attendance.invalidate_recordset()
        self.assertFalse(attendance.check_out)

    def test_cron_ignores_already_closed_attendance(self):
        yesterday = self.yesterday_utc(hour=9, minute=0)
        yesterday_checkout = yesterday + timedelta(hours=8)

        attendance = self.create_attendance(
            check_in=yesterday,
            check_out=yesterday_checkout,
        )

        original_checkout = attendance.check_out

        self.env["hr.attendance"]._cron_auto_checkout_at_day_end()

        attendance.invalidate_recordset()
        self.assertEqual(attendance.check_out, original_checkout)

    def test_cron_skips_a_fully_flexible_employee(self):
        employee_no_cal = self.env["hr.employee"].create(
            {
                "name": "No Calendar Employee",
            }
        )
        employee_no_cal.resource_calendar_id = False

        yesterday = self.yesterday_utc(hour=9, minute=0)

        attendance = self.create_attendance(
            check_in=yesterday,
            employee=employee_no_cal,
        )

        self.env["hr.attendance"]._cron_auto_checkout_at_day_end()

        attendance.invalidate_recordset()
        self.assertFalse(attendance.check_out)

    def test_cron_handles_shift_ending_at_midnight(self):
        calendar_24 = self.env["resource.calendar"].create(
            {
                "name": "Ends at midnight",
                "attendance_ids": [
                    Command.create(
                        {
                            "name": f"day{d}",
                            "dayofweek": str(d),
                            "hour_from": 8.0,
                            "hour_to": 24.0,
                        }
                    )
                    for d in range(7)
                ],
            }
        )
        employee = self.env["hr.employee"].create(
            {"name": "Midnight Shift", "resource_calendar_id": calendar_24.id}
        )
        attendance = self.create_attendance(
            check_in=self.yesterday_utc(hour=9), employee=employee
        )

        self.env["hr.attendance"]._cron_auto_checkout_at_day_end()

        attendance.invalidate_recordset()
        self.assertTrue(attendance.check_out)

    def test_cron_isolates_a_failing_record(self):
        att = self.create_attendance(check_in=self.yesterday_utc(hour=9))
        with patch.object(
            type(self.env["hr.attendance"]),
            "message_post",
            side_effect=ValidationError("boom"),
        ):
            self.env["hr.attendance"]._cron_auto_checkout_at_day_end()

        att.invalidate_recordset()
        self.assertFalse(att.check_out)


class TestAttendanceCreation(AttendanceTelegramTestCase):
    def test_create_attendance_with_check_in(self):
        attendance = self.create_attendance()
        self.assertTrue(attendance.check_in)
        self.assertFalse(attendance.check_out)
        self.assertEqual(attendance.employee_id, self.test_employee)

    def test_create_full_attendance_record(self):
        check_in = self.get_utc_datetime(-8)
        lunch_out = self.get_utc_datetime(-4)
        lunch_in = self.get_utc_datetime(-3)
        check_out = self.get_utc_datetime()

        attendance = self.create_attendance(
            check_in=check_in,
            lunch_out=lunch_out,
            lunch_in=lunch_in,
            check_out=check_out,
        )

        self.assertEqual(attendance.check_in, check_in)
        self.assertEqual(attendance.check_out, check_out)
        self.assertEqual(attendance.lunch_out, lunch_out)
        self.assertEqual(attendance.lunch_in, lunch_in)
        self.assertAlmostEqual(attendance.lunch_hours, 1.0, places=2)
