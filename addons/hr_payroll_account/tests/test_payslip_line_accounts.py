import odoo.tests
from odoo import Command

from odoo.addons.hr_payroll_account.tests.test_hr_payroll_account import (
    TestHrPayrollAccountCommon,
)


@odoo.tests.tagged("post_install", "-at_install")
class TestPayslipLineAccounts(TestHrPayrollAccountCommon):

    def setUp(self):
        super().setUp()
        self.debit_account = self.env["account.account"].create(
            {
                "name": "Payroll Debit",
                "code": "PRD001",
                "account_type": "expense",
            }
        )
        self.credit_account = self.env["account.account"].create(
            {
                "name": "Payroll Credit",
                "code": "PRC001",
                "account_type": "liability_current",
            }
        )
        self.accounted_rule = self.env["hr.salary.rule"].create(
            {
                "name": "Accounted Allowance",
                "code": "ACCTD",
                "sequence": 250,
                "struct_id": self.hr_structure_softwaredeveloper.id,
                "category_id": self.env.ref("hr_payroll.ALW").id,
                "amount_select": "fix",
                "amount_fix": 100.0,
                "account_debit": self.debit_account.id,
                "account_credit": self.credit_account.id,
            }
        )
        self.hr_payslip_john.compute_sheet()

        self.accountant = self.env["res.users"].create(
            {
                "name": "Payroll Accountant",
                "login": "payroll.accountant",
                "group_ids": [
                    Command.link(self.env.ref("hr_payroll.group_hr_payroll_user").id),
                    Command.link(self.env.ref("account.group_account_readonly").id),
                ],
            }
        )

    def _accounted_line(self, user=None):
        line = self.hr_payslip_john.line_ids.filtered(
            lambda line: line.salary_rule_id == self.accounted_rule
        )
        self.assertTrue(line, "the payslip must carry a line for the accounted rule")
        return line.with_user(user) if user else line

    def test_the_accounts_are_readable_from_the_line(self):
        line = self._accounted_line(self.accountant)
        self.assertEqual(line.salary_rule_account_debit, self.debit_account)
        self.assertEqual(line.salary_rule_account_credit, self.credit_account)

    def test_the_accounts_follow_the_payslip_company(self):
        other_company = self.env["res.company"].create({"name": "Other Payroll Co"})
        self.accounted_rule.with_company(other_company).account_debit = False

        line = self._accounted_line().with_company(other_company)

        self.assertEqual(
            line.salary_rule_account_debit,
            self.debit_account,
            "the account shown must be the one of the payslip's company",
        )
