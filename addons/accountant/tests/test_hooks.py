from odoo import SUPERUSER_ID
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.accountant import _accounting_post_init, uninstall_hook


@tagged("post_install", "-at_install")
class TestAccountantHooks(AccountTestInvoicingCommon):
    def _general_journal(self, code):
        return self.env["account.journal"].create(
            {
                "name": f"Tax returns {code}",
                "code": code,
                "type": "general",
                "show_on_dashboard": False,
            }
        )

    def test_uninstall_hook_restores_every_overwritten_group_field(self):
        group_user = self.env.ref("account.group_account_user")
        group_readonly = self.env.ref("account.group_account_readonly")
        self.assertEqual(group_user.sequence, 40)
        self.assertTrue(group_user.comment)
        self.assertTrue(group_user.privilege_id)

        uninstall_hook(self.env)

        self.assertEqual(group_user.name, "Show Full Accounting Features")
        self.assertEqual(group_user.sequence, 0)
        self.assertFalse(group_user.comment)
        self.assertFalse(group_user.privilege_id)
        self.assertEqual(
            group_readonly.comment,
            "Access to all Accounting data, journal entries, configuration and"
            " reports included, but in read-only mode, no actions allowed.",
        )

    def test_uninstall_hook_hands_back_every_adopted_menu(self):
        accounting_menu = self.env.ref("accountant.menu_accounting")
        invoicing_menu = self.env.ref("account.menu_finance")
        Menu = self.env["ir.ui.menu"].with_context(active_test=False)
        adopted = Menu.search([("parent_id", "=", accounting_menu.id)])
        self.assertTrue(adopted, "the data file should have adopted some menus")

        uninstall_hook(self.env)

        self.assertFalse(
            Menu.search([("parent_id", "=", accounting_menu.id)]),
            "nothing may be left under menu_accounting: uninstall deletes it,"
            " and its remaining children would be promoted to root menus",
        )
        self.assertEqual(
            adopted.parent_id,
            invoicing_menu,
            "every adopted menu belongs back under account.menu_finance",
        )

    def test_replacing_the_tax_return_journal_unpins_the_old_one(self):
        company = self.env.company
        first, second = self._general_journal("TRA"), self._general_journal("TRB")

        company.account_config_id.account_tax_return_journal_id = first
        self.assertTrue(
            first.show_on_dashboard, "the tax return journal is shown on the dashboard"
        )

        company.account_config_id.account_tax_return_journal_id = second
        self.assertFalse(
            first.show_on_dashboard,
            "a journal that stops being the tax return journal stops being pinned",
        )
        self.assertTrue(second.show_on_dashboard)

    def test_clearing_the_tax_return_journal_keeps_it_pinned(self):
        company = self.env.company
        journal = self._general_journal("TRC")
        company.account_config_id.account_tax_return_journal_id = journal

        company.account_config_id.account_tax_return_journal_id = False

        self.assertTrue(journal.show_on_dashboard)

    def test_post_init_pins_a_journal_assigned_before_install(self):
        company = self.env.company
        journal = self._general_journal("TRD")
        self.env.cr.execute(
            "UPDATE account_config SET account_tax_return_journal_id = %s WHERE company_id = %s",
            (journal.id, company.id),
        )
        company.account_config_id.invalidate_recordset(
            ["account_tax_return_journal_id"]
        )
        self.assertFalse(journal.show_on_dashboard)

        company.country_id = self.env.ref("base.be")
        _accounting_post_init(self.env(user=SUPERUSER_ID))

        self.assertTrue(journal.show_on_dashboard)
