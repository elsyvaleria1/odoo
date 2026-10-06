from freezegun import freeze_time

from odoo.tests.common import tagged

from odoo.addons.hr_payroll_holidays.tests.common import TestPayrollHolidaysBase


@tagged("post_install", "-at_install")
class TestLeaveStateChange(TestPayrollHolidaysBase):
    @freeze_time("2018-02-24 10:00:00")
    def test_leave_back_to_approval_leave_when_not_in_confirm_payslip(self):
        """
        ================================================================================================================
        | case 1: An approved leave can be moved back to confirm state if leave is not in done/paid payslip.           |
        | case 2: An approved leave can't be moved back to confirm state if leave is in done/paid payslip.             |
        ================================================================================================================
        """
        unpaid_leave_type = self.env["hr.leave.type"].create(
            {
                "name": "unpaid leave in days",
                "request_unit": "day",
                "leave_validation_type": "both",
                "requires_allocation": False,
                "work_entry_type_id": self.work_entry_type_unpaid.id,
            }
        )
        unpaid_leave = (
            self.env["hr.leave"]
            .with_user(self.emp.user_id)
            .create(
                {
                    "name": "unpaid leave for 3 days",
                    "employee_id": self.emp.id,
                    "holiday_status_id": unpaid_leave_type.id,
                    "request_date_from": "2018-02-23",
                    "request_date_to": "2018-02-25",
                }
            )
        )

        unpaid_leave.with_user(self.joseph.id).action_approve()
        unpaid_leave.with_user(self.joseph.id).action_back_to_approval()
        self.assertEqual(
            unpaid_leave.state,
            "confirm",
            "Approved leave can be moved back to confirm state as long as not included in the done/paid payslip",
        )

        unpaid_leave.with_user(self.joseph).action_approve()
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Donald Payslip",
                "employee_id": self.emp.id,
            }
        )
        payslip.compute_sheet()
        payslip.action_payslip_done()
        unpaid_leave.with_user(self.joseph).action_back_to_approval()
        self.assertEqual(
            unpaid_leave.state,
            "validate",
            "Approved leave can't be moved back to confirm state if included in done/paid payslip",
        )

    def test_payslip_coverage_checks_on_empty_recordset(self):
        """
        The payslip-coverage check used to crash with ValueError: max()
        iterable argument is empty when called on an empty hr.leave recordset
        (F1), because it built a search domain from max()/min() of an empty
        mapped() list with no guard for `not self`. It must behave as a no-op
        instead.
        """
        empty_leaves = self.env["hr.leave"]
        self.assertFalse(
            empty_leaves._leaves_covered_by_validated_payslip(),
            "Should return an empty recordset for an empty recordset, not raise",
        )
        try:
            empty_leaves._check_uncovered_by_validated_payslip()
        except ValueError:
            self.fail(
                "_check_uncovered_by_validated_payslip raised on an empty "
                "recordset instead of behaving as a no-op"
            )
