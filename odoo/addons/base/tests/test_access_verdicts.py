from datetime import timedelta
from unittest.mock import patch

from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestModelVerdicts(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Grant = cls.env["res.users.grant"]
        cls.company_b = cls.env["res.company"].create({"name": "Verdicts B"})
        cls.reader = cls.env["res.groups"].create({"name": "Verdicts: reader"})
        cls.privilege = cls.env["res.groups"].create(
            {"name": "Verdicts: privilege", "is_privilege": True}
        )
        cls.env["ir.model.data"].create(
            [
                {
                    "module": "base",
                    "name": name,
                    "model": "res.groups",
                    "res_id": group.id,
                }
                for name, group in (
                    ("verdicts_reader", cls.reader),
                    ("verdicts_privilege", cls.privilege),
                )
            ]
        )
        cls.break_glass = cls.env.ref("base.group_break_glass")
        model_id = cls.env["ir.model"]._get_id("ir.config_parameter")
        cls.rows = cls.env["ir.access"].create(
            [
                {
                    "name": f"Verdicts: {group.name} reads the parameters",
                    "model_id": model_id,
                    "group_id": group.id,
                    "kind": "permission",
                    "operation": "r",
                }
                for group in (cls.reader, cls.privilege, cls.break_glass)
            ]
        )
        cls.user = new_test_user(cls.env, login="verdicts", groups="base.group_user")
        cls.user.company_ids = [Command.link(cls.company_b.id)]

    def principal(self, **context):
        return self.env(user=self.user, context=context)

    def reads(self, env):
        return env["ir.config_parameter"].has_access("read")

    def assertVerdict(self, env, expected):
        self.assertEqual(self.reads(env), expected)
        with self.assertQueryCount(0):
            self.assertEqual(self.reads(env), expected)

    def at(self, moment):
        return patch.object(type(self.env.cr), "now", lambda cr: moment)

    def test_a_grant_and_its_revocation(self):
        env = self.principal()
        self.assertVerdict(env, False)
        grant = self.Grant.create({"user_id": self.user.id, "group_id": self.reader.id})
        self.assertVerdict(env, True)
        grant.action_revoke()
        self.assertVerdict(env, False)

    def test_a_membership_written_from_either_side(self):
        env = self.principal()
        self.assertVerdict(env, False)
        self.user.group_ids = [Command.link(self.reader.id)]
        self.assertVerdict(env, True)
        self.reader.user_ids = [Command.unlink(self.user.id)]
        self.assertVerdict(env, False)
        self.reader.user_ids = [Command.link(self.user.id)]
        self.assertVerdict(env, True)

    def test_a_privilege_holds_in_its_environment_only(self):
        env = self.principal()
        self.assertVerdict(env, False)
        privileged = env["ir.config_parameter"].with_privilege(
            "base.verdicts_privilege", reason="probe"
        )
        self.assertVerdict(privileged.env, True)
        self.assertVerdict(env, False)

    def test_a_superuser_needs_no_privilege_its_module_has_not_loaded(self):
        partners = self.env["res.partner"].sudo()
        with patch.object(self.registry, "ready", False):
            self.assertEqual(
                partners.with_privilege("module_not_loaded.privilege"), partners
            )
            kept = partners.with_privilege(
                "module_not_loaded.privilege", "base.privilege_check_duties"
            )
            self.assertEqual(
                kept.env.privileges,
                frozenset({self.env.ref("base.privilege_check_duties").id}),
            )
            with self.assertRaisesRegex(ValueError, "names no privilege"):
                self.principal()["res.partner"].with_privilege(
                    "module_not_loaded.privilege"
                )
        with self.assertRaisesRegex(ValueError, "names no privilege"):
            partners.with_privilege("module_not_loaded.privilege")

    def test_a_misspelled_privilege_of_a_loaded_module_raises_while_modules_load(self):
        partners = self.env["res.partner"].sudo()
        with patch.object(self.registry, "ready", False):
            with self.assertRaisesRegex(ValueError, "names no privilege"):
                partners.with_privilege("base.privilege_misspelled")
            with self.assertRaisesRegex(ValueError, "names no privilege"):
                partners.with_privilege(
                    "module_not_loaded.privilege", "base.privilege_misspelled"
                )

    def test_a_scoped_grant_follows_the_companies_in_use(self):
        in_a = self.principal(allowed_company_ids=[self.env.company.id])
        in_b = self.principal(allowed_company_ids=[self.company_b.id])
        grant = self.Grant.create(
            {
                "user_id": self.user.id,
                "group_id": self.reader.id,
                "company_ids": [Command.set(self.company_b.ids)],
            }
        )
        self.assertVerdict(in_a, False)
        self.assertVerdict(in_b, True)
        grant.company_ids = [Command.set(self.env.company.ids)]
        self.assertVerdict(in_a, True)
        self.assertVerdict(in_b, False)

    def test_a_timed_grant_counts_at_the_second(self):
        env = self.principal()
        now = self.env.cr.now()
        self.Grant.create(
            {
                "user_id": self.user.id,
                "group_id": self.reader.id,
                "date_to": now + timedelta(hours=1),
            }
        )
        self.assertVerdict(env, True)
        with self.at(now + timedelta(hours=2)):
            self.assertEqual(self.reads(env), False)

    def test_a_scheduled_grant_counts_at_the_second(self):
        env = self.principal()
        now = self.env.cr.now()
        self.Grant.create(
            {
                "user_id": self.user.id,
                "group_id": self.reader.id,
                "date_from": now + timedelta(hours=1),
            }
        )
        self.assertVerdict(env, False)
        with self.at(now + timedelta(hours=2)):
            self.assertEqual(self.reads(env), True)

    def test_an_eligibility_activated_and_stopped(self):
        env = self.principal()
        eligibility = self.env["res.users.eligibility"].create(
            {"user_id": self.user.id, "group_id": self.reader.id, "max_hours": 2}
        )
        self.assertVerdict(env, False)
        eligibility.with_user(self.user).action_activate(1, "read a parameter")
        self.assertVerdict(env, True)
        eligibility.with_user(self.user).action_stop()
        self.assertVerdict(env, False)

    def test_break_glass_opened_and_closed(self):
        env = self.principal()
        eligibility = self.env["res.users.eligibility"].create(
            {"user_id": self.user.id, "group_id": self.break_glass.id, "max_hours": 2}
        )
        self.assertVerdict(env, False)
        eligibility.with_user(self.user).action_activate(1, "incident")
        self.assertVerdict(env, True)
        eligibility.action_revoke("incident closed")
        self.assertVerdict(env, False)

    def test_a_hierarchy_change(self):
        env = self.principal()
        holder = self.env["res.groups"].create({"name": "Verdicts: holder"})
        self.user.group_ids = [Command.link(holder.id)]
        self.assertVerdict(env, False)
        holder.implied_ids = [Command.link(self.reader.id)]
        self.assertVerdict(env, True)

    def test_an_access_row_change(self):
        env = self.principal()
        self.user.group_ids = [Command.link(self.reader.id)]
        self.assertVerdict(env, True)
        self.rows[0].operation = "u"
        self.assertVerdict(env, False)
        self.rows[0].operation = "r"
        self.assertVerdict(env, True)


@tagged("post_install", "-at_install")
class TestMembershipKeepsCaches(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env["res.groups"].create({"name": "Membership probe"})
        cls.env["ir.model.data"].create(
            {
                "module": "base",
                "name": "membership_probe",
                "model": "res.groups",
                "res_id": cls.group.id,
            }
        )
        cls.user = new_test_user(cls.env, login="membership", groups="base.group_user")

    def add(self):
        self.user.group_ids = [Command.link(self.group.id)]

    def remove(self):
        self.user.group_ids = [Command.unlink(self.group.id)]

    def assertStayWarm(self, change):
        env = self.env(user=self.user)

        def read():
            return (
                env["ir.default"]._get_model_defaults("res.partner"),
                env["ir.model.data"]._xmlid_to_res_id("base.group_user"),
                env["ir.access"]._get_all_access(),
            )

        before = read()
        change()
        with self.assertQueryCount(0):
            self.assertEqual(read(), before)

    def test_the_defaults_the_xml_ids_and_the_rows_stay_warm(self):
        self.assertStayWarm(self.add)
        self.assertStayWarm(self.remove)

    def test_they_stay_warm_over_a_write_on_the_group_side(self):
        self.assertStayWarm(
            lambda: self.group.write({"user_ids": [Command.link(self.user.id)]})
        )
        self.assertStayWarm(
            lambda: self.group.write({"user_ids": [Command.unlink(self.user.id)]})
        )

    def test_the_menus_follow(self):
        action = self.env["ir.actions.act_window"].create(
            {"name": "Membership probe", "res_model": "res.partner"}
        )
        menu = self.env["ir.ui.menu"].create(
            {
                "name": "Membership probe",
                "action": f"{action._name},{action.id}",
                "group_ids": [Command.set(self.group.ids)],
            }
        )
        menus = self.env(user=self.user)["ir.ui.menu"]
        self.assertNotIn(menu.id, menus.load_menus_root()["all_menu_ids"])
        self.assertNotIn(menu.id, menus.load_menus(False))
        self.add()
        self.assertIn(menu.id, menus.load_menus_root()["all_menu_ids"])
        self.assertIn(menu.id, menus.load_menus(False))
        self.remove()
        self.assertNotIn(menu.id, menus.load_menus_root()["all_menu_ids"])
        self.assertNotIn(menu.id, menus.load_menus(False))

    def test_a_view_projection_follows(self):
        view = self.env["ir.ui.view"].create(
            {
                "name": "Membership probe",
                "model": "res.partner",
                "type": "form",
                "arch": """<form>
                    <field name="name"/>
                    <field name="ref" groups="base.membership_probe"/>
                </form>""",
            }
        )
        partners = self.env(user=self.user)["res.partner"]

        def shows_ref():
            return 'name="ref"' in partners.get_view(view.id, "form")["arch"]

        self.assertFalse(shows_ref())
        self.add()
        self.assertTrue(shows_ref())
        self.remove()
        self.assertFalse(shows_ref())
