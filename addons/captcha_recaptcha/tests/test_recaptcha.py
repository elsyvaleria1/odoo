import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

from odoo.libs.guarded_http import GuardedSession
from odoo.tests import TransactionCase, tagged

ADAPTER = "odoo.addons.captcha_recaptcha.models.captcha_adapter_recaptcha"


@tagged("post_install", "-at_install")
class TestRecaptcha(TransactionCase):
    def setUp(self):
        super().setUp()
        self.icp = self.env["ir.config_parameter"].sudo()
        self.env["credential.credential"]._set_system_secret(
            "captcha_recaptcha.secret_key", "SECRET"
        )

    def _verdict(self, answer):
        response = MagicMock(status_code=200, **{"json.return_value": answer})
        with patch.object(GuardedSession, "request", return_value=response) as sent:
            verdict = (
                self.env["captcha.adapter.recaptcha"]
                .with_user(self.env.ref("base.public_user"))
                ._verdict("10.0.0.1", "a-token", "login")
            )
        return verdict, sent

    def test_a_visitor_is_verified_through_the_service(self):
        verdict, sent = self._verdict(
            {"success": True, "score": 0.9, "action": "login"}
        )
        self.assertEqual(verdict, "is_human")
        method, url = sent.call_args.args[:2]
        self.assertEqual(
            (method, url),
            ("POST", "https://www.recaptcha.net/recaptcha/api/siteverify"),
        )
        self.assertEqual(sent.call_args.kwargs["data"]["secret"], "SECRET")
        self.assertTrue(
            self.env["integration.connection"]
            .sudo()
            .search(
                [
                    (
                        "service_id",
                        "=",
                        self.env.ref("captcha_recaptcha.service_recaptcha").id,
                    )
                ]
            )
        )

    def test_a_score_below_the_minimum_is_a_bot(self):
        self.icp.set_param("captcha_recaptcha.min_score", "0.7")
        for score, verdict in ((0.9, "is_human"), (0.1, "is_bot"), (0.0, "is_bot")):
            with self.subTest(score=score):
                self.assertEqual(
                    self._verdict({"success": True, "score": score, "action": "login"})[
                        0
                    ],
                    verdict,
                )

    def test_a_success_without_a_score_is_not_human(self):
        """v3 scores every success: a scoreless one (a v2 key, an API change)
        read as 0 passed a minimum of 0, and logged a score never sent."""
        for minimum in ("0.7", "0.0"):
            with self.subTest(minimum=minimum):
                self.icp.set_param("captcha_recaptcha.min_score", minimum)
                with self.assertLogs(ADAPTER, "WARNING") as logs:
                    verdict, __ = self._verdict({"success": True, "action": "login"})
                self.assertEqual(verdict, "bad_request")
                self.assertNotIn("0.000000", "".join(logs.output))

    def test_the_secret_setting_lives_in_the_vault(self):
        self.env["res.config.settings"].create(
            {"captcha_recaptcha_secret_key": " OTHER "}
        ).execute()
        self.assertEqual(
            self.env["credential.credential"]._get_system_secret(
                "captcha_recaptcha.secret_key"
            ),
            "OTHER",
        )
        self.assertFalse(self.icp.get_param("captcha_recaptcha.secret_key"))

    def test_the_upgrade_keeps_recaptcha_checking_the_forms(self):
        Credential = self.env["credential.credential"]
        self.icp.set_param("recaptcha_public_key", "SITE")
        self.icp.set_param("recaptcha_min_score", "0.5")
        self.icp.set_param("enable_recaptcha", "True")
        self.icp.set_param("captcha.provider", "")
        Credential._set_system_secret("recaptcha_private_key", "OLD")
        path = Path(__file__).parents[1] / "migrations" / "2.0" / "post-migrate.py"
        spec = importlib.util.spec_from_file_location("recaptcha_2_0", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        migration.migrate(self.env.cr, "1.1")

        self.assertEqual(self.icp.get_param("captcha_recaptcha.site_key"), "SITE")
        self.assertEqual(self.icp.get_param("captcha_recaptcha.min_score"), "0.5")
        self.assertEqual(self.icp.get_param("captcha.provider"), "recaptcha")
        self.assertEqual(
            Credential._get_system_secret("captcha_recaptcha.secret_key"), "OLD"
        )
        self.assertFalse(Credential._get_system_secret("recaptcha_private_key"))
        self.assertFalse(self.icp.get_param("recaptcha_public_key"))
        self.assertFalse(self.icp.get_param("enable_recaptcha"))
        self.assertEqual(self.env["ir.http"]._captcha_provider().code, "recaptcha")
