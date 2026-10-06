from odoo import tests
from odoo.fields import Command, Date

from .common import TestPayslipBase


@tests.tagged("post_install", "-at_install")
class TestPayslipReport(TestPayslipBase):
    def test_worked_days_hours_printed_as_duration(self):
        """The worked days table of the payslip PDF prints hours as HH:MM.

        7.2 hours is seven hours and twelve minutes, not seven hours and two
        tenths of something. The line and the Total row have to agree.
        """
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.richard_contract.id,
                "struct_id": self.developer_pay_structure.id,
                "date_from": Date.to_date("2026-02-01"),
                "date_to": Date.to_date("2026-02-28"),
                "worked_days_line_ids": [
                    Command.create(
                        {
                            "name": "Attendance",
                            "number_of_days": 1.0,
                            "number_of_hours": 7.2,
                            "work_entry_type_id": self.work_entry_type.id,
                            "version_id": self.richard_contract.id,
                            "amount": 100.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Extra attendance",
                            "number_of_days": 1.0,
                            "number_of_hours": 0.55,
                            "work_entry_type_id": self.work_entry_type_overtime_duty.id,
                            "version_id": self.richard_contract.id,
                            "amount": 10.0,
                        }
                    ),
                ],
            }
        )

        report = self.env.ref("hr_payroll.action_report_payslip")
        html = (
            report.sudo()
            .with_context(lang="en_US")
            ._render_qweb_html(report.report_name, payslip.ids)[0]
            .decode()
        )

        self.assertIn(">07:12<", html, "7.2 hours should print as 07:12")
        self.assertIn(">00:33<", html, "0.55 hours should print as 00:33")
        self.assertIn(">07:45<", html, "the Total row should print as 07:45")
        self.assertNotIn(">7.2<", html, "the raw decimal should not survive")

    def test_draft_payslip_prints_its_warning_text(self):
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Draft payslip of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.richard_contract.id,
                "struct_id": self.developer_pay_structure.id,
                "date_from": Date.to_date("2026-02-01"),
                "date_to": Date.to_date("2026-02-28"),
            }
        )

        warning = payslip._get_invalid_warning()
        report = self.env.ref("hr_payroll.action_report_payslip")
        html = (
            report.with_context(lang="en_US")
            ._render_qweb_html(report.report_name, payslip.ids)[0]
            .decode()
        )

        self.assertEqual(
            warning, "This payslip is not validated. This is not a legal document."
        )
        self.assertIn(warning, html)
        self.assertNotIn(">True<", html)
