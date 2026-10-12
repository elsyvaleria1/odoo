from datetime import date

from odoo.tests import Form, tagged

from .common import TestPayslipBase


@tagged("post_install", "-at_install")
class TestPayslipRunAssignment(TestPayslipBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.january = cls.env["hr.payslip.run"].create(
            {
                "name": "January 2025",
                "date_start": date(2025, 1, 1),
                "date_end": date(2025, 1, 31),
            }
        )
        cls.february = cls.env["hr.payslip.run"].create(
            {
                "name": "February 2025",
                "date_start": date(2025, 2, 1),
                "date_end": date(2025, 2, 28),
            }
        )

    def _january_payslip(self):
        return self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 1, 31),
                "payslip_run_id": self.january.id,
            }
        )

    def _period_warnings(self, payslip):
        return [
            issue
            for issue in (payslip.issues or {}).values()
            if issue["message"] == "The payslip period does not match the pay run"
        ]

    def test_matching_period_raises_no_warning(self):
        payslip = self._january_payslip()
        self.assertFalse(self._period_warnings(payslip))

    def test_mismatching_period_warns(self):
        payslip = self._january_payslip()
        payslip.payslip_run_id = self.february
        self.assertTrue(self._period_warnings(payslip))

    def test_off_cycle_payslip_raises_no_warning(self):
        payslip = self._january_payslip()
        payslip.payslip_run_id = False
        self.assertFalse(self._period_warnings(payslip))

    def test_pay_run_stays_editable_once_validated(self):
        payslip = self._january_payslip()
        payslip.action_validate()
        self.assertEqual(payslip.state, "validated")

        with Form(payslip) as form:
            form.payslip_run_id = self.february
        self.assertEqual(payslip.payslip_run_id, self.february)
