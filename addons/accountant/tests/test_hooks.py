from odoo import SUPERUSER_ID
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.accountant import _accounting_post_init, uninstall_hook


@tagged("post_install", "-at_install")
class TestAccountantHooks(AccountTestInvoicingCommon):
    """The module's install and uninstall hooks had no coverage at all, which is
    how both of the defects exercised below reached production."""

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
        """The hook restored the user group's name and nothing else, while the
        security data overwrites four fields on it and one on the readonly
        group. `account` stays installed after this module goes, so anything
        left behind keeps this module's value forever.
        """
        group_user = self.env.ref("account.group_account_user")
        group_readonly = self.env.ref("account.group_account_readonly")
        # what the data file put there
        self.assertEqual(group_user.sequence, 40)
        self.assertTrue(group_user.comment)
        self.assertTrue(group_user.privilege_id)

        uninstall_hook(self.env)

        # `account` declares the user group with a name and implied_ids only,
        # and res.groups gives these three no default, so core's values are 0/False
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
        """The hook used to carry its own list of the menus to restore, and it
        named 6 of the 7 the data file adopts. ir.ui.menu.unlink() reparents the
        children a menu still has to parent_id = False, so the one left behind
        became a root-level app once menu_accounting was deleted.
        """
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
        """Deliberate asymmetry with the test above: nothing takes over the role,
        so there is no reason to hide the journal the user was last using."""
        company = self.env.company
        journal = self._general_journal("TRC")
        company.account_config_id.account_tax_return_journal_id = journal

        company.account_config_id.account_tax_return_journal_id = False

        self.assertTrue(journal.show_on_dashboard)

    def test_post_init_pins_a_journal_assigned_before_install(self):
        """Why the post-init loop exists: the inverse only fires on write, so a
        company whose journal predates this module never triggered it.
        """
        company = self.env.company
        journal = self._general_journal("TRD")
        # Assign it behind the ORM's back, so the inverse does not run and the
        # company looks like one set up before this module was installed.
        self.env.cr.execute(
            "UPDATE account_config SET account_tax_return_journal_id = %s WHERE company_id = %s",
            (journal.id, company.id),
        )
        company.account_config_id.invalidate_recordset(
            ["account_tax_return_journal_id"]
        )
        self.assertFalse(journal.show_on_dashboard)

        # Scope the hook to a country outside its auto-install list, so it cannot
        # try to install account_reports_cash_basis in the middle of a test.
        company.country_id = self.env.ref("base.be")
        # As root, the way the real post-init hook is invoked: it walks every
        # company in the database, which a plain test user cannot write to.
        _accounting_post_init(self.env(user=SUPERUSER_ID))

        self.assertTrue(journal.show_on_dashboard)
