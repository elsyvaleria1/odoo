from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPayrollCreateComputes(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create({"name": "Weekly worker"})
        cls.weekly = cls.env["hr.payroll.structure.type"].create(
            {
                "name": "Weekly hourly",
                "default_schedule_pay": "weekly",
                "wage_type": "hourly",
            }
        )

    def test_a_version_takes_the_pay_schedule_of_its_structure_type(self):
        version = self.env["hr.version"].create(
            {
                "employee_id": self.employee.id,
                "date_version": "2031-02-01",
                "structure_type_id": self.weekly.id,
            }
        )

        self.assertEqual(version.schedule_pay, "weekly")

    def test_a_payslip_batch_takes_the_pay_schedule_of_its_structure(self):
        structure = self.env["hr.payroll.structure"].create(
            {"name": "Weekly structure", "type_id": self.weekly.id}
        )

        batch = self.env["hr.payslip.run"].create(
            {"name": "Week 5", "structure_id": structure.id}
        )

        self.assertEqual(batch.schedule_pay, "weekly")
        self.assertTrue(batch.date_start < batch.date_end)

    def test_a_payslip_batch_without_structure_is_monthly(self):
        batch = self.env["hr.payslip.run"].create({"name": "September"})

        self.assertEqual(batch.schedule_pay, "monthly")
        self.assertEqual(batch.date_start.day, 1)

    def test_an_attachment_of_an_open_ended_input_type_is_unlimited(self):
        input_type = self.env["hr.payslip.input.type"].create(
            {"name": "Garnishment", "code": "GARN1B", "default_no_end_date": True}
        )

        attachment = self.env["hr.salary.attachment"].create(
            {
                "employee_ids": [Command.link(self.employee.id)],
                "description": "Court order",
                "monthly_amount": 10,
                "total_amount": 100,
                "date_start": "2026-01-01",
                "other_input_type_id": input_type.id,
            }
        )

        self.assertEqual(attachment.duration_type, "unlimited")
