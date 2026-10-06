from unittest.mock import MagicMock, patch

from odoo.libs.guarded_http import GuardedSession
from odoo.tests import TransactionCase, tagged

MODULE = "odoo.addons.website_cf_turnstile.models.ir_http"


@tagged("post_install", "-at_install")
class TestTurnstile(TransactionCase):
    def test_the_hook_outside_a_request_checks_nothing(self):
        """No request means no visitor's token to verify.

        The override read `request.httprequest` first and raised
        `RuntimeError: object is not bound`, which failed every caller of the
        shared hook outside HTTP once Turnstile was installed beside
        reCAPTCHA.
        """
        self.assertIsNone(self.env["ir.http"]._check_request_recaptcha_token("login"))

    def test_a_wrong_action_is_logged_as_text(self):
        """The action is a string; `%f` made the warning itself fail to format."""
        self.env["credential.credential"].sudo()._set_system_secret(
            "cf.turnstile_secret_key", "SECRET"
        )
        req = MagicMock()
        req.env = self.env
        response = MagicMock(
            **{"json.return_value": {"success": True, "action": "signup"}}
        )
        with (
            patch(f"{MODULE}.request", req),
            patch.object(GuardedSession, "request", return_value=response),
            self.assertLogs(MODULE, "WARNING") as logs,
        ):
            verdict = self.env["ir.http"]._get_turnstile_verdict(
                "10.0.0.1", "a-token", action="login"
            )

        self.assertEqual(verdict, "wrong_action")
        self.assertIn("signup", logs.records[0].getMessage())
