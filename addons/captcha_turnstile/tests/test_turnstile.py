import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

from odoo.libs.guarded_http import GuardedSession
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTurnstile(TransactionCase):
    def setUp(self):
        super().setUp()
        self.icp = self.env["ir.config_parameter"].sudo()

    def test_the_verification_goes_through_its_service(self):
        self.env["credential.credential"]._set_system_secret(
            "captcha_turnstile.secret_key", "SECRET"
        )
        response = MagicMock(
            status_code=200,
            **{"json.return_value": {"success": True, "action": "signup"}},
        )
        with patch.object(GuardedSession, "request", return_value=response) as sent:
            verdict = self.env["captcha.adapter.turnstile"]._verdict(
                "10.0.0.1", "a-token", "login"
            )
        self.assertEqual(verdict, "wrong_action")
        self.assertEqual(
            sent.call_args.args[:2],
            ("POST", "https://challenges.cloudflare.com/turnstile/v0/siteverify"),
        )

    def _migrate(self):
        path = Path(__file__).parents[1] / "migrations" / "2.0" / "post-migrate.py"
        spec = importlib.util.spec_from_file_location("turnstile_2_0", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(self.env.cr, "1.1")

    def test_the_upgrade_keeps_turnstile_checking_the_forms(self):
        Credential = self.env["credential.credential"]
        self.icp.set_param("cf.turnstile_site_key", "SITE")
        self.icp.set_param("captcha.provider", "")
        Credential._set_system_secret("cf.turnstile_secret_key", "OLD")

        self._migrate()

        self.assertEqual(self.icp.get_param("captcha_turnstile.site_key"), "SITE")
        self.assertEqual(self.icp.get_param("captcha.provider"), "turnstile")
        self.assertEqual(
            Credential._get_system_secret("captcha_turnstile.secret_key"), "OLD"
        )
        self.assertFalse(Credential._get_system_secret("cf.turnstile_secret_key"))
        self.assertFalse(self.icp.get_param("cf.turnstile_site_key"))

    def test_the_upgrade_leaves_the_provider_already_chosen(self):
        self.icp.set_param("cf.turnstile_site_key", "SITE")
        self.icp.set_param("captcha.provider", "recaptcha")
        with self.assertLogs(level="WARNING") as logs:
            self._migrate()
        self.assertIn("both configured", logs.output[0])
        self.assertEqual(self.icp.get_param("captcha.provider"), "recaptcha")
