from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestResendPayslipGuards(TransactionCase):
    def test_resend_requires_payroll_group(self):
        basic_user = new_test_user(
            self.env, login="doc_payroll_basic", groups="base.group_user"
        )
        with self.assertRaises(UserError):
            self.env["hr.payslip"].with_user(basic_user).action_resend_payslips()

    def test_resend_warns_on_unvalidated_payslips(self):
        payroll_user = new_test_user(
            self.env,
            login="doc_payroll_officer",
            groups="base.group_user,hr_payroll.group_hr_payroll_user",
        )
        employee = self.env["hr.employee"].create({"name": "Paid Employee"})
        payslip = self.env["hr.payslip"].create(
            {"name": "Draft Slip", "employee_id": employee.id}
        )
        self.assertEqual(payslip.state, "draft")

        action = payslip.with_user(payroll_user).action_resend_payslips()
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "warning")
        self.assertIn("validated or paid", action["params"]["message"])

    def test_employee_resend_reports_skipped_payslips(self):
        payroll_user = new_test_user(
            self.env,
            login="doc_payroll_officer_2",
            groups="base.group_user,hr_payroll.group_hr_payroll_user",
        )
        employee = self.env["hr.employee"].create({"name": "No Mail Employee"})
        employee.partner_id.email = False
        employee.private_email = False
        employee.work_email = False
        payslip = self.env["hr.payslip"].create(
            {"name": "Validated Slip", "employee_id": employee.id}
        )
        self.env.cr.execute(
            "UPDATE hr_payslip SET state='validated' WHERE id=%s", (payslip.id,)
        )
        payslip.invalidate_recordset()
        self.env["document.document"].create(
            {
                "name": "slip.pdf",
                "res_model": "hr.payslip",
                "res_id": payslip.id,
                "datas": "JVBERi0xLjQK",
                "access_via_link": "view",
                "access_ids": [
                    Command.create(
                        {"partner_id": payroll_user.partner_id.id, "role": "view"}
                    )
                ],
            }
        )
        self.assertTrue(
            payslip.with_user(payroll_user).document_access_url,
            "Precondition: the acting user must see the payslip document",
        )

        mails_before = self.env["mail.mail"].sudo().search_count([])
        action = employee.with_user(payroll_user).action_resend_payslips()
        mails_after = self.env["mail.mail"].sudo().search_count([])

        self.assertEqual(mails_after, mails_before, "Nothing must have been sent")
        self.assertEqual(action["params"]["type"], "warning")
        self.assertIn("email must be set", action["params"]["message"])
