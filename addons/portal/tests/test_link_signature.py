import hashlib
import hmac
from datetime import date
from unittest.mock import patch

from freezegun import freeze_time

from odoo import api
from odoo.tests import HttpCase, TransactionCase
from odoo.tools import hmac as scoped_hmac
from odoo.tools import is_hmac_valid, register_signed_scope
from odoo.tools.security import _SIGNED_SCOPES

from odoo.addons.portal.models import mixin_mail_thread
from odoo.addons.portal.models.mixin_mail_thread import (
    LEGACY_HASH_ENABLED,
    LEGACY_HASH_LAST_USED,
    PARTNER_HASH_SCOPE,
)
from odoo.addons.portal.utils import is_thread_hash_pid_valid

TOKEN = "a-stored-token"
DEBUG_LOGGER = "odoo.debug.logic.portal.mixin_mail_thread"
GC_LOGGER = "odoo.addons.portal.models.ir_config_parameter"


class _LinkSignatureCase:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create(
            {"name": "Signed Customer", "email": "signed@example.com"}
        )

    def setUp(self):
        super().setUp()
        self.patch(
            self.env.registry["res.partner"], "_mail_post_token_field", "signup_type"
        )
        self.record = self.customer.sudo()
        self.record.signup_type = TOKEN
        self.pid = self.customer.id
        self.signed = (self.env.cr.dbname, TOKEN, self.pid)

    def _bare_secret_hash(self):
        secret = self.env["ir.config_parameter"].sudo().get_param("database.secret")
        return hmac.new(
            secret.encode(), repr(self.signed).encode(), hashlib.sha256
        ).hexdigest()

    def _params(self, **values):
        params = self.env["ir.config_parameter"]
        for key, value in values.items():
            params.set_param(key, value)

    def _param(self, key):
        return self.env.registry.settings.get(self.env, key)

    def _legacy_enabled(self, last_used="2999-01-01"):
        self._params(**{LEGACY_HASH_ENABLED: "True", LEGACY_HASH_LAST_USED: last_used})


