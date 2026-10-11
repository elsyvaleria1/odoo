from odoo.tests import tagged

from .common import TestPayslipBase


@tagged("post_install", "-at_install")
class TestPayslipLineReport(TestPayslipBase):

    def test_group_payslip_lines_by_structure(self):
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
            }
        )
        payslip.compute_sheet()
        self.assertTrue(payslip.line_ids)

        groups = self.env["hr.payslip.line"]._read_group(
            [("slip_id", "=", payslip.id)], ["struct_id"], ["__count"]
        )
        self.assertEqual(groups, [(payslip.struct_id, len(payslip.line_ids))])
