from unittest.mock import patch

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("post_install", "-at_install")
class TestPayrollGuards(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Guarded employee", "contract_date_start": "2024-01-01"}
        )

    def test_a_non_payroll_officer_can_write_a_version(self):
        """The payslip-recompute field lookup reads wage_type, a
        payroll-groups field: it must not break a plain hr officer's write."""
        officer = mail_new_test_user(
            self.env,
            name="hr officer without payroll",
            login="guards_hr_officer",
            groups="base.group_user,hr.group_hr_user",
        )
        version = self.employee.version_id
        version.with_user(officer).write({"job_title": "Head of Guards"})
        self.assertEqual(version.job_title, "Head of Guards")

    def test_a_cleared_type_schedule_falls_back_to_monthly(self):
        structure_type = self.env["hr.payroll.structure.type"].create(
            {"name": "Cleared schedule type"}
        )
        structure_type.default_schedule_pay = False
        version = self.employee.version_id
        version.structure_type_id = structure_type
        self.assertEqual(version.schedule_pay, "monthly")

    def test_every_payslip_report_honours_the_error_gate(self):
        payslip = self.env["hr.payslip"].create(
            {"employee_id": self.employee.id, "name": "Guarded slip"}
        )
        Payslip = type(self.env["hr.payslip"])
        error = {"level": "danger", "message": "guarded error"}

        def one_error(slips):
            return {slip: [error] if slip == payslip else [] for slip in slips}

        with patch.object(Payslip, "_get_errors_by_slip", one_error):
            payslip.invalidate_recordset(["error_count", "issues"])
            self.assertTrue(payslip.error_count)
            with self.assertRaises(ValidationError):
                self.env["ir.actions.report"]._render_qweb_pdf(
                    "hr_payroll.action_report_light_payslip", payslip.ids
                )

    def test_a_template_mailing_honours_the_error_gate(self):
        payslips = self.env["hr.payslip"].create(
            [
                {"employee_id": self.employee.id, "name": "Guarded slip"},
                {"employee_id": self.employee.id, "name": "Clean slip"},
            ]
        )
        template = self.env["mail.template"].create(
            {
                "name": "Payslips",
                "model_id": self.env["ir.model"]._get_id("hr.payslip"),
                "report_template_ids": [
                    Command.set(
                        self.env.ref("hr_payroll.action_report_light_payslip").ids
                    )
                ],
            }
        )
        Payslip = type(self.env["hr.payslip"])
        error = {"level": "danger", "message": "guarded error"}

        def one_error(slips):
            return {slip: [error] if slip == payslips[0] else [] for slip in slips}

        with patch.object(Payslip, "_get_errors_by_slip", one_error):
            payslips.invalidate_recordset(["error_count", "issues"])
            with self.assertRaises(ValidationError):
                template.with_context(
                    force_report_rendering=True
                )._prepare_attachment_vals(payslips.ids, {"report_template_ids"})
