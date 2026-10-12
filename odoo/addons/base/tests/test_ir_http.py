import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from odoo import http
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.exceptions import AccessDenied, ConcurrencyError
from odoo.http import SessionExpiredException
from odoo.http.core import _request_stack
from odoo.tests.common import TransactionCase

from odoo.addons.base.models.ir_http import IrHttp as BaseIrHttp


class _FakeSession(dict):
    uid = None


class TestIrHttpAuth(TransactionCase):
    @contextmanager
    def _fake_request(self, env, path="/"):
        fake = SimpleNamespace(
            env=env,
            bound_env=env,
            session=_FakeSession(),
            httprequest=SimpleNamespace(path=path, host="localhost"),
        )
        _request_stack.push(fake)
        try:
            yield fake
        finally:
            _request_stack.pop()

    def test_auth_method_user_rejects_public(self):
        public_uid = self.env.ref("base.public_user").id
        with self._fake_request(self.env(user=public_uid)):
            with self.assertRaises(SessionExpiredException):
                self.registry["ir.http"]._auth_method_user()

    def test_authenticate_explicit_unknown_method(self):
        with self._fake_request(self.env) as fake:
            fake.session = SimpleNamespace(uid=None)
            with self.assertRaises(AccessDenied):
                self.registry["ir.http"]._authenticate_explicit("does_not_exist")

    def test_authentication_concurrency_errors_reach_the_retry_layer(self):
        for error in (*PG_RETRY_EXCEPTIONS, ConcurrencyError):
            with (
                self.subTest(error=error),
                self._fake_request(self.env),
                patch.object(
                    self.registry["ir.http"],
                    "_auth_method_none",
                    side_effect=error("retry authentication"),
                ),
                self.assertRaises(error),
            ):
                self.registry["ir.http"]._authenticate_explicit("none")

    def test_unexpected_authentication_error_still_denies_access(self):
        with (
            self._fake_request(self.env),
            patch.object(
                self.registry["ir.http"],
                "_auth_method_none",
                side_effect=RuntimeError("broken verifier"),
            ),
            self.assertRaises(AccessDenied),
        ):
            self.registry["ir.http"]._authenticate_explicit("none")

    def test_serve_fallback_skips_non_public(self):
        path = "/non_public_fallback_probe"
        self.env["ir.attachment"].sudo().create(
            {
                "name": "probe.bin",
                "type": "binary",
                "url": path,
                "raw": b"secret",
                "public": False,
            }
        )
        serve_fallback = BaseIrHttp.__dict__["_serve_fallback"].__func__
        with self._fake_request(self.env, path=path):
            self.assertIsNone(
                serve_fallback(self.registry["ir.http"]),
                "non-public binary attachment must not be served by the fallback",
            )

    def test_serve_attachment_public_filter(self):
        path = "/serve_attachment_public_filter_probe"
        Attachment = self.env["ir.attachment"].sudo()
        non_public = Attachment.create(
            {
                "name": "private.bin",
                "type": "binary",
                "url": path,
                "raw": b"secret",
                "public": False,
            }
        )
        public = Attachment.create(
            {
                "name": "public.bin",
                "type": "binary",
                "url": path,
                "raw": b"hello",
                "public": True,
            }
        )
        served = Attachment._get_serve_attachment(
            path, extra_domain=[("public", "=", True)]
        )
        self.assertEqual(
            served,
            public,
            "only the public attachment should match the fallback domain",
        )
        self.assertNotEqual(served, non_public)


class TestIrHttpSessionGc(TransactionCase):
    def test_gc_sessions_vacuums_with_the_configured_inactivity(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sessions.max_inactivity_seconds", "4321"
        )
        with patch.object(http.root.session_store, "vacuum") as vacuum:
            self.env["ir.http"]._gc_sessions()
        vacuum.assert_called_once_with(max_lifetime=4321)

    def test_gc_sessions_is_skipped_by_the_environment_switch(self):
        with (
            patch.dict(os.environ, {"ODOO_SKIP_GC_SESSIONS": "1"}),
            patch.object(http.root.session_store, "vacuum") as vacuum,
        ):
            self.env["ir.http"]._gc_sessions()
        vacuum.assert_not_called()


class TestWebTranslationsHash(TransactionCase):
    def test_hash_without_lang_follows_the_context_lang(self):
        for code in ("fr_FR", "es_ES"):
            self.env["res.lang"]._activate_lang(code)
        IrHttp = self.env["ir.http"]
        self.env.registry.clear_cache()
        self.addCleanup(self.env.registry.clear_cache)

        for code in ("fr_FR", "es_ES"):
            with self.subTest(lang=code):
                self.assertEqual(
                    IrHttp.with_context(lang=code)._get_web_translations_hash(
                        ["base"], None
                    ),
                    IrHttp._get_web_translations_hash(["base"], code),
                )


class TestSlugifyPath(TransactionCase):
    def test_the_extension_segment_honours_max_length(self):
        slug = self.env["ir.http"]._slugify(
            "Dir/" + "b" * 80 + ".css", max_length=20, path=True
        )
        self.assertEqual(slug, "dir/" + "b" * 16 + ".css")

    def test_an_extension_longer_than_max_length_is_not_kept(self):
        self.assertEqual(
            self.env["ir.http"]._slugify("dir/style.scss", max_length=4, path=True),
            "dir/styl",
        )

    def test_without_max_length_the_extension_is_kept_whole(self):
        self.assertEqual(
            self.env["ir.http"]._slugify("My Dir/Main Style.css", path=True),
            "my-dir/main-style.css",
        )
