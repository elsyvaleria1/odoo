import odoo.tests

from odoo.addons.hr_payroll_account.tests.test_hr_payroll_account import (
    TestHrPayrollAccountCommon,
)


@odoo.tests.tagged("post_install", "-at_install")
class TestAnalyticMoveLineMerge(TestHrPayrollAccountCommon):
    def setUp(self):
        super().setUp()
        self.merge_debit_account = self.env["account.account"].create(
            {
                "name": "Merge Debit",
                "code": "MRGD01",
                "account_type": "expense",
            }
        )
        self.merge_credit_account = self.env["account.account"].create(
            {
                "name": "Merge Credit",
                "code": "MRGC01",
                "account_type": "liability_current",
            }
        )
        plan = self.env["account.analytic.plan"].create({"name": "Payroll Merge Plan"})
        self.analytic_account = self.env["account.analytic.account"].create(
            {"name": "Payroll Merge Account", "plan_id": plan.id}
        )
        self.distribution = {str(self.analytic_account.id): 100.0}

        self.rule_values = {
            "name": "Mergeable Allowance",
            "struct_id": self.hr_structure_softwaredeveloper.id,
            "category_id": self.env.ref("hr_payroll.ALW").id,
            "amount_select": "fix",
            "account_debit": self.merge_debit_account.id,
            "account_credit": self.merge_credit_account.id,
        }

    def _create_rules(self, analytic_distribution=False):
        for code, amount in (("MRG1", 100.0), ("MRG2", 50.0)):
            self.env["hr.salary.rule"].create(
                {
                    **self.rule_values,
                    "code": code,
                    "sequence": 250,
                    "amount_fix": amount,
                    "analytic_distribution": analytic_distribution,
                }
            )

    def _post_and_get_merge_lines(self):
        payslip = self.hr_payslip_john
        payslip.compute_sheet()
        payslip.action_payslip_done()
        self.assertTrue(payslip.move_id, "the payslip must have produced an entry")
        return payslip.move_id.line_ids.filtered(
            lambda line: line.account_id == self.merge_debit_account
        )

    def test_two_lines_of_one_name_merge_without_analytic(self):
        self._create_rules()

        lines = self._post_and_get_merge_lines()

        self.assertEqual(len(lines), 1, "the two lines must share one journal item")
        self.assertAlmostEqual(lines.debit, 150.0, places=2)

    def test_two_lines_of_one_name_merge_with_the_same_analytic(self):
        self._create_rules(analytic_distribution=self.distribution)

        lines = self._post_and_get_merge_lines()

        self.assertEqual(
            len(lines),
            1,
            "an analytic distribution must not switch merging off",
        )
        self.assertAlmostEqual(lines.debit, 150.0, places=2)
        self.assertEqual(lines.analytic_distribution, self.distribution)

    def test_lines_with_different_analytic_do_not_merge(self):
        other_account = self.env["account.analytic.account"].create(
            {
                "name": "Other Payroll Account",
                "plan_id": self.analytic_account.plan_id.id,
            }
        )
        self.env["hr.salary.rule"].create(
            {
                **self.rule_values,
                "code": "MRG1",
                "sequence": 250,
                "amount_fix": 100.0,
                "analytic_distribution": self.distribution,
            }
        )
        self.env["hr.salary.rule"].create(
            {
                **self.rule_values,
                "code": "MRG2",
                "sequence": 251,
                "amount_fix": 50.0,
                "analytic_distribution": {str(other_account.id): 100.0},
            }
        )

        lines = self._post_and_get_merge_lines()

        self.assertEqual(
            len(lines),
            2,
            "lines carrying different distributions must stay apart",
        )
