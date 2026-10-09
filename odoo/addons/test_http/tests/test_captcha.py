from contextlib import contextmanager
from http import HTTPStatus
from unittest.mock import patch

from odoo import http
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCaptcha(HttpCase):
    def setUp(self):
        super().setUp()
        self.authenticate(None, None)

    @contextmanager
    def patch_captcha_valid(self, validity):
        def _check_request_captcha_token(self, captcha):
            if not validity:
                raise UserError("CAPTCHA test")

        with patch.object(
            self.env.registry["ir.http"],
            "_check_request_captcha_token",
            _check_request_captcha_token,
        ):
            yield

    def test_post_valid(self):
        with self.patch_captcha_valid(True):
            res = self.url_open(
                "/web/login",
                data={
                    "csrf_token": http.Request.csrf_token(self),
                    "login": "_",
                    "password": "_",
                },
            )
            res.raise_for_status()

    def test_post_invalid_is_said_on_the_login_form(self):
        with self.patch_captcha_valid(False):
            res = self.url_open(
                "/web/login",
                data={
                    "csrf_token": http.Request.csrf_token(self),
                    "login": "admin",
                    "password": "admin",
                },
            )
        self.assertEqual(res.status_code, HTTPStatus.OK)
        self.assertIn("CAPTCHA test", res.text)
        self.assertTrue(res.url.endswith("/web/login"), "no session was opened")
        self.assertIn('name="password"', res.text, "the login form, again")

    def test_get_ignores_captcha(self):
        with self.patch_captcha_valid(False):
            res = self.url_open("/web/login")
            res.raise_for_status()
