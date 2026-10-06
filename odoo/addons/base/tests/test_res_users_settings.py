from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestResUsersSettingsOwnership(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = new_test_user(cls.env, login="ruset_a", groups="base.group_user")
        cls.user_b = new_test_user(cls.env, login="ruset_b", groups="base.group_user")
        Settings = cls.env["res.users.settings"]
        cls.settings_a = Settings._get_or_create_for_user(cls.user_a)
        cls.settings_b = Settings._get_or_create_for_user(cls.user_b)
        cls._writable_field = next(
            (
                name
                for name, field in Settings._fields.items()
                if name not in Settings._PROTECTED_SETTINGS_FIELDS
                and field.store
                and not (field.compute and not field.inverse)
                and not field.relational
            ),
            None,
        )

    def test_user_cannot_write_other_users_settings(self):
        settings_b_as_a = self.settings_b.with_user(self.user_a)
        vals = {self._writable_field: False} if self._writable_field else {}
        with self.assertRaises(AccessError):
            settings_b_as_a.write(vals)

    def test_user_cannot_read_other_users_settings(self):
        settings_b_as_a = self.settings_b.with_user(self.user_a)
        with self.assertRaises(AccessError):
            settings_b_as_a._res_users_settings_format()

    def test_protected_user_id_cannot_be_rewritten(self):
        settings_a_as_a = self.settings_a.with_user(self.user_a)
        settings_a_as_a.set_res_users_settings({"user_id": self.user_b.id})
        self.assertEqual(
            self.settings_a.user_id,
            self.user_a,
            "user_id must not be rewritable via set_res_users_settings (RUSET-L2)",
        )


class TestResUsersSettingsChangeDetection(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = new_test_user(cls.env, login="rusetcd_a", groups="base.group_user")
        cls.user_b = new_test_user(cls.env, login="rusetcd_b", groups="base.group_user")
        cls.settings_a = cls.env["res.users.settings"]._get_or_create_for_user(
            cls.user_a
        )

    def test_x2many_command_target_ids_static_commands(self):
        normalize = self.env["res.users.settings"]._get_x2many_command_target_ids
        current = {1, 2}
        self.assertEqual(normalize(current, [Command.set([2, 1])]), {1, 2})
        self.assertEqual(normalize(current, [Command.set([3])]), {3})
        self.assertEqual(normalize(current, [Command.set([])]), set())
        self.assertEqual(normalize(current, [Command.link(2)]), {1, 2})
        self.assertEqual(normalize(current, [Command.link(3)]), {1, 2, 3})
        self.assertEqual(normalize(current, [Command.unlink(2)]), {1})
        self.assertEqual(normalize(current, [Command.delete(2)]), {1})
        self.assertEqual(normalize(current, [Command.clear()]), set())
        self.assertEqual(normalize(current, [Command.clear(), Command.link(5)]), {5})
        self.assertEqual(normalize(current, [3, 4]), {1, 2, 3, 4})
        self.assertEqual(normalize(current, []), {1, 2})
        self.assertEqual(current, {1, 2})

    def test_x2many_command_target_ids_dynamic_or_malformed(self):
        normalize = self.env["res.users.settings"]._get_x2many_command_target_ids
        current = {1, 2}
        self.assertIsNone(normalize(current, [Command.create({"name": "x"})]))
        self.assertIsNone(normalize(current, [Command.update(1, {"name": "x"})]))
        self.assertIsNone(normalize(current, "nope"))
        self.assertIsNone(normalize(current, 5))
        self.assertIsNone(normalize(current, {1, 2}))
        self.assertIsNone(normalize(current, [("bogus",)]))
        self.assertIsNone(normalize(current, [(9, 1, 2)]))
        self.assertIsNone(normalize(current, [True]))

    def test_is_setting_changed_many2one_compares_ids(self):
        settings = self.settings_a
        self.assertFalse(settings._is_setting_changed("user_id", self.user_a.id))
        self.assertTrue(settings._is_setting_changed("user_id", self.user_b.id))
        self.assertTrue(settings._is_setting_changed("user_id", False))
        empty = self.env["res.users.settings"].new({})
        self.assertFalse(empty._is_setting_changed("user_id", False))
        self.assertFalse(empty._is_setting_changed("user_id", None))

    def test_is_setting_changed_scalar(self):
        settings = self.settings_a
        self.assertFalse(
            settings._is_setting_changed("display_name", settings.display_name)
        )
        self.assertTrue(settings._is_setting_changed("display_name", "something else"))


@tagged("post_install", "-at_install")
class TestResUsersSettingsWriteOnlyChanges(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="rusetwoc", groups="base.group_user")
        cls.settings = cls.env["res.users.settings"]._get_or_create_for_user(cls.user)

    def _find_writable_field(self, types):
        Settings = self.env["res.users.settings"]
        as_user = Settings.with_user(self.user)
        return next(
            (
                name
                for name, field in Settings._fields.items()
                if name not in Settings._PROTECTED_SETTINGS_FIELDS
                and field.type in types
                and field.store
                and not (field.compute and not field.inverse)
                and as_user._has_field_access(field, "read")
                and as_user._has_field_access(field, "write")
            ),
            None,
        )

    def test_unchanged_x2many_is_not_written(self):
        fname = self._find_writable_field(("many2many", "one2many"))
        if not fname:
            self.skipTest("no writable x2many field on res.users.settings")
        settings = self.settings.with_user(self.user)
        current_ids = settings[fname].ids
        res = settings.set_res_users_settings({fname: [Command.set(current_ids)]})
        self.assertEqual(
            set(res.keys()),
            {"id"},
            f"re-submitting the current value of {fname} must not be a change",
        )

    def test_unchanged_many2one_is_not_written(self):
        Settings = self.env["res.users.settings"]
        unprotected = Settings._PROTECTED_SETTINGS_FIELDS - {"user_id"}
        settings = self.settings.with_user(self.user)
        with patch.object(type(Settings), "_PROTECTED_SETTINGS_FIELDS", unprotected):
            res = settings.set_res_users_settings({"user_id": self.user.id})
        self.assertEqual(
            set(res.keys()),
            {"id"},
            "re-submitting the current value of a many2one must not be a change",
        )


@tagged("post_install", "-at_install")
class TestResUsersSettingsRowLifecycle(TransactionCase):
    def test_created_internal_user_has_settings(self):
        user = new_test_user(self.env, login="rusetlc_a", groups="base.group_user")
        self.assertTrue(user.res_users_settings_id)

    def test_created_portal_user_has_none(self):
        user = new_test_user(self.env, login="rusetlc_b", groups="base.group_portal")
        self.assertFalse(user.res_users_settings_id)

    def test_promotion_alone_makes_no_row(self):
        user = new_test_user(self.env, login="rusetlc_c", groups="base.group_portal")
        user.write(
            {
                "group_ids": [
                    Command.unlink(self.env.ref("base.group_portal").id),
                    Command.link(self.env.ref("base.group_user").id),
                ]
            }
        )
        user.invalidate_recordset()
        self.assertFalse(user.res_users_settings_id)
        self.assertTrue(
            self.env["res.users.settings"]._get_or_create_for_user(user),
            "the accessor the web client boots through must close it",
        )

    def test_settings_backed_fields_come_from_the_registry(self):
        users = self.env["res.users"]
        backed = users._get_settings_backed_fields()
        for name in backed:
            field = users._fields[name]
            self.assertTrue(field.related.startswith("res_users_settings_id."))
            self.assertFalse(field.readonly, f"{name} cannot be written anyway")
        self.assertEqual(
            backed,
            frozenset(
                name
                for name, field in users._fields.items()
                if field.related
                and field.related.startswith("res_users_settings_id.")
                and not field.readonly
            ),
        )

    def test_a_settings_write_makes_its_own_row(self):
        for name, value in self._writable_settings_values():
            user = new_test_user(
                self.env, login=f"rusetlc_w_{name}", groups="base.group_portal"
            )
            self.assertFalse(user.res_users_settings_id)
            user.write({name: value})
            user.invalidate_recordset()
            self.assertTrue(user.res_users_settings_id, f"{name} made no row")
            self.assertEqual(user[name], value, f"{name} was written to nothing")

    def test_a_settings_write_does_not_answer_a_readonly_cursor_with_nothing(self):
        name, value = next(iter(self._writable_settings_values()))
        user = new_test_user(self.env, login="rusetlc_ro", groups="base.group_portal")
        self.assertFalse(user.res_users_settings_id)

        cursor = self.env.cr
        was_readonly = cursor._readonly
        cursor._readonly = True
        try:
            user.write({name: value})
        finally:
            cursor._readonly = was_readonly

        user.invalidate_recordset()
        self.assertTrue(user.res_users_settings_id, f"{name} made no row")
        self.assertEqual(user[name], value, f"{name} was written to nothing")

    def test_a_readonly_cursor_is_not_handed_an_unsaved_settings_row(self):
        user = new_test_user(
            self.env, login="rusetlc_ro_get", groups="base.group_portal"
        )
        self.assertFalse(user.res_users_settings_id)

        cursor = self.env.cr
        was_readonly = cursor._readonly
        cursor._readonly = True
        try:
            settings = self.env["res.users.settings"]._get_or_create_for_user(user)
        finally:
            cursor._readonly = was_readonly

        self.assertIsInstance(settings.id, int)
        self.assertEqual(settings._res_users_settings_format(["id"])["id"], settings.id)

    def test_a_settings_value_survives_create(self):
        for name, value in self._writable_settings_values():
            user = self.env["res.users"].create(
                {
                    "login": f"rusetlc_c_{name}",
                    "name": "created with a preference",
                    name: value,
                    "group_ids": [Command.link(self.env.ref("base.group_user").id)],
                }
            )
            user.invalidate_recordset()
            self.assertEqual(user[name], value, f"{name} was created onto nothing")

    def _writable_settings_values(self):
        settings_fields = self.env["res.users.settings"]._fields
        for name in sorted(self.env["res.users"]._get_settings_backed_fields()):
            selection = getattr(settings_fields[name], "selection", None)
            if isinstance(selection, list):
                yield name, selection[-1][0]


@tagged("post_install", "-at_install")
class TestResUsersSettingsOwnRow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal = new_test_user(
            cls.env, login="rusetown_p", groups="base.group_portal"
        )
        cls.other = new_test_user(cls.env, login="rusetown_o", groups="base.group_user")

    def test_a_portal_user_keeps_their_own_settings_without_elevation(self):
        env = self.env(user=self.portal)
        settings = env["res.users.settings"]._get_or_create_for_user(env.user)
        self.assertFalse(settings.env.su)
        self.assertEqual(settings.user_id, self.portal)
        self.assertEqual(
            settings._res_users_settings_format()["id"],
            settings.id,
        )
        self.assertEqual(
            env["res.users.settings"]._get_or_create_for_user(env.user), settings
        )

    def test_a_portal_user_reaches_no_one_elses_settings(self):
        other_settings = self.env["res.users.settings"]._get_or_create_for_user(
            self.other
        )
        env = self.env(user=self.portal)
        with self.assertRaises(AccessError):
            env["res.users.settings"]._get_or_create_for_user(self.other)
        with self.assertRaises(AccessError):
            other_settings.with_env(env)._res_users_settings_format()
        with self.assertRaises(AccessError):
            env["res.users.settings"].browse(other_settings.id).unlink()


@tagged("post_install", "-at_install")
class TestResUsersSettingsWrittenWithTheUser(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(
            cls.env, login="rusetpriv_m", groups="base.group_erp_manager"
        )
        cls.plain = new_test_user(
            cls.env, login="rusetpriv_u", groups="base.group_user"
        )
        cls.target = new_test_user(
            cls.env, login="rusetpriv_t", groups="base.group_portal"
        )

    def _privileged(self, user):
        return self.env(user=user)["res.users.settings"].with_privilege(
            "base.privilege_write_user_settings"
        )

    def test_whoever_may_write_a_user_writes_their_settings(self):
        self.assertFalse(self.target.res_users_settings_id)
        with self.assertRaises(AccessError):
            self.env(user=self.admin)["res.users.settings"]._get_or_create_for_user(
                self.target
            )
        settings = self._privileged(self.admin)._get_or_create_for_user(self.target)
        self.assertEqual(settings.user_id, self.target)
        self.assertFalse(settings.env.su)

    def test_the_privilege_reaches_no_user_the_caller_may_not_write(self):
        with self.assertRaises(AccessError):
            self._privileged(self.plain)._get_or_create_for_user(self.target)
