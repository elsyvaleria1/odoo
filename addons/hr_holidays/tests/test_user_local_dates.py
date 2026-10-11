from datetime import date

from freezegun import freeze_time

from odoo.tests import tagged

from odoo.addons.hr_holidays.tests.common import TestHrHolidaysCommon

UTC_NIGHT = "2026-09-15 01:00:00"
LOCAL_DAY = date(2026, 9, 14)


@tagged("post_install", "-at_install")
class TestUserLocalDates(TestHrHolidaysCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_employee.tz = "America/Mexico_City"
        cls.leave_type = cls.env["hr.leave.type"].create(
            {
                "name": "Paid Time Off",
                "request_unit": "day",
                "leave_validation_type": "hr",
                "requires_allocation": False,
            }
        )

    @freeze_time(UTC_NIGHT)
    def test_new_request_defaults_to_the_users_today(self):
        defaults = (
            self.env["hr.leave"]
            .with_user(self.user_employee)
            .default_get(["request_date_from", "request_date_to"])
        )
        self.assertEqual(defaults["request_date_from"], LOCAL_DAY)
        self.assertEqual(defaults["request_date_to"], LOCAL_DAY)

    @freeze_time(UTC_NIGHT)
    def test_todays_own_leave_is_not_in_the_past_yet(self):
        leave = (
            self.env["hr.leave"]
            .with_user(self.user_employee)
            .create(
                {
                    "name": "Day off",
                    "employee_id": self.employee_emp_id,
                    "holiday_status_id": self.leave_type.id,
                    "request_date_from": LOCAL_DAY,
                    "request_date_to": LOCAL_DAY,
                }
            )
        )
        leave.sudo().state = "validate"

        next_states = leave._get_next_states_by_state()
        self.assertIn(
            "cancel",
            next_states["validate"],
            "an employee whose time off starts today can still cancel it at "
            "19:00 local, even though the server clock already says tomorrow",
        )

        leave._action_user_cancel("changed my mind")
        self.assertEqual(leave.state, "cancel")

    @freeze_time(UTC_NIGHT)
    def test_an_employee_on_leave_today_is_found_absent(self):
        leave = self.env["hr.leave"].create(
            {
                "name": "Day off",
                "employee_id": self.employee_emp_id,
                "holiday_status_id": self.leave_type.id,
                "request_date_from": LOCAL_DAY,
                "request_date_to": LOCAL_DAY,
            }
        )
        leave.sudo().state = "validate"
        absent = (
            self.env["hr.employee"]
            .with_context(tz="America/Mexico_City")
            .search([("is_absent", "=", True)])
        )
        self.assertIn(self.employee_emp, absent)
