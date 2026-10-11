from datetime import date

from freezegun import freeze_time

from odoo.tests import tagged

from .common import TestHrHolidaysCommon


@tagged("post_install", "-at_install")
class TestLeaveResourceState(TestHrHolidaysCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.leave_type = cls.env["hr.leave.type"].create(
            {
                "name": "Vacation",
                "leave_validation_type": "hr",
                "requires_allocation": False,
                "company_id": cls.company.id,
            }
        )
        cls.person = cls.employee_emp.resource_id
        cls.cron = cls.env.ref("hr_holidays.ir_cron_resource_state_from_leaves")

    def _leave(self, date_from, date_to):
        return self.env["hr.leave"].create(
            {
                "name": "Vacation",
                "holiday_status_id": self.leave_type.id,
                "employee_id": self.employee_emp.id,
                "request_date_from": date_from,
                "request_date_to": date_to,
            }
        )

    @freeze_time("2026-03-10 12:00:00")
    def test_an_approved_leave_in_progress_puts_the_person_on_leave(self):
        self.person.action_set_in_service()
        leave = self._leave(date(2026, 3, 9), date(2026, 3, 11))
        self.assertEqual(self.person.state, "in_service")
        leave.action_approve()
        self.assertRecordValues(
            self.employee_emp,
            [{"resource_state": "maintenance"}],
        )
        self.assertEqual(self.person.state_before_maintenance, "in_service")
        leave.action_refuse()
        self.assertEqual(self.employee_emp.resource_state, "in_service")

    @freeze_time("2026-03-10 12:00:00")
    def test_a_person_files_time_off_that_needs_no_approval(self):
        unapproved = self.env["hr.leave.type"].create(
            {
                "name": "Sick",
                "leave_validation_type": "no_validation",
                "requires_allocation": False,
                "company_id": self.company.id,
            }
        )
        self.env["hr.leave"].with_user(self.user_employee_id).create(
            {
                "name": "Sick",
                "holiday_status_id": unapproved.id,
                "employee_id": self.employee_emp.id,
                "request_date_from": date(2026, 3, 10),
                "request_date_to": date(2026, 3, 10),
            }
        )
        self.assertEqual(self.person.state, "maintenance")

    def test_the_hourly_job_follows_a_leave_from_start_to_end(self):
        with freeze_time("2026-03-05 12:00:00"):
            self._leave(date(2026, 3, 9), date(2026, 3, 11)).action_approve()
            self.assertEqual(self.person.state, "available")
            self.cron.lastcall = "2026-03-05 12:00:00"
        with freeze_time("2026-03-10 12:00:00"):
            self.env["resource.resource"]._cron_sync_state_from_leaves()
            self.assertEqual(self.person.state, "maintenance")
            self.cron.lastcall = "2026-03-10 12:00:00"
        with freeze_time("2026-03-12 12:00:00"):
            self.env["resource.resource"]._cron_sync_state_from_leaves()
            self.assertEqual(self.person.state, "available")

    def test_hr_words_name_the_shared_states(self):
        labels = dict(
            self.env["hr.employee"]
            ._fields["resource_state"]
            ._description_selection(self.env)
        )
        self.assertEqual(labels["maintenance"], "On Leave")
        self.assertEqual(labels["disposed"], "Departed")
        self.assertEqual(
            self.env["hr.employee"].search(
                [
                    ("id", "=", self.employee_emp.id),
                    ("resource_state", "=", "available"),
                ]
            ),
            self.employee_emp,
        )
