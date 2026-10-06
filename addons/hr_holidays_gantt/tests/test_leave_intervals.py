from datetime import date, datetime

from odoo.tests.common import TransactionCase


class TestLeaveIntervals(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create({"name": "Interval Employee"})
        cls.leave_type = cls.env["hr.leave.type"].create(
            {
                "name": "Gantt Time Off",
                "requires_allocation": False,
                "request_unit": "day",
            }
        )

    def _leave(self, day_from, day_to):
        return self.env["hr.leave"].create(
            {
                "employee_id": self.employee.id,
                "holiday_status_id": self.leave_type.id,
                "request_date_from": day_from,
                "request_date_to": day_to,
            }
        )

    def test_requested_leave_is_collected(self):
        """Check that a confirmed (non-validated) leave shows up in the
        employee's interval map."""
        leave = self._leave(date(2024, 1, 10), date(2024, 1, 11))
        self.assertEqual(leave.state, "confirm")

        intervals = self.env["hr.leave"]._get_leave_interval(
            datetime(2024, 1, 8), datetime(2024, 1, 14), self.employee
        )
        self.assertIn(leave, intervals[self.employee.id])

    def test_validated_leave_is_collected_as_calendar_leave(self):
        """Check that a validated leave reaches the map through its
        resource.schedule.exception record."""
        leave = self._leave(date(2024, 1, 10), date(2024, 1, 11))
        leave.action_approve()

        intervals = self.env["hr.leave"]._get_leave_interval(
            datetime(2024, 1, 8), datetime(2024, 1, 14), self.employee
        )
        collected = intervals[self.employee.id]
        self.assertTrue(collected)
        self.assertTrue(
            any(item._name == "resource.schedule.exception" for item in collected),
            "validated leaves must arrive as resource.schedule.exception",
        )

    def test_leave_warning_wording_for_requested_leave(self):
        """Check that the gantt warning names the employee and uses the
        requested wording for non-validated leaves."""
        self._leave(date(2024, 1, 10), date(2024, 1, 11))
        leaves = self.env["hr.leave"]._get_leave_interval(
            datetime(2024, 1, 8), datetime(2024, 1, 14), self.employee
        )
        warning = self.env["hr.leave"]._get_leave_warning(
            leaves[self.employee.id],
            self.employee,
            datetime(2024, 1, 8),
            datetime(2024, 1, 14),
        )
        self.assertIn("Interval Employee", warning)
        self.assertIn("requested time off", warning)
