import os
from unittest.mock import patch

from cryptography.fernet import Fernet

import odoo
from odoo.exceptions import AccessError, ConcurrencyError, ValidationError
from odoo.libs import sealing
from odoo.modules.registry import Registry
from odoo.tests import common
from odoo.tests.common import BaseCase, TransactionCase, new_test_user
from odoo.tools import mute_logger
from odoo.tools.security import hmac

from odoo.addons.base.models.access_link import TOKEN_SCOPE
from odoo.addons.base.models.ir_config_parameter import _default_parameters


class TestIrConfigParameter(TransactionCase):
    def test_settings_port_preserves_defaults_and_cache_invalidation(self):
        parameters = self.env["ir.config_parameter"]
        env = self.env(user=self.env.ref("base.public_user"))
        settings = env.registry.settings
        key = "test.settings_port.value"
        for default in (None, False, "", 0, 17):
            with self.subTest(default=default):
                self.assertIs(settings.get(env, key, default), default)
        parameters.set_param(key, "0")
        self.assertEqual(settings.get(env, key, False), "0")
        parameters.set_param(key, "updated")
        self.assertEqual(settings.get(env, key), "updated")
        parameters.search([("key", "=", key)]).unlink()
        self.assertIsNone(settings.get(env, key))
        self.assertFalse(env.su)
        with self.assertRaises(AccessError):
            env["ir.config_parameter"].get_param(key)
        with self.assertRaises(AccessError):
            env["ir.config_parameter"].set_param(key, "forbidden")

    def test_settings_port_reads_typed_values_without_elevating_the_caller(self):
        parameters = self.env["ir.config_parameter"]
        env = self.env(user=self.env.ref("base.public_user"))
        settings = env.registry.settings
        key = "test.settings_port.typed"
        self.assertEqual(settings.get_int(env, key, 7), 7)
        self.assertEqual(settings.get_float(env, key, 0.5), 0.5)
        self.assertIs(settings.get_bool(env, key), False)
        self.assertIs(settings.get_bool(env, key, True), True)
        parameters.set_param(key, "12")
        self.assertEqual(settings.get_int(env, key, 7), 12)
        self.assertEqual(settings.get_float(env, key, 0.5), 12.0)
        self.assertIs(settings.get_bool(env, key), True)
        parameters.set_param(key, "off")
        self.assertEqual(settings.get_int(env, key, 7), 7)
        self.assertIs(settings.get_bool(env, key, True), False)
        self.assertFalse(env.su)

    def test_default_parameters(self):
        for key in _default_parameters:
            config_parameter = self.env["ir.config_parameter"].search(
                [("key", "=", key)], limit=1
            )
            with self.assertRaises(ValidationError):
                config_parameter.unlink()

            new_key = f"{key}_updated"
            with self.assertRaises(ValidationError):
                config_parameter.write({"key": new_key})


class TestBuildParametersClearTheAssetsCache(TransactionCase):
    def _assets_generation(self):
        return self.registry.ormcache_lrus["assets"].generation

    def test_each_write_of_a_build_parameter_clears_the_assets_cache(self):
        parameters = self.env["ir.config_parameter"].sudo()
        for step in ("create", "write", "unlink"):
            with self.subTest(step=step):
                generation = self._assets_generation()
                if step == "create":
                    parameters.set_param("web.esbuild.source_maps", "linked")
                elif step == "write":
                    parameters.set_param("web.esbuild.source_maps", "inline")
                else:
                    parameters.search(
                        [("key", "=", "web.esbuild.source_maps")]
                    ).unlink()
                self.assertNotEqual(self._assets_generation(), generation)

    def test_another_parameter_leaves_the_assets_cache(self):
        generation = self._assets_generation()
        self.env["ir.config_parameter"].sudo().set_param("test.unrelated", "1")
        self.assertEqual(self._assets_generation(), generation)


