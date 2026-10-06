import unittest
from urllib.parse import parse_qs, urlencode, urlsplit

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

PROVIDER_MIXINS = ("mixin.google.gmail", "mixin.microsoft.outlook")


@tagged("post_install", "-at_install")
class TestProviderIsolation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if any(name not in cls.env.registry for name in PROVIDER_MIXINS):
            raise unittest.SkipTest("needs both bundled providers installed")

        Config = cls.env["ir.config_parameter"].sudo()
        Config.set_param("google_gmail_client_id", "GOOGLE-ID")
        Vault = cls.env["credential.credential"]
        Vault._set_system_secret("google_gmail_client_secret", "GOOGLE-SECRET")
        Config.set_param("microsoft_outlook_client_id", "MICROSOFT-ID")
        Vault._set_system_secret("microsoft_outlook_client_secret", "MICROSOFT-SECRET")

        cls.server = cls.env["ir.mail_server"].create(
            {
                "name": "Two providers",
                "smtp_host": "smtp.example.com",
                "smtp_user": "user@example.com",
            }
        )
        cls.server.invalidate_recordset()
        from odoo.addons.mail_google.models.mixin_google_gmail import GMAIL
        from odoo.addons.mail_microsoft.models.mixin_microsoft_outlook import (
            OUTLOOK,
        )

        cls.gmail_uri = cls.server._oauth2_authorize_uri(GMAIL, "GOOGLE-ID", "S")
        cls.outlook_uri = cls.server._oauth2_authorize_uri(OUTLOOK, "MICROSOFT-ID", "S")

    def _params(self, uri):
        return {key: values[0] for key, values in parse_qs(urlsplit(uri).query).items()}

    def test_each_provider_keeps_its_own_credentials(self):
        gmail = self._params(self.gmail_uri)
        outlook = self._params(self.outlook_uri)

        self.assertEqual(gmail["client_id"], "GOOGLE-ID")
        self.assertEqual(outlook["client_id"], "MICROSOFT-ID")

    def test_each_provider_keeps_its_own_endpoint_and_route(self):
        self.assertTrue(self.gmail_uri.startswith("https://accounts.google.com/"))
        self.assertIn("login.microsoftonline.com", self.outlook_uri)

        gmail = self._params(self.gmail_uri)
        outlook = self._params(self.outlook_uri)
        self.assertTrue(gmail["redirect_uri"].endswith("/google_gmail/confirm"))
        self.assertTrue(outlook["redirect_uri"].endswith("/microsoft_outlook/confirm"))

    def test_each_provider_keeps_its_own_scope_and_extra_params(self):
        gmail = self._params(self.gmail_uri)
        outlook = self._params(self.outlook_uri)

        self.assertIn("https://mail.google.com/", gmail["scope"])
        self.assertIn("offline_access", outlook["scope"])
        self.assertIn(self.server._OUTLOOK_SCOPE, outlook["scope"])

        self.assertEqual(gmail["access_type"], "offline")
        self.assertNotIn("response_mode", gmail)
        self.assertEqual(outlook["response_mode"], "query")
        self.assertNotIn("access_type", outlook)

    def test_each_provider_signs_its_state_in_its_own_scope(self):
        from odoo.addons.mail_google.models.mixin_google_gmail import GMAIL
        from odoo.addons.mail_microsoft.models.mixin_microsoft_outlook import (
            OUTLOOK,
        )

        self.assertNotEqual(GMAIL.csrf_scope, OUTLOOK.csrf_scope)


@tagged("post_install", "-at_install")
class TestProviderStateIsolation(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if any(name not in cls.env.registry for name in PROVIDER_MIXINS):
            raise unittest.SkipTest("needs both bundled providers installed")
        cls.env["ir.config_parameter"].sudo().set_param(
            "google_gmail_client_id", "GOOGLE-ID"
        )
        cls.env["credential.credential"]._set_system_secret(
            "google_gmail_client_secret", "GOOGLE-SECRET"
        )
        cls.server = cls.env["ir.mail_server"].create(
            {
                "name": "Two providers",
                "smtp_host": "smtp.example.com",
                "smtp_user": "user@example.com",
            }
        )

    def test_a_gmail_state_is_refused_by_the_outlook_callback(self):
        self.authenticate("admin", "admin")
        action = self.call_jsonrpc(
            "/web/dataset/call_button",
            {
                "model": "ir.mail_server",
                "method": "open_google_gmail_uri",
                "args": [self.server.ids],
                "kwargs": {},
            },
        )
        state = parse_qs(urlsplit(action["url"]).query)["state"][0]
        query = urlencode({"code": "CODE", "state": state})
        with mute_logger("odoo.addons.mail_microsoft.controllers.main"):
            response = self.url_open(
                f"/microsoft_outlook/confirm?{query}", allow_redirects=False
            )
        self.assertEqual(response.status_code, 403)
