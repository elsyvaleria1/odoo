from odoo.tests.common import TransactionCase, new_test_user


class TestPayrollWorkEntriesMenu(TransactionCase):
    def _work_entries_menu(self, user):
        """Return the menu entry carrying the work entries action, as the user sees it."""
        action = self.env.ref("hr_work_entry.hr_work_entry_action")
        menus = self.env["ir.ui.menu"].with_user(user).load_menus(False)
        for key, menu in menus.items():
            if key == "root":
                continue
            if (
                menu["action_model"] == "ir.actions.act_window"
                and menu["action_id"] == action.id
            ):
                return menu
        return None

    def test_payroll_officer_reaches_the_work_entries_menu(self):
        """A Payroll Officer has full ACL on hr.work.entry; give them a menu to use it.

        The menu carrying the work entries action hangs under a root restricted
        to hr.group_hr_manager, and group_hr_payroll_user only implies
        hr.group_hr_user, so the officer used to see nothing at all.
        """
        officer = new_test_user(
            self.env,
            login="payroll_officer",
            groups="hr_payroll.group_hr_payroll_user",
        )
        self.assertTrue(
            self.env["hr.work.entry"].with_user(officer).has_access("write"),
            "the officer is supposed to be able to edit work entries",
        )
        self.assertTrue(
            self._work_entries_menu(officer),
            "the Payroll Officer has no menu leading to the work entries",
        )

    def test_hr_manager_keeps_the_work_entries_menu(self):
        """Opening the section to payroll must not close it on HR managers."""
        manager = new_test_user(
            self.env,
            login="hr_manager_without_payroll",
            groups="hr.group_hr_manager",
        )
        self.assertTrue(self._work_entries_menu(manager))
