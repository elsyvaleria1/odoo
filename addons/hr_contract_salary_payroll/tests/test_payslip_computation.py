from datetime import date, datetime

from odoo.addons.hr_payroll.tests.common import TestPayslipContractBase


class TestPayslipComputation(TestPayslipContractBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The structure type has to be Belgian: `_get_contract_wage_field_name`
        # returns `wage_on_signature` only for a BE structure
        # (`hr_contract_salary/models/hr_version.py:230-234`), and that is
        # exactly what this test measures. But
        # `hr.payroll.structure.type._check_country` refuses a country no
        # allowed company sits in, and the base class sets up a US one - so the
        # test brings its own Belgian company instead of borrowing whatever the
        # database happens to have. Without it `setUpClass` raised and the whole
        # class was skipped on every non-Belgian deployment, this fork included.
        belgium = cls.env.ref("base.be")
        cls.company_be = cls.env["res.company"].create(
            {"name": "BE Co (payslip computation)", "country_id": belgium.id}
        )
        cls.env.user.company_ids |= cls.company_be
        cls.contract_cdi.structure_type_id.with_context(
            allowed_company_ids=cls.company_be.ids
        ).country_id = belgium
        cls.contract_cdi.wage_on_signature = 4000.33
        cls.richard_payslip = cls.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": cls.richard_emp.id,
                "version_id": cls.contract_cdi.id,
                "struct_id": cls.developer_pay_structure.id,
                "date_from": date(2016, 1, 1),
                "date_to": date(2016, 1, 31),
            }
        )

    def _reset_work_entries(self, version):
        # Unlink existing work entries and reset the generation window so they regenerate on the next generate_work_entries() call
        self.env["hr.work.entry"].search(
            [("employee_id", "=", version.employee_id.id)]
        ).unlink()
        now = datetime(2016, 1, 1, 0, 0, 0)
        version.write(
            {
                "date_generated_from": now,
                "date_generated_to": now,
            }
        )

    def test_worked_days_amount_with_unpaid(self):

        self._reset_work_entries(self.richard_payslip.version_id)
        work_entries = self.richard_emp.version_ids.generate_work_entries(
            date(2016, 1, 1), date(2016, 2, 1)
        )
        work_entries.action_validate()

        self.richard_payslip._compute_worked_days_line_ids()
        work_days = self.richard_payslip.worked_days_line_ids

        attendance_line = work_days.filtered(
            lambda l: (
                l.code == self.env.ref("hr_work_entry.work_entry_type_attendance").code
            )
        )
        self.assertAlmostEqual(
            attendance_line.amount,
            4000.33,
            delta=0.01,
            msg="His attendance must be paid 4033.33",
        )
        self.richard_payslip.version_id.wage_on_signature = 3000.33
        # A wage write refreshes the draft payslip, which replaces its worked days lines.
        attendance_line = self.richard_payslip.worked_days_line_ids.filtered(
            lambda l: (
                l.code == self.env.ref("hr_work_entry.work_entry_type_attendance").code
            )
        )
        self.assertAlmostEqual(
            attendance_line.amount,
            3000.33,
            delta=0.01,
            msg="His attendance must be paid 3033.33",
        )
