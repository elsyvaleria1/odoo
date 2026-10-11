from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.captcha.models.captcha_adapter import CaptchaAdapter
from odoo.addons.captcha.models.ir_http import IrHttp
from odoo.addons.captcha.provider import CaptchaProvider

FAKE = CaptchaProvider(code="fake", label="Fake Captcha", adapter="captcha.adapter")
ADAPTER = "odoo.addons.captcha.models.captcha_adapter"
HOOK = "odoo.addons.captcha.models.ir_http"


@tagged("post_install", "-at_install")
class TestCaptcha(TransactionCase):
    """The forms ask one provider, chosen in the settings, through one hook."""

    def setUp(self):
        super().setUp()
        self.startPatcher(
            patch.object(IrHttp, "_captcha_providers", lambda self: {"fake": FAKE})
        )
        self.startPatcher(
            patch.object(CaptchaAdapter, "_site_key", lambda self: "SITE", create=True)
        )
        self.has_secret = True
        self.startPatcher(
            patch.object(
                CaptchaAdapter,
                "_has_secret",
                lambda adapter: self.has_secret,
                create=True,
            )
        )
        self.env["ir.config_parameter"].sudo().set_param("captcha.provider", "fake")

    @contextmanager
    def _request(self, verdict, params=None):
        request = MagicMock()
        request.httprequest.remote_addr = "10.0.0.1"
        request.params = {"captcha_token": "a-token", **(params or {})}
        with (
            patch(f"{HOOK}.request", request),
            patch.object(CaptchaAdapter, "_verdict", return_value=verdict) as asked,
        ):
            yield request, asked

    def test_a_human_passes_and_the_token_leaves_the_params(self):
        with self._request("is_human") as (request, asked):
            self.env["ir.http"]._check_request_captcha_token("login")
        asked.assert_called_once_with("10.0.0.1", "a-token", "login")
        self.assertNotIn("captcha_token", request.params)

    def test_each_refusal_is_said(self):
        for verdict, error in (
            ("wrong_secret", ValidationError),
            ("wrong_token", ValidationError),
            ("timeout", UserError),
            ("bad_request", UserError),
            ("wrong_action", UserError),
            ("is_bot", UserError),
        ):
            with self.subTest(verdict=verdict), self._request(verdict):
                with self.assertRaises(error):
                    self.env["ir.http"]._check_request_captcha_token("login")

    def test_with_none_chosen_nothing_is_checked(self):
        self.env["ir.config_parameter"].sudo().set_param("captcha.provider", "none")
        with self._request("is_bot") as (__, asked):
            self.env["ir.http"]._check_request_captcha_token("login")
        asked.assert_not_called()

    def test_with_no_choice_the_configured_provider_checks(self):
        self.env["ir.config_parameter"].sudo().set_param("captcha.provider", "")
        self.assertEqual(self.env["ir.http"]._captcha_provider(), FAKE)
        self.has_secret = False
        self.assertIsNone(self.env["ir.http"]._captcha_provider())

    def test_with_no_choice_the_first_configured_provider_by_code_checks(self):
        other = CaptchaProvider(code="aaa", label="Other", adapter="captcha.adapter")
        self.env["ir.config_parameter"].sudo().set_param("captcha.provider", "")
        with patch.object(
            IrHttp, "_captcha_providers", lambda self: {"fake": FAKE, "aaa": other}
        ):
            self.assertEqual(self.env["ir.http"]._captcha_provider(), other)

    def test_outside_a_request_nothing_is_checked(self):
        self.assertIsNone(self.env["ir.http"]._check_request_captcha_token("login"))

    def test_the_browser_learns_the_provider_and_its_key(self):
        self.assertEqual(
            self.env["ir.http"]._add_captcha_to_session_info({})["captcha"],
            {"provider": "fake", "site_key": "SITE"},
        )
        self.env["ir.config_parameter"].sudo().set_param("captcha.provider", "none")
        self.assertNotIn(
            "captcha", self.env["ir.http"]._add_captcha_to_session_info({})
        )


@tagged("post_install", "-at_install")
class TestSiteverify(TransactionCase):
    """The siteverify protocol reCAPTCHA and Turnstile share."""

    def _verdict(self, *, answer=None, raises=None, token="a-token", action="login"):
        response = MagicMock(**{"json.return_value": answer})
        with (
            patch.object(CaptchaAdapter, "_secret", lambda self: "SECRET", create=True),
            patch.object(
                CaptchaAdapter,
                "_post_verification",
                side_effect=raises,
                return_value=response,
                create=True,
            ),
        ):
            return self.env["captcha.adapter"]._verdict("10.0.0.1", token, action)

    def test_no_secret_checks_nothing(self):
        with patch.object(CaptchaAdapter, "_secret", lambda self: False, create=True):
            self.assertEqual(
                self.env["captcha.adapter"]._verdict("10.0.0.1", "t", "login"),
                "no_secret",
            )

    def test_the_answer_is_read_as_a_verdict(self):
        for answer, verdict in (
            ({"success": True, "action": "login"}, "is_human"),
            ({"success": True, "action": "signup"}, "wrong_action"),
            (
                {"success": False, "error-codes": ["invalid-input-secret"]},
                "wrong_secret",
            ),
            (
                {"success": False, "error-codes": ["invalid-input-response"]},
                "wrong_token",
            ),
            ({"success": False, "error-codes": ["timeout-or-duplicate"]}, "timeout"),
            ({"success": False, "error-codes": ["bad-request"]}, "bad_request"),
            ({"success": False, "error-codes": []}, "is_bot"),
        ):
            with self.subTest(answer=answer):
                self.assertEqual(self._verdict(answer=answer), verdict)

    def test_a_timeout_and_a_malformed_answer(self):
        self.assertEqual(self._verdict(raises=requests.exceptions.Timeout()), "timeout")
        with self.assertLogs(ADAPTER, "ERROR") as logs:
            self.assertEqual(self._verdict(raises=ValueError("boom")), "bad_request")
        self.assertIn("ValueError", logs.output[0])

    def test_a_refused_token_reaches_the_log_by_its_prefix_alone(self):
        huge = "A" * 100_000
        with self.assertLogs(ADAPTER, "WARNING") as logs:
            verdict = self._verdict(
                answer={"success": False, "error-codes": ["invalid-input-response"]},
                token=huge,
            )
        self.assertEqual(verdict, "wrong_token")
        logged = "".join(logs.output)
        self.assertNotIn(huge, logged)
        self.assertLess(len(logged), 500)
        self.assertIn("invalid-input-response", logged)

    def test_a_missing_token_is_refused_without_asking(self):
        with (
            patch.object(CaptchaAdapter, "_secret", lambda self: "SECRET", create=True),
            patch.object(CaptchaAdapter, "_post_verification", create=True) as sent,
        ):
            for token in (False, ""):
                self.assertEqual(
                    self.env["captcha.adapter"]._verdict("10.0.0.1", token, "login"),
                    "wrong_token",
                )
        sent.assert_not_called()
