from odoo.exceptions import AccessError
from odoo.tests import common

from odoo.addons.mail.tests.common import mail_new_test_user


class TestMenuSecurity(common.TransactionCase):

    MANAGER_ONLY_LEAVES = (
        "gamification.gamification_activity_feed_menu",
        "gamification.gamification_engagement_menu",
        "gamification.gamification_definition_menu",
        "gamification.gamification_karma_ranks_menu",
        "gamification.gamification_karma_tracking_menu",
        "gamification.gamification_streak_type_menu",
        "gamification.gamification_kudos_category_menu",
        "gamification.gamification_skill_tree_menu",
    )
    MANAGER_ONLY_PARENTS = (
        "gamification.gamification_config_parent_menu",
        "gamification.gamification_analytics_parent_menu",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = cls.env.ref("gamification.gamification_menu")
        cls.employee = mail_new_test_user(
            cls.env,
            login="gam_menu_employee",
            name="Menu Employee",
            email="gam_menu_emp@example.com",
            groups="base.group_user",
        )
        cls.manager = mail_new_test_user(
            cls.env,
            login="gam_menu_manager",
            name="Menu Manager",
            email="gam_menu_mgr@example.com",
            groups="base.group_user,gamification.group_gamification_manager",
        )

    def _loaded_menu_ids(self, user):
        menus = self.env["ir.ui.menu"].with_user(user).load_menus(False)
        return {key for key in menus if isinstance(key, int)}

    def _module_menu_ids(self):
        xmlids = self.env["ir.model.data"].search(
            [("module", "=", "gamification"), ("model", "=", "ir.ui.menu")]
        )
        return set(xmlids.mapped("res_id"))

    def test_root_menu_is_app(self):
        self.assertFalse(self.root.parent_id)
        self.assertTrue(self.root.web_icon)
        self.assertEqual(self.root.name, "Gamification")

    def test_dashboard_label_omits_the_app_name(self):
        dashboard = self.env.ref("gamification.gamification_dashboard_menu")
        self.assertEqual(dashboard.name, "Dashboard")
        self.assertEqual(
            self.env.ref("gamification.gamification_dashboard_action").name,
            "Dashboard",
        )

    def test_root_visible_for_plain_user(self):
        self.assertIn(self.root.id, self._loaded_menu_ids(self.employee))

    def test_config_and_analytics_hidden_for_user(self):
        loaded = self._loaded_menu_ids(self.employee)
        for xmlid in self.MANAGER_ONLY_PARENTS + self.MANAGER_ONLY_LEAVES:
            with self.subTest(menu=xmlid):
                self.assertNotIn(self.env.ref(xmlid).id, loaded)

    def test_employee_still_sees_the_participation_branches(self):
        loaded = self._loaded_menu_ids(self.employee)
        for xmlid in (
            "gamification.gamification_dashboard_menu",
            "gamification.gamification_activity_parent_menu",
            "gamification.gamification_recognition_parent_menu",
            "gamification.gamification_teams_parent_menu",
        ):
            with self.subTest(menu=xmlid):
                self.assertIn(self.env.ref(xmlid).id, loaded)

    def test_config_visible_and_writable_for_manager(self):
        loaded = self._loaded_menu_ids(self.manager)
        tracking_menu = self.env.ref("gamification.gamification_karma_tracking_menu")

        for xmlid in self.MANAGER_ONLY_PARENTS:
            with self.subTest(menu=xmlid):
                self.assertIn(self.env.ref(xmlid).id, loaded)

        for xmlid in self.MANAGER_ONLY_LEAVES:
            menu = self.env.ref(xmlid)
            if menu == tracking_menu:
                continue
            with self.subTest(menu=xmlid):
                self.assertIn(menu.id, loaded)
                res_model = menu.action.res_model
                records = self.env[res_model].with_user(self.manager).browse()
                self.assertTrue(records.has_access("write"))

        self.assertFalse(self.manager.has_group("base.group_system"))
        self.assertNotIn(tracking_menu.id, loaded)

    def test_portal_and_public_see_no_gamification_menus(self):
        module_menus = self._module_menu_ids()
        portal = mail_new_test_user(
            self.env,
            login="gam_menu_portal",
            name="Menu Portal",
            email="gam_menu_portal@example.com",
            groups="base.group_portal",
        )
        for user in (portal, self.env.ref("base.public_user")):
            with self.subTest(user=user.login):
                self.assertFalse(user.has_group("gamification.group_gamification_user"))
                try:
                    loaded = self._loaded_menu_ids(user)
                except AccessError:
                    continue
                self.assertFalse(loaded & module_menus)
