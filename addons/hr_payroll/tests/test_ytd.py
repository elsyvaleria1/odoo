from datetime import date

from dateutil.relativedelta import relativedelta

from odoo.exceptions import ValidationError

from odoo.addons.hr_payroll.tests.common import TestPayslipContractBase


class TestYTD(TestPayslipContractBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_2 = cls.env["res.company"].create({"name": "Odooo"})
        cls.shrek_emp = cls.env["hr.employee"].create(
            {
                "name": "Shrek",
                "company_id": cls.company_2.id,
                "date_version": date(2000, 4, 22),
                "contract_date_start": date(2000, 4, 22),
                "wage": 5000.33,
                "structure_type_id": cls.structure_type.id,
            }
        )
        cls.shrek_contract = cls.shrek_emp.version_id

        cls.company_3 = cls.env["res.company"].create({"name": "Odooooooo"})
        cls.donkey_emp = cls.env["hr.employee"].create(
            {
                "name": "Donkey",
                "company_id": cls.company_3.id,
                "date_version": date(2000, 4, 22),
                "contract_date_start": date(2000, 4, 22),
                "wage": 5000.33,
                "structure_type_id": cls.structure_type.id,
            }
        )
        cls.donkey_contract = cls.donkey_emp.version_id

    def _generate_payslip(
        self,
        date_from,
        struct,
        line_value,
        no_confirm=False,
        no_compute=False,
        employee=None,
        contract=None,
    ):
        date_to = date_from + relativedelta(months=1, days=-1)

        test_payslip = self.env["hr.payslip"].create(
            {
                "name": "Payslip for YTD tests - " + str(date_from),
                "employee_id": employee.id if employee else self.richard_emp.id,
                "version_id": contract.id if contract else self.contract_cdi.id,
                "company_id": employee.company_id.id
                if employee
                else self.richard_emp.company_id.id,
                "struct_id": struct.id,
                "date_from": date_from,
                "date_to": date_to,
                "edited": True,
            }
        )

        test_rule = self.env["hr.salary.rule"].search(
            [
                ("code", "=", "TEST-YTD"),
                ("struct_id", "=", struct.id),
            ]
        )

        if not test_rule:
            test_rule = self.env["hr.salary.rule"].create(
                {
                    "name": "Rule for YTD test",
                    "amount_select": "code",
                    "amount_python_compute": "result = payslip.line_ids.filtered(lambda l: l.code == 'TEST-YTD')['total']",
                    "code": "TEST-YTD",
                    "category_id": self.env.ref("hr_payroll.ALW").id,
                    "struct_id": struct.id,
                }
            )
        test_payslip.line_ids += self.env["hr.payslip.line"].create(
            {
                "code": "TEST-YTD",
                "name": test_rule.name,
                "salary_rule_id": test_rule.id,
                "total": line_value,
                "slip_id": test_payslip.id,
            }
        )

        test_worked_days = test_payslip.worked_days_line_ids.filtered(
            lambda l: l.code == "WORK100"
        )
        self.assertEqual(len(test_worked_days), 1)
        test_worked_days.amount = line_value

        if not no_compute:
            test_payslip.compute_sheet()
            if not no_confirm:
                test_payslip.action_payslip_done()

        return test_payslip

    def _assert_ytd_values(self, payslip, line_goal_value):
        test_line = payslip.line_ids.filtered(lambda l: l.code == "BASIC")
        self.assertAlmostEqual(
            test_line.ytd,
            line_goal_value,
            delta=0.01,
            msg="The YTD of the slip line should be "
            + str(line_goal_value)
            + "$ but is currently "
            + str(test_line.ytd)
            + "$",
        )

        test_worked_days = payslip.worked_days_line_ids.filtered(
            lambda l: l.code == "WORK100"
        )
        self.assertAlmostEqual(
            test_worked_days.ytd,
            line_goal_value,
            delta=0.01,
            msg="The YTD of the worked days line should be "
            + str(line_goal_value)
            + "$ but is currently "
            + str(test_worked_days.ytd)
            + "$",
        )

    def test_ytd_00_classic_flow(self):
        ytd_test_structure_00 = self.env["hr.payroll.structure"].create(
            {
                "name": "Salary Structure for YTD test 00",
                "type_id": self.structure_type.id,
                "ytd_computation": True,
            }
        )

        payslip_year_2023_A = self._generate_payslip(
            date(2023, 11, 1), ytd_test_structure_00, 1001
        )
        self._assert_ytd_values(payslip_year_2023_A, 1001)
        payslip_year_2023_B = self._generate_payslip(
            date(2023, 2, 1), ytd_test_structure_00, 1002
        )
        self._assert_ytd_values(payslip_year_2023_B, 1002)
        payslip_year_2025 = self._generate_payslip(
            date(2025, 2, 1), ytd_test_structure_00, 1004
        )
        self._assert_ytd_values(payslip_year_2025, 1004)

        payslip_january_A = self._generate_payslip(
            date(2024, 1, 1), ytd_test_structure_00, 1010
        )
        self._assert_ytd_values(payslip_january_A, 1010)
        payslip_march_A = self._generate_payslip(
            date(2024, 3, 1), ytd_test_structure_00, 1020
        )
        self._assert_ytd_values(payslip_march_A, 1010 + 1020)
        payslip_may = self._generate_payslip(
            date(2024, 5, 1), ytd_test_structure_00, 1040
        )
        self._assert_ytd_values(payslip_may, 1010 + 1020 + 1040)

        payslip_february_A = self._generate_payslip(
            date(2024, 2, 1), ytd_test_structure_00, 1080
        )
        self._assert_ytd_values(payslip_february_A, 1010 + 1080)
        payslip_february_B = self._generate_payslip(
            date(2024, 2, 15), ytd_test_structure_00, 1160
        )
        self._assert_ytd_values(payslip_february_B, 1010 + 1080 + 1160)
        payslip_march_B = self._generate_payslip(
            date(2024, 3, 2), ytd_test_structure_00, 1320
        )
        self._assert_ytd_values(payslip_march_B, 1010 + 1020 + 1320)

        payslip_january_B = self._generate_payslip(
            date(2024, 1, 1), ytd_test_structure_00, 1640
        )
        self._assert_ytd_values(payslip_january_B, 1010 + 1640)

    def test_ytd_01_matching_payslips(self):
        ytd_test_structure_01 = self.env["hr.payroll.structure"].create(
            {
                "name": "Salary Structure for YTD test 01",
                "type_id": self.structure_type.id,
                "ytd_computation": True,
            }
        )

        payslip_classic_A = self._generate_payslip(
            date(2024, 1, 1), ytd_test_structure_01, 1010
        )
        self._assert_ytd_values(payslip_classic_A, 1010)

        payslip_draft = self._generate_payslip(
            date(2024, 2, 1), ytd_test_structure_01, 1001, no_confirm=True
        )
        self._assert_ytd_values(payslip_draft, 1010 + 1001)

        payslip_another_employee = self._generate_payslip(
            date(2024, 3, 1), ytd_test_structure_01, 1002, employee=self.jules_emp
        )
        self._assert_ytd_values(payslip_another_employee, 1002)

        ytd_test_structure_01_bis = self.env["hr.payroll.structure"].create(
            {
                "name": "Salary Structure for YTD test 01 bis",
                "type_id": self.structure_type.id,
                "ytd_computation": True,
            }
        )

        payslip_another_structure = self._generate_payslip(
            date(2024, 4, 1), ytd_test_structure_01_bis, 1004
        )
        self._assert_ytd_values(payslip_another_structure, 1004)

        payslip_classic_B = self._generate_payslip(
            date(2024, 5, 1), ytd_test_structure_01, 1020
        )
        self._assert_ytd_values(payslip_classic_B, 1010 + 1020)

    def test_ytd_02_reset_date(self):
        ytd_test_structure_02 = self.env["hr.payroll.structure"].create(
            {
                "name": "Salary Structure for YTD test 02",
                "type_id": self.structure_type.id,
                "ytd_computation": True,
            }
        )

        self.assertEqual(self.richard_emp.company_id.ytd_reset_day, 1)
        self.assertEqual(self.richard_emp.company_id.ytd_reset_month, "1")

        reset_date = date(2024, 1, 1)
        self.richard_emp.company_id.ytd_reset_day = reset_date.day
        self.richard_emp.company_id.ytd_reset_month = str(reset_date.month)

        payslip_before_reset = self._generate_payslip(
            reset_date + relativedelta(months=-1, days=0), ytd_test_structure_02, 1001
        )
        self._assert_ytd_values(payslip_before_reset, 1001)

        payslip_on_reset = self._generate_payslip(
            reset_date + relativedelta(months=-1, days=1), ytd_test_structure_02, 1010
        )
        self._assert_ytd_values(payslip_on_reset, 1010)

        payslip_after_reset = self._generate_payslip(
            reset_date + relativedelta(months=-1, days=2), ytd_test_structure_02, 1020
        )
        self._assert_ytd_values(payslip_after_reset, 1010 + 1020)

        self.richard_emp.company_id.ytd_reset_day = 1
        with self.assertRaises(ValidationError):
            self.richard_emp.company_id.ytd_reset_day = -20
        with self.assertRaises(ValidationError):
            self.richard_emp.company_id.ytd_reset_day = 0

        self.richard_emp.company_id.ytd_reset_month = "1"
        self.richard_emp.company_id.ytd_reset_day = 31
        with self.assertRaises(ValidationError):
            self.richard_emp.company_id.ytd_reset_day = 32

        with self.assertRaises(ValidationError):
            self.richard_emp.company_id.ytd_reset_month = "4"
        self.richard_emp.company_id.ytd_reset_day = 30
        self.richard_emp.company_id.ytd_reset_month = "4"
        with self.assertRaises(ValidationError):
            self.richard_emp.company_id.ytd_reset_day = 31

        self.richard_emp.company_id.ytd_reset_day = 28
        self.richard_emp.company_id.ytd_reset_month = "2"
        with self.assertRaises(ValidationError):
            self.richard_emp.company_id.ytd_reset_day = 29

        self.assertEqual(
            self.richard_emp.company_id.get_last_ytd_reset_date(date(2020, 6, 1)),
            date(2020, 2, 28),
        )

    def test_ytd_03_edit_payslip_lines_wizard(self):
        ytd_test_structure_03 = self.env["hr.payroll.structure"].create(
            {
                "name": "Salary Structure for YTD test 03",
                "type_id": self.structure_type.id,
                "ytd_computation": True,
            }
        )

        payslip_classic_A = self._generate_payslip(
            date(2024, 1, 1), ytd_test_structure_03, 1001
        )
        self._assert_ytd_values(payslip_classic_A, 1001)

        payslip_to_edit = self._generate_payslip(
            date(2024, 6, 1), ytd_test_structure_03, 1002, no_confirm=True
        )
        self._assert_ytd_values(payslip_to_edit, 1001 + 1002)

        manager = self.env.ref("hr_payroll.group_hr_payroll_manager")
        self.env.user.group_ids |= manager
        action = payslip_to_edit.action_edit_payslip_lines()
        self.env.user.group_ids -= manager
        wizard = self.env[action["res_model"]].browse(action["res_id"])

        test_slip_lines = wizard.line_ids.filtered(lambda l: l.code == "BASIC")
        self.assertEqual(len(test_slip_lines), 1)
        test_slip_lines.ytd = 6010

        test_worked_days = wizard.worked_days_line_ids.filtered(
            lambda l: l.code == "WORK100"
        )
        self.assertEqual(len(test_worked_days), 1)
        test_worked_days.ytd = 6010

        wizard.action_validate_edition()
        payslip_to_edit.action_payslip_done()
        self._assert_ytd_values(payslip_to_edit, 6010)

        payslip_classic_B = self._generate_payslip(
            date(2024, 7, 1), ytd_test_structure_03, 1020
        )
        self._assert_ytd_values(payslip_classic_B, 6010 + 1020)
        payslip_classic_C = self._generate_payslip(
            date(2024, 8, 1), ytd_test_structure_03, 1040
        )
        self._assert_ytd_values(payslip_classic_C, 6010 + 1020 + 1040)

    def test_ytd_04_compute_many_payslips_together(self):
        ytd_test_structure_04 = self.env["hr.payroll.structure"].create(
            {
                "name": "Salary Structure for YTD test 04",
                "type_id": self.structure_type.id,
                "ytd_computation": True,
            }
        )

        payslip_lot0_classic = self._generate_payslip(
            date(2024, 1, 1), ytd_test_structure_04, 1
        )
        self._assert_ytd_values(payslip_lot0_classic, 1)
        payslip_lot0_company_2 = self._generate_payslip(
            date(2024, 1, 1),
            ytd_test_structure_04,
            2,
            employee=self.shrek_emp,
            contract=self.shrek_contract,
        )
        self._assert_ytd_values(payslip_lot0_company_2, 2)
        self.company_3.ytd_reset_month = "4"
        payslip_lot0_company_3 = self._generate_payslip(
            date(2024, 1, 1),
            ytd_test_structure_04,
            4,
            employee=self.donkey_emp,
            contract=self.donkey_contract,
        )
        self._assert_ytd_values(payslip_lot0_company_3, 4)

        payslip_lot1_classic_A = self._generate_payslip(
            date(2024, 2, 1), ytd_test_structure_04, 8, no_compute=True
        )
        payslip_lot1_another_employee = self._generate_payslip(
            date(2024, 3, 1),
            ytd_test_structure_04,
            16,
            no_compute=True,
            employee=self.jules_emp,
        )
        ytd_test_structure_04_bis = self.env["hr.payroll.structure"].create(
            {
                "name": "Salary Structure for YTD test 04 bis",
                "type_id": self.structure_type.id,
                "ytd_computation": True,
            }
        )
        payslip_lot1_another_structure = self._generate_payslip(
            date(2024, 4, 1), ytd_test_structure_04_bis, 32, no_compute=True
        )
        payslip_lot1_another_year = self._generate_payslip(
            date(2025, 3, 1), ytd_test_structure_04, 64, no_compute=True
        )
        payslip_lot1_company_2_A = self._generate_payslip(
            date(2024, 2, 1),
            ytd_test_structure_04,
            128,
            no_compute=True,
            employee=self.shrek_emp,
            contract=self.shrek_contract,
        )
        payslip_lot1_company_2_B = self._generate_payslip(
            date(2024, 6, 1),
            ytd_test_structure_04,
            256,
            no_compute=True,
            employee=self.shrek_emp,
            contract=self.shrek_contract,
        )
        payslip_lot1_company_3_A = self._generate_payslip(
            date(2024, 2, 1),
            ytd_test_structure_04,
            512,
            no_compute=True,
            employee=self.donkey_emp,
            contract=self.donkey_contract,
        )
        payslip_lot1_company_3_B = self._generate_payslip(
            date(2024, 6, 1),
            ytd_test_structure_04,
            1024,
            no_compute=True,
            employee=self.donkey_emp,
            contract=self.donkey_contract,
        )
        payslip_lot1_classic_B = self._generate_payslip(
            date(2024, 5, 1), ytd_test_structure_04, 2048, no_compute=True
        )
        payslip_lot1_classic_C = self._generate_payslip(
            date(2024, 6, 1), ytd_test_structure_04, 4096, no_compute=True
        )

        payslip_lot_1 = (
            payslip_lot1_classic_A
            + payslip_lot1_another_employee
            + payslip_lot1_another_structure
            + payslip_lot1_another_year
            + payslip_lot1_company_2_A
            + payslip_lot1_company_2_B
            + payslip_lot1_company_3_A
            + payslip_lot1_company_3_B
            + payslip_lot1_classic_B
            + payslip_lot1_classic_C
        )

        payslip_lot_1.compute_sheet()
        payslip_lot_1.action_payslip_done()

        self.assertEqual(payslip_lot1_company_2_A.company_id, self.company_2)

        self._assert_ytd_values(payslip_lot1_classic_A, 1 + 8)
        self._assert_ytd_values(payslip_lot1_another_employee, 16)
        self._assert_ytd_values(payslip_lot1_another_structure, 32)
        self._assert_ytd_values(payslip_lot1_another_year, 64)
        self._assert_ytd_values(payslip_lot1_company_2_A, 2 + 128)
        self._assert_ytd_values(payslip_lot1_company_2_B, 2 + 256)
        self._assert_ytd_values(payslip_lot1_company_3_A, 4 + 512)
        self._assert_ytd_values(payslip_lot1_company_3_B, 1024)
        self._assert_ytd_values(payslip_lot1_classic_B, 1 + 2048)
        self._assert_ytd_values(payslip_lot1_classic_C, 1 + 4096)

        payslip_lot2_classic = self._generate_payslip(
            date(2024, 7, 1), ytd_test_structure_04, 8192, no_compute=True
        )
        payslip_lot2_another_employee = self._generate_payslip(
            date(2024, 8, 1),
            ytd_test_structure_04,
            16384,
            no_compute=True,
            employee=self.jules_emp,
        )
        payslip_lot2_another_structure = self._generate_payslip(
            date(2024, 9, 1), ytd_test_structure_04_bis, 32768, no_compute=True
        )
        payslip_lot2_another_year = self._generate_payslip(
            date(2025, 10, 1), ytd_test_structure_04, 65536, no_compute=True
        )
        payslip_lot2_company_2 = self._generate_payslip(
            date(2024, 11, 1),
            ytd_test_structure_04,
            131072,
            no_compute=True,
            employee=self.shrek_emp,
            contract=self.shrek_contract,
        )

        payslip_lot_2 = (
            payslip_lot2_classic
            + payslip_lot2_another_employee
            + payslip_lot2_another_structure
            + payslip_lot2_another_year
            + payslip_lot2_company_2
        )

        payslip_lot_2.compute_sheet()
        payslip_lot_2.action_payslip_done()

        self._assert_ytd_values(payslip_lot2_classic, 1 + 4096 + 8192)
        self._assert_ytd_values(payslip_lot2_another_employee, 16 + 16384)
        self._assert_ytd_values(payslip_lot2_another_structure, 32 + 32768)
        self._assert_ytd_values(payslip_lot2_another_year, 64 + 65536)
        self._assert_ytd_values(payslip_lot2_company_2, 2 + 256 + 131072)

    def test_ytd_05_reset_date_with_many_payslips_together(self):
        ytd_test_structure_05 = self.env["hr.payroll.structure"].create(
            {
                "name": "Salary Structure for YTD test 05",
                "type_id": self.structure_type.id,
                "ytd_computation": True,
            }
        )

        self.richard_emp.company_id.ytd_reset_month = "5"
        self.company_2.ytd_reset_month = "3"
        self.company_3.ytd_reset_month = "7"

        payslip_company_2_preliminary = self._generate_payslip(
            date(2024, 4, 1),
            ytd_test_structure_05,
            1010,
            employee=self.shrek_emp,
            contract=self.shrek_contract,
        )
        self._assert_ytd_values(payslip_company_2_preliminary, 1010)

        payslip__company_1_lot = self._generate_payslip(
            date(2024, 10, 1),
            ytd_test_structure_05,
            1001,
            no_compute=True,
            employee=self.richard_emp,
            contract=self.contract_cdi,
        )
        payslip__company_2_lot = self._generate_payslip(
            date(2024, 12, 1),
            ytd_test_structure_05,
            1020,
            no_compute=True,
            employee=self.shrek_emp,
            contract=self.shrek_contract,
        )
        payslip__company_3_lot = self._generate_payslip(
            date(2024, 10, 1),
            ytd_test_structure_05,
            1002,
            no_compute=True,
            employee=self.donkey_emp,
            contract=self.donkey_contract,
        )

        payslip_lot = (
            payslip__company_1_lot + payslip__company_2_lot + payslip__company_3_lot
        )

        payslip_lot.compute_sheet()
        payslip_lot.action_payslip_done()

        self._assert_ytd_values(payslip__company_2_lot, 1010 + 1020)
