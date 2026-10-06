from datetime import date, datetime

from odoo import fields, tests

from odoo.addons.hr_holidays.tests.common import TestHrHolidaysCommon


@tests.tagged("post_install", "-at_install")
class TestHrHolidaysMultiCompanyCommon(TestHrHolidaysCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_2 = cls.env["res.company"].create({"name": "Test company 2"})

    def _pending_allocation_of_company_2(self):
        schedule = self.env["resource.calendar"].create(
            {"name": "Schedule of company 2", "company_id": self.company_2.id}
        )
        worker = self.env["hr.employee"].create(
            {
                "name": "Worker of company 2",
                "company_id": self.company_2.id,
                "resource_calendar_id": schedule.id,
            }
        )
        leave_type = self.env["hr.leave.type"].create(
            {
                "name": "Days of company 2",
                "requires_allocation": True,
                "allocation_validation_type": "no_validation",
                "company_id": False,
            }
        )
        allocation = (
            self.env["hr.leave.allocation"]
            .sudo()
            .create(
                {
                    "name": "Two days",
                    "employee_id": worker.id,
                    "holiday_status_id": leave_type.id,
                    "number_of_days": 2,
                    "date_from": fields.Date.today(),
                }
            )
        )
        self.assertNotIn(
            self.company_2,
            self.user_hruser.company_ids | self.user_employee.company_ids,
        )
        hours_per_day = schedule.hours_per_day
        self.env.flush_all()
        allocation.number_of_days = 3
        self.assertTrue(
            self.env.is_to_compute(
                allocation._fields["number_of_hours_display"], allocation
            )
        )
        self.env["resource.calendar"].invalidate_model()
        return allocation, hours_per_day

    def test_a_pending_allocation_display_is_computed_whoever_flushes_it(self):
        allocation, hours_per_day = self._pending_allocation_of_company_2()
        self.env(user=self.user_hruser).flush_all()
        self.assertEqual(allocation.number_of_hours_display, 3 * hours_per_day)

    def test_a_leave_request_raising_its_approval_flushes_another_company_s_allocation(
        self,
    ):
        allocation, hours_per_day = self._pending_allocation_of_company_2()
        leave_type = self.env["hr.leave.type"].create(
            {
                "name": "Needs the officer",
                "requires_allocation": False,
                "leave_validation_type": "hr",
                "company_id": False,
            }
        )
        leave = (
            self.env["hr.leave"]
            .with_user(self.user_employee)
            .create(
                {
                    "name": "A day off",
                    "employee_id": self.employee_emp_id,
                    "holiday_status_id": leave_type.id,
                    "request_date_from": date(2024, 1, 10),
                    "request_date_to": date(2024, 1, 10),
                }
            )
        )
        self.assertTrue(leave)
        self.assertEqual(allocation.number_of_hours_display, 3 * hours_per_day)

    def test_unrelated_public_leave(self):
        public_leave = self.env["resource.schedule.exception"].create(
            {
                "name": "Global Time Off for Company 2",
                "resource_id": False,
                "date_from": datetime(2024, 1, 3, 6, 0, 0),
                "date_to": datetime(2024, 1, 3, 19, 0, 0),
            }
        )
        public_leave.company_id = self.company_2
        leave_type = self.env["hr.leave.type"].create(
            {
                "name": "Test Leave Type",
                "requires_allocation": False,
                "request_unit": "day",
                "company_id": False,
            }
        )
        leave = self.env["hr.leave"].create(
            {
                "name": "3 days leave",
                "employee_id": self.employee_emp_id,
                "holiday_status_id": leave_type.id,
                "request_date_from": date(2024, 1, 2),
                "request_date_to": datetime(2024, 1, 4),
            }
        )
        self.assertNotEqual(public_leave.company_id, self.employee_emp.company_id)
        self.assertEqual(
            leave.number_of_days,
            3,
            "The leave should not depend on other companies public leaves.",
        )

    def test_the_columns_the_company_rules_filter_are_indexed(self):
        """The global company rules must not make every read a sequential scan.

        `hr_leave_rule_multicompany` puts `company_id` in the domain of every
        read of a time off, and `hr_leave_allocation_rule_multicompany` reaches
        `holiday_status_id.company_id`, which the ORM resolves by joining
        through that Many2one (`_traverse_related_sql`). Both columns carry the
        weight of the security layer on every query, so neither may be left
        without an index.
        """
        expected = {
            ("hr_leave", "company_id"),
            ("hr_leave", "holiday_status_id"),
            ("hr_leave_allocation", "holiday_status_id"),
        }
        missing = set()
        for table, column in sorted(expected):
            self.env.cr.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = %s AND indexdef LIKE %s",
                (table, f"%({column})%"),
            )
            if not self.env.cr.fetchall():
                missing.add(f"{table}.{column}")
        self.assertFalse(
            missing,
            "no index covers %s, so the multi-company guards scan the "
            "whole table on every read" % ", ".join(sorted(missing)),
        )
