from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPaymentFileCompany(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.first = cls.env.company
        cls.second = cls.env["res.company"].create({"name": "Second"})
        cls.first_employee = cls.env["hr.employee"].create(
            {"name": "First employee", "company_id": cls.first.id}
        )
        cls.second_employee = cls.env["hr.employee"].create(
            {"name": "Second employee", "company_id": cls.second.id}
        )

    def setUp(self):
        super().setUp()
        self.first_slip = self.env["hr.payslip"].new(
            {"employee_id": self.first_employee}
        )
        self.second_slip = self.env["hr.payslip"].new(
            {"employee_id": self.second_employee}
        )
        self.wizard_model = self.env["wizard.hr.payslip.export.payment.file"]

    def test_batch_company_takes_priority(self):
        batch = self.env["hr.payslip.run"].new({"company_id": self.second})
        wizard = self.wizard_model.new(
            {"payslip_run_id": batch, "payslip_ids": self.first_slip + self.second_slip}
        )
        for require_single in (False, True):
            self.assertEqual(
                wizard._get_company_for_payment_file(require_single=require_single),
                self.second,
            )
        self.assertEqual(wizard.payslip_ids, self.first_slip + self.second_slip)

    def test_individual_payslips_preserve_first_company_and_validate(self):
        for slips, first in (
            (self.first_slip + self.second_slip, self.first),
            (self.second_slip + self.first_slip, self.second),
        ):
            wizard = self.wizard_model.new({"payslip_ids": slips})
            self.assertEqual(wizard._get_company_for_payment_file(), first)
            with self.assertRaisesRegex(UserError, "one company at a time"):
                wizard._get_company_for_payment_file(require_single=True)
            self.assertEqual(wizard.payslip_ids, slips)

    def test_repeated_company_and_empty_payslips(self):
        same_company_slip = self.env["hr.payslip"].new(
            {"employee_id": self.first_employee}
        )
        wizard = self.wizard_model.new(
            {"payslip_ids": self.first_slip + same_company_slip}
        )
        self.assertEqual(
            wizard._get_company_for_payment_file(require_single=True), self.first
        )
        for require_single in (False, True):
            empty = self.wizard_model.new({})
            self.assertEqual(
                empty._get_company_for_payment_file(require_single=require_single),
                self.env["res.company"],
            )

    def test_requires_one_wizard(self):
        for wizards in (
            self.wizard_model,
            self.wizard_model.new({}) + self.wizard_model.new({}),
        ):
            with self.assertRaises(ValueError):
                wizards._get_company_for_payment_file()
