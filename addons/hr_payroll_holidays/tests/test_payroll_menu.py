from odoo.tests.common import TransactionCase, new_test_user


class TestPayrollHolidaysWorkEntriesMenu(TransactionCase):
    def _work_entries_menu(self, user):
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

    def test_work_entries_action_stays_on_a_leaf_menu(self):
        manager = new_test_user(
            self.env,
            login="hr_and_holidays_manager",
            groups="hr.group_hr_manager,hr_holidays.group_hr_holidays_user",
        )
        menu = self._work_entries_menu(manager)
        self.assertTrue(menu)
        self.assertFalse(
            menu["children"],
            "the work entries action sits on a menu that the navbar renders as a dropdown",
        )
