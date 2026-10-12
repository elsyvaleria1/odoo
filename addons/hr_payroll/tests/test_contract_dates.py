from datetime import date

from odoo.exceptions import RedirectWarning
from odoo.tests import new_test_user, tagged

from odoo.addons.hr_payroll.tests.common import TestPayslipBase


@tagged("post_install", "-at_install")
class TestContractDates(TestPayslipBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.richard_contract.write(
            {
                "contract_date_start": date(2025, 1, 1),
                "contract_date_end": date(2025, 12, 31),
            }
        )
        cls.bonus_structure = cls.env["hr.payroll.structure"].create(
            {
                "name": "Christmas bonus",
                "type_id": cls.structure_type.id,
            }
        )
        cls.env["hr.salary.rule"].create(
            {
                "name": "Bonus",
                "sequence": 5,
                "code": "BONUS",
                "category_id": cls.env.ref("hr_payroll.ALW").id,
                "struct_id": cls.bonus_structure.id,
                "amount_select": "fix",
                "amount_fix": 500.0,
            }
        )

    def _validated_bonus_payslip(self):
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Christmas bonus of Richard",
                "employee_id": self.richard_emp.id,
                "version_id": self.richard_contract.id,
                "struct_id": self.bonus_structure.id,
                "date_from": date(2025, 3, 1),
                "date_to": date(2025, 3, 31),
            }
        )
        payslip.compute_sheet()
        payslip.action_payslip_done()
        self.assertEqual(payslip.state, "validated")
        return payslip

    def test_start_date_cannot_skip_a_validated_payslip(self):
        payslip = self._validated_bonus_payslip()
        with self.assertRaises(RedirectWarning) as capture:
            self.richard_contract.contract_date_start = date(2025, 6, 1)
            self.richard_contract.flush_recordset()
        self.assertEqual(
            capture.exception.args[1]["domain"],
            [("id", "in", payslip.ids)],
            "The redirect must point at the payslip standing in the way",
        )

    def test_end_date_cannot_skip_a_validated_payslip(self):
        self._validated_bonus_payslip()
        with self.assertRaises(RedirectWarning):
            self.richard_contract.contract_date_end = date(2025, 2, 28)
            self.richard_contract.flush_recordset()

    def test_a_refunded_payslip_stops_blocking(self):
        payslip = self._validated_bonus_payslip()
        payslip.action_payslip_paid()
        payslip.refund_sheet()
        self.assertTrue(payslip.is_refunded)

        self.richard_contract.contract_date_start = date(2025, 6, 1)
        self.richard_contract.flush_recordset()
        self.assertEqual(self.richard_contract.contract_date_start, date(2025, 6, 1))

    def test_a_departure_still_closes_the_contract(self):
        self._validated_bonus_payslip()
        self.richard_emp.departure_reason_id = self.env.ref("hr.departure_resigned")
        self.richard_contract.contract_date_end = date(2025, 2, 28)
        self.richard_contract.flush_recordset()
        self.assertEqual(self.richard_contract.contract_date_end, date(2025, 2, 28))

    def test_an_hr_manager_outside_payroll_ends_a_departed_contract(self):
        manager = new_test_user(
            self.env,
            login="hr_manager_outside_payroll",
            groups="base.group_user,hr.group_hr_manager",
        )
        self.assertFalse(manager.has_group("hr_payroll.group_hr_payroll_user"))
        wizard = (
            self.env["wizard.hr.employee.register.departure"]
            .with_user(manager)
            .with_context(active_ids=self.richard_emp.ids, employee_termination=True)
            .create({"departure_reason_id": self.env.ref("hr.departure_resigned").id})
        )
        self.assertTrue(wizard.set_date_end)
        wizard.action_register_departure()
        self.assertEqual(
            self.richard_contract.sudo().contract_date_end, wizard.departure_date
        )