class TestLinkSignature(_LinkSignatureCase, TransactionCase):
    def test_a_new_link_is_signed_in_the_portal_scope_and_verifies(self):
        signature = self.record._sign_token(self.pid)
        self.assertEqual(
            signature, scoped_hmac(self.env, PARTNER_HASH_SCOPE, self.signed)
        )
        self.assertNotEqual(signature, self._bare_secret_hash())
        self.assertTrue(is_thread_hash_pid_valid(self.record, signature, self.pid))
        self.assertTrue(is_thread_hash_pid_valid(self.record, signature, str(self.pid)))

    def test_a_legacy_link_verifies_while_enabled_and_says_so(self):
        legacy = self._bare_secret_hash()
        self._legacy_enabled()
        with self.assertLogs(DEBUG_LOGGER, "DEBUG") as captured:
            self.assertTrue(is_thread_hash_pid_valid(self.record, legacy, self.pid))
        (line,) = captured.output
        self.assertIn("event=legacy_hash_accepted", line)
        self.assertIn(f"record={self.pid}", line)
        self.assertNotIn(legacy, line, "the signature itself is never logged")

        for enabled in ("False", False):
            with self.subTest(enabled=enabled):
                self._params(**{LEGACY_HASH_ENABLED: enabled})
                with self.assertNoLogs(DEBUG_LOGGER, "DEBUG"):
                    self.assertFalse(
                        is_thread_hash_pid_valid(self.record, legacy, self.pid)
                    )

    def test_a_legacy_link_records_its_day_once(self):
        legacy = self._bare_secret_hash()
        self._legacy_enabled(last_used="2026-09-01")
        writes = []
        IrConfigParameter = type(self.env["ir.config_parameter"])
        write = IrConfigParameter.write

        def counted_write(params, vals):
            writes.append(params.mapped("key"))
            return write(params, vals)

        with patch.object(IrConfigParameter, "write", counted_write):
            for day in ("2026-10-01", "2026-10-01", "2026-10-02"):
                with freeze_time(day):
                    for _ in range(3):
                        self.assertTrue(
                            is_thread_hash_pid_valid(self.record, legacy, self.pid)
                        )
                self.assertEqual(self._param(LEGACY_HASH_LAST_USED), day)
        self.assertEqual(
            writes,
            [[LEGACY_HASH_LAST_USED], [LEGACY_HASH_LAST_USED]],
            "one write the first time a legacy link opens each day, none after",
        )

    def test_a_fresh_install_refuses_a_legacy_link(self):
        self.assertIsNone(self._param(LEGACY_HASH_ENABLED))
        self.assertIsNone(self._param(LEGACY_HASH_LAST_USED))
        with self.assertNoLogs(DEBUG_LOGGER, "DEBUG"):
            self.assertFalse(
                is_thread_hash_pid_valid(
                    self.record, self._bare_secret_hash(), self.pid
                )
            )
        self.assertTrue(
            is_thread_hash_pid_valid(
                self.record, self.record._sign_token(self.pid), self.pid
            )
        )

    def test_the_fallback_ends_after_thirty_idle_days_and_not_before(self):
        params = self.env["ir.config_parameter"]
        self._legacy_enabled(last_used="2026-09-01")
        with freeze_time("2026-09-30"), self.assertNoLogs(GC_LOGGER, "INFO"):
            params._gc_portal_legacy_hash()
        self.assertEqual(self._param(LEGACY_HASH_ENABLED), "True")
        legacy = self._bare_secret_hash()
        self.assertTrue(is_thread_hash_pid_valid(self.record, legacy, self.pid))

        self._params(**{LEGACY_HASH_LAST_USED: "2026-09-01"})
        with freeze_time("2026-10-01"), self.assertLogs(GC_LOGGER, "INFO") as ended:
            params._gc_portal_legacy_hash()
        (line,) = ended.output
        self.assertIn("2026-09-01", line)
        self.assertEqual(self._param(LEGACY_HASH_ENABLED), "False")
        self.assertFalse(is_thread_hash_pid_valid(self.record, legacy, self.pid))
        with freeze_time("2026-10-02"), self.assertNoLogs(GC_LOGGER, "INFO"):
            params._gc_portal_legacy_hash()
        self.assertEqual(self._param(LEGACY_HASH_LAST_USED), "2026-09-01")

    def test_the_fallback_enabled_without_a_day_counts_from_the_sweep(self):
        self._params(**{LEGACY_HASH_ENABLED: "True"})
        with freeze_time("2026-10-01"):
            self.env["ir.config_parameter"]._gc_portal_legacy_hash()
        self.assertEqual(self._param(LEGACY_HASH_ENABLED), "True")
        self.assertEqual(self._param(LEGACY_HASH_LAST_USED), "2026-10-01")

    def test_a_link_signed_for_another_scope_is_refused(self):
        other_scope = "test.portal_other_scope"
        self.addCleanup(_SIGNED_SCOPES.pop, other_scope, None)
        register_signed_scope(other_scope, purpose="a test", lifetime="undated")
        self._legacy_enabled()
        other = scoped_hmac(self.env, other_scope, self.signed)
        self.assertFalse(is_thread_hash_pid_valid(self.record, other, self.pid))
        signature = self.record._sign_token(self.pid)
        self.assertFalse(
            is_hmac_valid(self.env, other_scope, self.signed, signature),
            "a portal hash proves nothing in any other scope",
        )

    def test_a_tampered_link_is_refused(self):
        self._legacy_enabled()
        signature = self.record._sign_token(self.pid)
        other = self.env["res.partner"].create({"name": "Someone Else"})
        flipped = signature[:-1] + ("0" if signature[-1] != "0" else "1")
        for name, presented, pid in (
            ("flipped", flipped, self.pid),
            ("truncated", signature[:-1], self.pid),
            ("upper", signature.upper(), self.pid),
            ("another partner", signature, other.id),
            ("over another token", self.record._sign_token(self.pid, "x"), self.pid),
            ("legacy for another partner", self._bare_secret_hash(), other.id),
        ):
            with self.subTest(name):
                self.assertFalse(is_thread_hash_pid_valid(self.record, presented, pid))


class TestLegacyLinkOnAReadOnlyRequest(_LinkSignatureCase, HttpCase):
    def test_the_day_is_recorded_once_the_cursor_is_released(self):
        self._legacy_enabled(last_used="2026-09-01")
        legacy = self._bare_secret_hash()
        deferred = []
        fake_request = type("Request", (), {"call_after_release": deferred.append})
        public = self.env.ref("base.public_user")
        with (
            patch.object(mixin_mail_thread, "request", fake_request()),
            self.env.registry.cursor(readonly=True) as cr,
        ):
            record = self.record.with_env(api.Environment(cr, public.id, {}))
            self.assertTrue(is_thread_hash_pid_valid(record.sudo(), legacy, self.pid))
        self.assertEqual(self._param(LEGACY_HASH_LAST_USED), "2026-09-01")
        (record_use,) = deferred
        record_use()
        self.env.invalidate_all()
        self.assertEqual(self._param(LEGACY_HASH_LAST_USED), date.today().isoformat())
