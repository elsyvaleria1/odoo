from datetime import datetime

from odoo.tests import tagged

from odoo.addons.hr_holidays.tests.common import TestHolidayContract


@tagged("post_install", "-at_install")
class TestLeaveDuration(TestHolidayContract):
    def test_an_enforced_booking_does_not_shorten_time_off(self):
        start, stop = datetime(2015, 11, 17, 7, 0), datetime(2015, 11, 17, 18, 0)
        control = self.create_leave(start, stop, employee_id=self.jules_emp.id)
        expected = control.number_of_hours, control.number_of_days
        control.unlink()
        self.env["resource.reservation"].create(
            {
                "name": "Appointment with enforced capacity",
                "resource_id": self.jules_emp.resource_id.id,
                "date_start": datetime(2015, 11, 17, 9, 0),
                "date_end": datetime(2015, 11, 17, 13, 0),
                "allocated_percentage": 10,
                "enforcement_mode": "hard",
            }
        )
        leave = self.create_leave(start, stop, employee_id=self.jules_emp.id)
        self.assertEqual((leave.number_of_hours, leave.number_of_days), expected)

    def test_a_past_period_reads_the_schedule_it_had(self):
        monday = (datetime(2015, 6, 1), datetime(2015, 6, 2))
        per_day = self.jules_emp._get_work_time_per_day(*monday)[self.jules_emp.id]
        self.assertEqual(per_day, [(monday[0].date(), 8.0)], "the 40h contract")
        leave_days = self.jules_emp._get_leave_duration_data_batch(*monday)[
            self.jules_emp.id
        ]
        self.assertEqual(leave_days, {"days": 0, "hours": 0})
