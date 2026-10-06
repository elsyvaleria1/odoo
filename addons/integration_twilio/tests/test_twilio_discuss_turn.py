from odoo.tests import tagged

from odoo.addons.integration_twilio.models import mail_ice_server
from odoo.addons.integration_twilio.tests.common import MockSmsTwilio


@tagged("post_install", "-at_install", "twilio")
class TestTwilioDiscussTurn(MockSmsTwilio):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sms_twilio(cls.company_admin)
        cls.env["ir.config_parameter"].sudo().set_param(
            "mail.use_twilio_rtc_servers", True
        )

    def setUp(self):
        super().setUp()
        self.patch(mail_ice_server, "_company_ice_servers", {})

    def _token_requests(self):
        return [r for r in self.mock_requests if r.url.endswith("/Tokens.json")]

    def test_company_account_serves_turn_when_discuss_has_none(self):
        self.mock_requests.clear()
        servers = self.env["mail.ice.server"]._get_ice_servers()
        self.assertEqual(servers, self.tokens_json["ice_servers"])
        self.env["mail.ice.server"]._get_ice_servers()
        self.assertEqual(len(self._token_requests()), 1, "cached for an hour")

    def test_discuss_own_account_wins(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.twilio_account_sid", "AC99999999999999999999999999999999"
        )
        self.env["credential.credential"]._set_system_secret(
            "mail.twilio_account_token", "own"
        )
        self.mock_requests.clear()
        self.env["mail.ice.server"]._get_ice_servers()
        self.assertTrue(self._token_requests())
        self.assertIn(
            "AC99999999999999999999999999999999", self._token_requests()[0].url
        )

    def test_switched_off_turn_uses_local_servers(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.use_twilio_rtc_servers", False
        )
        self.mock_requests.clear()
        self.env["mail.ice.server"]._get_ice_servers()
        self.assertFalse(self._token_requests())
