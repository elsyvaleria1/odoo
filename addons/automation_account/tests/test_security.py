from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests.common import tagged

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestSecurity(AutomationAccountCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.group_employee = cls.env.ref("base.group_user")
        cls.group_accountant = cls.env.ref("account.group_account_basic")

        cls.employee = cls.env["res.users"].create(
            {
                "name": "Automation plain employee",
                "login": "automation_plain_employee",
                "group_ids": [Command.set(cls.group_employee.ids)],
            },
        )
        cls.accountant = cls.env["res.users"].create(
            {
                "name": "Automation accountant",
                "login": "automation_accountant",
                "group_ids": [
                    Command.set((cls.group_employee | cls.group_accountant).ids),
                ],
            },
        )

    def test_a_plain_employee_cannot_create_the_wizard(self):
        with self.assertRaises(AccessError):
            self.env["wizard.account.bank.statement.line.start.automation"].with_user(
                self.employee
            ).create(
                {
                    "automation_id": self.automation.id,
                    "partner_id": self.partner.id,
                    "amount": 10.0,
                    "date": "2026-08-27",
                    "currency_id": self.company.currency_id.id,
                    "company_ids": [Command.set(self.company.ids)],
                },
            )

    def test_an_accountant_can_open_the_wizard(self):
        wizard = (
            self.env["wizard.account.bank.statement.line.start.automation"]
            .with_user(self.accountant)
            .create(
                {
                    "automation_id": self.automation.id,
                    "partner_id": self.partner.id,
                    "amount": 10.0,
                    "date": "2026-08-27",
                    "currency_id": self.company.currency_id.id,
                    "company_ids": [Command.set(self.company.ids)],
                },
            )
        )

        self.assertEqual(wizard.partner_id, self.partner)
        self.assertEqual(wizard.automation_id, self.automation)

    def test_completing_the_run_still_needs_create_on_the_runtime(self):
        self._make_step("pass")
        wizard = (
            self.env["wizard.account.bank.statement.line.start.automation"]
            .with_user(self.accountant)
            .create(
                {
                    "automation_id": self.automation.id,
                    "partner_id": self.partner.id,
                    "amount": 10.0,
                    "date": "2026-08-27",
                    "currency_id": self.company.currency_id.id,
                    "company_ids": [Command.set(self.company.ids)],
                },
            )
        )

        with self.assertRaises(AccessError):
            wizard.action_create_runtime()

    def test_the_wizard_grants_no_unlink(self):
        access = self.env.ref("automation_account.access_automation_runtime_create")

        self.assertEqual(access.group_id, self.group_accountant)
        self.assertFalse(access.for_unlink)

    def test_the_menu_is_gated_on_the_accounting_group(self):
        menu = self.env.ref("automation_account.menu_automation_runtime_accounting")

        self.assertIn(self.group_accountant, menu.group_ids)

    def test_the_action_defaults_to_the_bank_statement_filter(self):
        action = self.env.ref(
            "automation_account.action_automation_runtime_accounting",
        )

        self.assertIn("search_default_filter_with_bank_statement", action.context)
