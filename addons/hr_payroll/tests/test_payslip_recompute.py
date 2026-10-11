from datetime import date
from unittest.mock import patch

from odoo.fields import Command

from .common import TestPayslipContractBase


class TestPayslipRecomputeOnWrite(TestPayslipContractBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.payslip = cls.env["hr.payslip"].create(
            {
                "name": "December 2015",
                "employee_id": cls.richard_emp.id,
                "version_id": cls.contract_cdi.id,
                "struct_id": cls.developer_pay_structure.id,
                "date_from": date(2015, 12, 1),
                "date_to": date(2015, 12, 31),
            }
        )
        cls.payslip.compute_sheet()

    def _house_rent_allowance(self):
        return self.payslip.line_ids.filtered(lambda line: line.code == "HRA").total

    def test_a_wage_change_refreshes_the_draft_payslip(self):
        self.assertAlmostEqual(self._house_rent_allowance(), 5000.33 * 0.4, places=2)
        lines = self.payslip.line_ids
        self.contract_cdi.wage = 6000
        self.assertAlmostEqual(self._house_rent_allowance(), 2400.0, places=2)
        self.assertFalse(lines.exists())

    def test_only_a_listed_employee_field_refreshes_the_draft_payslip(self):
        lines = self.payslip.line_ids
        with patch.object(
            type(self.env["hr.employee"]),
            "_get_employee_fields_that_recompute_payslip",
            lambda employees: ["identification_id"],
            create=True,
        ):
            self.richard_emp.barcode = "4242"
            self.assertTrue(lines.exists())
            self.richard_emp.identification_id = "ID-4242"
        self.assertFalse(lines.exists())


class TestPayslipRecomputeOnInputChange(TestPayslipContractBase):
    """Writing the Salary Inputs tab of a draft payslip that already has lines."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bonus_type = cls.env["hr.payslip.input.type"].create(
            {
                "name": "Test Bonus",
                "code": "TESTBONUS",
            }
        )
        cls.developer_pay_structure.input_line_type_ids = [
            Command.link(cls.bonus_type.id)
        ]
        cls.env["hr.salary.rule"].create(
            {
                "name": "Test Bonus",
                "sequence": 200,
                "code": "TESTBONUS",
                "category_id": cls.env.ref("hr_payroll.ALW").id,
                "struct_id": cls.developer_pay_structure.id,
                "amount_select": "code",
                "amount_python_compute": (
                    "result = inputs['TESTBONUS'].amount if 'TESTBONUS' in inputs else 0.0"
                ),
            }
        )

    def _computed_payslip_with_a_bonus(self, name, amount=100.0):
        payslip = self.env["hr.payslip"].create(
            {
                "name": name,
                "employee_id": self.richard_emp.id,
                "version_id": self.contract_cdi.id,
                "struct_id": self.developer_pay_structure.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )
        bonus = self.env["hr.payslip.input"].create(
            {
                "payslip_id": payslip.id,
                "input_type_id": self.bonus_type.id,
                "amount": amount,
            }
        )
        payslip.compute_sheet()
        return payslip, bonus

    def _bonus_total(self, payslip):
        return payslip._get_line_values(["TESTBONUS"])["TESTBONUS"][payslip.id]["total"]

    def test_an_input_change_refreshes_the_draft_payslip(self):
        payslip, bonus = self._computed_payslip_with_a_bonus("Payslip with a bonus")
        self.assertEqual(self._bonus_total(payslip), 100.0)

        payslip.write({"input_line_ids": [Command.update(bonus.id, {"amount": 150.0})]})
        self.assertEqual(
            self._bonus_total(payslip),
            150.0,
            "Changing an input must bring the salary lines along",
        )

    def test_an_input_change_leaves_a_hand_edited_payslip_alone(self):
        payslip, bonus = self._computed_payslip_with_a_bonus("Hand-edited payslip")
        payslip.edited = True
        payslip.line_ids.filtered(lambda line: line.code == "TESTBONUS").total = 42.0

        payslip.write({"input_line_ids": [Command.update(bonus.id, {"amount": 150.0})]})
        self.assertEqual(
            self._bonus_total(payslip),
            42.0,
            "A hand-edited payslip must not be recomputed behind the user's back",
        )