class TestSealedDatabaseSecret(TransactionCase):
    def setUp(self):
        super().setUp()
        self.ICP = self.env["ir.config_parameter"].sudo()
        self.real_key = {sealing.ENV_KEY: Fernet.generate_key().decode()}
        # the database's own secret is sealed with whatever key the server ran
        # under, which no test's key opens: each test starts from a clear one
        self._store_in_clear("the-installed-secret")

    def _stored(self):
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT value FROM ir_config_parameter WHERE key = 'database.secret'"
        )
        return self.env.cr.fetchone()[0]

    def _store_in_clear(self, value):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE ir_config_parameter SET value = %s WHERE key = 'database.secret'",
            [value],
        )
        self.env.invalidate_all()
        self.env.registry.clear_cache("stable")

    def test_with_a_key_the_secret_is_stored_sealed_and_read_in_clear(self):
        with patch.dict(os.environ, self.real_key):
            self.ICP.set_param("database.secret", "the-database-secret")

            self.assertTrue(sealing.is_sealed(self._stored()))
            self.assertNotIn("the-database-secret", self._stored())
            public_env = self.env(user=self.env.ref("base.public_user"))
            self.assertEqual(
                public_env.registry.settings.get(public_env, "database.secret"),
                "the-database-secret",
            )
            self.assertEqual(
                self.ICP.get_param("database.secret"), "the-database-secret"
            )

    def test_setting_the_same_secret_again_writes_nothing(self):
        with patch.dict(os.environ, self.real_key):
            self.ICP.set_param("database.secret", "the-database-secret")
            sealed = self._stored()
            with patch.object(type(self.ICP), "write") as write:
                old = self.ICP.set_param("database.secret", "the-database-secret")
            write.assert_not_called()
            self.assertEqual(old, "the-database-secret")
            self.assertEqual(self._stored(), sealed)

    def test_a_secret_left_in_clear_is_sealed_when_the_registry_loads(self):
        self._store_in_clear("legacy-secret")
        with patch.dict(os.environ, self.real_key):
            self.ICP._seal_sealed_parameters()

            self.assertTrue(sealing.is_sealed(self._stored()))
            self.assertEqual(self.ICP.get_param("database.secret"), "legacy-secret")

    def test_without_a_protecting_key_the_secret_stays_readable_in_clear(self):
        for environ in ({sealing.ENV_KEY: sealing.TEST_RUN_KEY}, {sealing.ENV_KEY: ""}):
            with self.subTest(key=bool(environ[sealing.ENV_KEY])):
                with (
                    patch.dict(os.environ, environ),
                    mute_logger("odoo.addons.base.models.ir_config_parameter"),
                ):
                    self.ICP.set_param("database.secret", "clear-secret")
                    self.ICP._seal_sealed_parameters()

                    self.assertEqual(self._stored(), "clear-secret")
                    self.assertEqual(
                        self.ICP.get_param("database.secret"), "clear-secret"
                    )

    def test_a_server_that_never_held_a_key_reports_the_clear_secret_as_info(self):
        self._store_in_clear("clear-secret")
        logger = "odoo.addons.base.models.ir_config_parameter"
        with (
            patch.dict(os.environ, {sealing.ENV_KEY: ""}),
            self.assertLogs(logger, "INFO") as logged,
        ):
            self.ICP._seal_sealed_parameters()
        self.assertEqual(
            [(r.levelname, r.args) for r in logged.records],
            [("INFO", ("database.secret",))],
        )

    def test_a_server_that_lost_its_key_reports_the_sealed_secret_as_an_error(self):
        with patch.dict(os.environ, self.real_key):
            self.ICP.set_param("database.secret", "the-database-secret")
        logger = "odoo.addons.base.models.ir_config_parameter"
        with (
            patch.dict(os.environ, {sealing.ENV_KEY: ""}),
            self.assertLogs(logger, "INFO") as logged,
        ):
            self.ICP._seal_sealed_parameters()
        self.assertEqual([r.levelname for r in logged.records], ["ERROR"])

    def test_a_copy_replaces_a_secret_sealed_under_a_key_it_does_not_hold(self):
        with patch.dict(os.environ, self.real_key):
            self.ICP.set_param("database.secret", "the-source-secret")
            source_sealed = self._stored()
        self.assertTrue(sealing.is_sealed(source_sealed))

        other_key = {sealing.ENV_KEY: Fernet.generate_key().decode()}
        with patch.dict(os.environ, other_key):
            self.ICP.init(force=True)

            self.assertNotEqual(self._stored(), source_sealed)
            self.assertNotIn(
                self.ICP.get_param("database.secret"), (None, "the-source-secret")
            )

    def test_sealing_changes_no_signature_and_no_session_token(self):
        self._store_in_clear("signing-secret")
        user = self.env.ref("base.user_admin")
        digest = hmac(self.env, TOKEN_SCOPE, "message")
        session_values = user._get_session_token_values()

        with patch.dict(os.environ, self.real_key):
            self.ICP._seal_sealed_parameters()
            self.assertTrue(sealing.is_sealed(self._stored()))

            self.assertEqual(hmac(self.env, TOKEN_SCOPE, "message"), digest)
            self.assertEqual(user._get_session_token_values(), session_values)


class TestTypedParams(TransactionCase):
    KEY = "base.test_typed_param"

    def _read(self, reader, raw, default):
        ICP = self.env["ir.config_parameter"]
        if raw is not None:
            ICP.set_param(self.KEY, raw)
        return getattr(ICP, reader)(self.KEY, default)

    def test_valid_values_are_parsed(self):
        self.assertEqual(self._read("get_param_int", "42", 7), 42)
        self.assertEqual(self._read("get_param_float", "42.5", 7.0), 42.5)
        self.assertEqual(self._read("get_param_float", "42", 7.0), 42.0)

    def test_missing_or_blank_falls_back_silently(self):
        for reader, default in (("get_param_int", 7), ("get_param_float", 7.5)):
            with self.subTest(reader=reader):
                self.assertEqual(self._read(reader, None, default), default)
                self.assertEqual(self._read(reader, "", default), default)

    @mute_logger("odoo.addons.base.models.ir_config_parameter")
    def test_unusable_value_falls_back_and_warns(self):
        for reader, default in (("get_param_int", 7), ("get_param_float", 7.5)):
            for raw in ("ten", "1,5", "12px"):
                with self.subTest(reader=reader, raw=raw):
                    self.assertEqual(self._read(reader, raw, default), default)

    @mute_logger("odoo.addons.base.models.ir_config_parameter")
    def test_float_string_is_not_an_int(self):
        self.assertEqual(self._read("get_param_int", "4.5", 7), 7)


class TestGetParamAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        privilege = cls.env["res.groups"].create(
            {"name": "Probe: read one system parameter", "is_privilege": True}
        )
        cls.env["ir.model.data"].create(
            {
                "module": "base",
                "name": "probe_privilege_one_parameter",
                "model": "res.groups",
                "res_id": privilege.id,
            }
        )
        cls.env["ir.access"].create(
            {
                "name": "Probe privilege: read base.probe_parameter",
                "model_id": cls.env["ir.model"]._get_id("ir.config_parameter"),
                "group_id": privilege.id,
                "kind": "permission",
                "operation": "r",
                "domain": "[('key', '=', 'base.probe_parameter')]",
            }
        )
        cls.env["ir.config_parameter"].set_param("base.probe_parameter", "granted")
        user = new_test_user(cls.env, login="probe_parameter", groups="base.group_user")
        cls.ICP = (
            cls.env["ir.config_parameter"]
            .with_user(user)
            .with_privilege("base.probe_privilege_one_parameter", reason="probe")
        )

    def test_a_key_scoped_permission_reads_its_key_and_no_other(self):
        self.assertEqual(self.ICP.get_param("base.probe_parameter"), "granted")
        with self.assertRaises(AccessError):
            self.ICP.get_param("database.uuid")

    def test_an_absent_key_answers_the_default(self):
        self.assertEqual(
            self.ICP.get_param("base.probe_absent", "fallback"), "fallback"
        )


class TestSetGetParam(TransactionCase):
    def test_set_get_param_lifecycle(self):
        ICP = self.env["ir.config_parameter"]
        key = "base.test_set_get_param"
        self.assertEqual(ICP.get_param(key, default="fallback"), "fallback")
        self.assertEqual(ICP.get_param(key), False)
        self.assertEqual(ICP.set_param(key, "v1"), False)
        self.assertEqual(ICP.get_param(key), "v1")
        self.assertEqual(ICP.set_param(key, "v2"), "v1")
        self.assertEqual(ICP.get_param(key), "v2")
        self.assertEqual(ICP.set_param(key, 42), "v2")
        self.assertEqual(ICP.get_param(key), "42")
        self.assertEqual(ICP.set_param(key, "42"), "42")
        self.assertEqual(ICP.set_param(key, False), "42")
        self.assertEqual(ICP.get_param(key), False)
        self.assertEqual(ICP.set_param(key, False), False)

    @mute_logger("odoo.db.cursor")
    def test_set_param_create_race(self):
        ICP = self.env["ir.config_parameter"]
        key = "base.test_set_param_race"
        ICP.set_param(key, "concurrent")
        cls = self.registry["ir.config_parameter"]
        original_search = cls.search
        missed = []

        def racy_search(model, domain, *args, **kwargs):
            if not missed and domain == [("key", "=", key)]:
                missed.append(True)
                return model.browse()
            return original_search(model, domain, *args, **kwargs)

        with patch.object(cls, "search", racy_search):
            old = ICP.set_param(key, "winner")

        self.assertTrue(missed, "the racy search stub was not exercised")
        self.assertEqual(old, "concurrent")
        self.assertEqual(ICP.get_param(key), "winner")


class TestSetParamConcurrency(BaseCase):
    KEY = "base.test_set_param_cross_tx_race"

    def setUp(self):
        super().setUp()
        self.addCleanup(self._drop_key)
        self._drop_key()

    def _drop_key(self):
        registry = Registry(common.get_db_name())
        with registry.cursor() as cr:
            env = odoo.api.Environment(cr, common.ADMIN_USER_ID, {})
            env["ir.config_parameter"].search([("key", "=", self.KEY)]).unlink()

    @mute_logger("odoo.db.cursor")
    def test_set_param_concurrent_create_is_retryable(self):
        registry = Registry(common.get_db_name())
        with registry.cursor() as cr_a, registry.cursor() as cr_b:
            env_a = odoo.api.Environment(cr_a, common.ADMIN_USER_ID, {})
            env_b = odoo.api.Environment(cr_b, common.ADMIN_USER_ID, {})
            for env in (env_a, env_b):
                env["ir.config_parameter"].search_count([("key", "=", self.KEY)])

            env_a["ir.config_parameter"].set_param(self.KEY, "winner")
            cr_a.commit()

            with self.assertRaises(ConcurrencyError):
                env_b["ir.config_parameter"].set_param(self.KEY, "loser")

            cr_b.rollback()
            env_b = odoo.api.Environment(cr_b, common.ADMIN_USER_ID, {})
            self.assertEqual(
                env_b["ir.config_parameter"].set_param(self.KEY, "loser"), "winner"
            )
