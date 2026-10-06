import base64
from urllib.parse import parse_qs

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.integration_twilio.tests.common import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    MockSmsTwilio,
)


@tagged("post_install", "-at_install", "twilio")
class TestTwilioAccount(MockSmsTwilio):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sms_twilio(cls.company_admin)
        cls.config = cls.company_admin.integration_twilio_config_id.sudo()

    def test_account_is_one_vault_credential_bound_to_the_service(self):
        credential = self.config.credential_id
        self.assertEqual(
            credential.endpoint_id, self.env.ref("integration_twilio.service_twilio")
        )
        self.assertEqual(
            credential.category_id,
            self.env.ref("credential.credential_category_basic_auth"),
        )
        self.assertEqual(credential.company_id, self.company_admin)
        self.assertEqual(self.config.twilio_account_sid, TWILIO_ACCOUNT_SID)
        self.assertEqual(self.config.twilio_auth_token, TWILIO_AUTH_TOKEN)
        self.assertTrue(credential.auto_validate_health)
        self.assertNotIn(
            "sms_twilio_auth_token", self.company_admin.sudo()._get_held_secrets()
        )

    def test_account_sid_format(self):
        with self.assertRaises(ValidationError):
            self.config.twilio_account_sid = "AC-not-a-sid"

    def test_calls_authenticate_with_the_vault_credential_and_are_logged(self):
        self.config._get_twilio_client().call("GET", "IncomingPhoneNumbers")
        expected = base64.b64encode(
            f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()
        ).decode()
        self.assertEqual(
            self.mock_requests[-1].headers["Authorization"], f"Basic {expected}"
        )
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.assertTrue(
            self.env["integration.exchange"]
            .sudo()
            .search_count(
                [
                    ("direction", "=", "outbound"),
                    ("credential_id", "=", self.config.credential_id.id),
                ]
            )
        )

    def test_sync_numbers_upserts_by_sid_and_keeps_manual_ones(self):
        numbers = self.company_admin.sudo().twilio_number_ids
        manual = numbers.filtered(lambda number: number.number == "+15056998877")
        first = numbers.filtered(lambda number: number.number == "+32455998877")
        first.sequence = 7
        numbers._sync_from_account(self.company_admin)

        numbers = self.company_admin.sudo().twilio_number_ids
        self.assertEqual(len(numbers), 3)
        self.assertIn(manual, numbers)
        self.assertRecordValues(
            numbers.filtered("twilio_sid").sorted("twilio_sid"),
            [
                {
                    "twilio_sid": "PN11111111111111111111111111111111",
                    "number": "+32455998877",
                    "sequence": 7,
                    "is_sms_capable": True,
                    "is_voice_capable": True,
                },
                {
                    "twilio_sid": "PN22222222222222222222222222222222",
                    "number": "+32455665544",
                    "sequence": 1,
                    "is_sms_capable": False,
                    "is_voice_capable": True,
                },
            ],
        )
        self.assertEqual(first.twilio_sid, "PN11111111111111111111111111111111")

        self.patch(
            type(self),
            "incoming_phone_numbers_json",
            {
                "incoming_phone_numbers": self.incoming_phone_numbers_json[
                    "incoming_phone_numbers"
                ][:1],
                "next_page_uri": None,
            },
        )
        numbers._sync_from_account(self.company_admin)
        self.assertEqual(
            set(self.company_admin.sudo().twilio_number_ids.mapped("number")),
            {"+32455998877", "+15056998877"},
        )

    def test_route_sms_points_each_sms_number_at_odoo(self):
        numbers = self.company_admin.sudo().twilio_number_ids
        numbers._sync_from_account(self.company_admin)
        self.mock_updated_numbers.clear()
        routed = self.company_admin.sudo().twilio_number_ids._route_sms_to_odoo()

        self.assertEqual(
            routed.mapped("twilio_sid"), ["PN11111111111111111111111111111111"]
        )
        self.assertTrue(routed.is_sms_routed)
        self.assertEqual(len(self.mock_updated_numbers), 1)
        sent = parse_qs(self.mock_updated_numbers[0])
        self.assertEqual(sent["SmsUrl"], [routed._get_inbound_sms_url()])
        self.assertEqual(sent["SmsMethod"], ["POST"])
