from urllib.parse import parse_qs

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger

from odoo.addons.integration_twilio.tests.common import (
    ONE_PIXEL_PNG,
    TWILIO_ACCOUNT_SID,
    MockSmsTwilio,
)


@tagged("post_install", "-at_install", "twilio")
class TestTwilioInboundSms(MockSmsTwilio, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sms_twilio(cls.company_admin)
        cls.number = cls.company_admin.twilio_number_ids.filtered(
            lambda number: number.number == "+32455998877"
        )
        cls.number.write(
            {
                "twilio_sid": "PN11111111111111111111111111111111",
                "user_ids": [Command.set(cls.basic_user.ids)],
            }
        )
        cls.path = f"/integration_twilio/sms/inbound/{cls.number.twilio_sid}"

    def _inbound(self, sender, body, sid="SM00000000000000000000000000000001", **extra):
        return {
            "AccountSid": TWILIO_ACCOUNT_SID,
            "MessageSid": sid,
            "From": sender,
            "To": self.number.number,
            "Body": body,
            "NumMedia": "0",
            **extra,
        }

    def _conversations(self, sender):
        return (
            self.env["discuss.channel"]
            .sudo()
            .search([("channel_type", "=", "sms"), ("sms_number", "=", sender)])
        )

    def test_unknown_sender_starts_a_conversation_without_a_contact(self):
        partners_before = self.env["res.partner"].search_count([])
        response = self.post_signed_twilio_callback(
            self.path, self._inbound("+12025550101", "Hola, ¿tienen fertilizante?")
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("<Response/>", response.text)
        channel = self._conversations("+12025550101")
        self.assertEqual(len(channel), 1)
        self.assertRecordValues(
            channel,
            [
                {
                    "name": "+12025550101",
                    "twilio_number_id": self.number.id,
                    "sms_partner_id": False,
                }
            ],
        )
        self.assertEqual(
            channel.channel_member_ids.partner_id, self.basic_user.partner_id
        )
        message = channel.message_ids
        self.assertEqual(len(message), 1)
        self.assertRecordValues(
            message,
            [{"message_type": "sms", "author_id": False, "email_from": "+12025550101"}],
        )
        self.assertIn("fertilizante", message.body)
        self.assertEqual(self.env["res.partner"].search_count([]), partners_before)

    def test_known_sender_is_the_author_and_redelivery_is_one_message(self):
        params = self._inbound(self.twilio_valid_phone_number, "Hello")
        self.post_signed_twilio_callback(self.path, params, idempotency_token="in-1")
        again = self.post_signed_twilio_callback(
            self.path, params, idempotency_token="in-1"
        )
        self.post_signed_twilio_callback(
            self.path,
            self._inbound(
                self.twilio_valid_phone_number,
                "Second",
                sid="SM00000000000000000000000000000002",
            ),
        )

        self.assertEqual(again.status_code, 200)
        channel = self._conversations(self.twilio_valid_phone_number)
        self.assertEqual(len(channel), 1)
        self.assertEqual(channel.sms_partner_id, self.valid_partner)
        self.assertEqual(
            channel.name, f"ValidPartner ({self.twilio_valid_phone_number})"
        )
        self.assertEqual(len(channel.message_ids), 2)
        self.assertEqual(channel.message_ids.author_id, self.valid_partner)

    @mute_logger(
        "odoo.addons.integration_twilio.models.integration_twilio_config",
        "odoo.addons.integration.models.mixin_inbound_gate",
    )
    def test_forged_signature_files_nothing(self):
        response = self.post_signed_twilio_callback(
            self.path,
            self._inbound("+12025550102", "forged"),
            auth_token="not-the-token",
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(self._conversations("+12025550102"))

    def test_unknown_number_is_not_found(self):
        response = self.post_signed_twilio_callback(
            "/integration_twilio/sms/inbound/PN99999999999999999999999999999999",
            self._inbound("+12025550103", "x"),
        )
        self.assertEqual(response.status_code, 404)

    def test_member_reply_is_sent_from_the_conversation_number(self):
        self.post_signed_twilio_callback(self.path, self._inbound("+15055550104", "Hi"))
        channel = self._conversations("+15055550104")
        self.mock_requests.clear()
        with self.mock_sms_twilio_gateway():
            channel.with_user(self.basic_user).message_post(
                body="We do, come by tomorrow",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )

        sent = [
            parse_qs(request.body)
            for request in self.mock_requests
            if request.url.endswith("/Messages.json")
        ]
        self.assertEqual(len(sent), 1)
        # a US recipient, but the conversation's Belgian number answers
        self.assertEqual(sent[0]["From"], ["+32455998877"])
        self.assertEqual(sent[0]["To"], ["+15055550104"])
        self.assertEqual(sent[0]["Body"], ["We do, come by tomorrow"])
        reply = channel.message_ids.filtered(
            lambda message: message.message_type == "comment"
        )
        self.assertEqual(reply.notification_ids.notification_type, "sms")

    def test_inbound_message_is_not_sent_back(self):
        self.mock_requests.clear()
        with self.mock_sms_twilio_gateway():
            self.post_signed_twilio_callback(
                self.path, self._inbound("+15055550105", "Hi")
            )
        self.assertFalse(
            [r for r in self.mock_requests if r.url.endswith("/Messages.json")]
        )

    def test_opt_out_keywords_reach_the_blacklist(self):
        sender = "+15055550106"
        self.post_signed_twilio_callback(
            self.path, self._inbound(sender, "STOP", OptOutType="STOP")
        )
        blacklist = self.env["phone.blacklist"].sudo().with_context(active_test=False)
        entry = blacklist.search([("number", "=", sender)])
        self.assertTrue(entry.active)
        self.post_signed_twilio_callback(
            self.path,
            self._inbound(
                sender,
                "START",
                sid="SM00000000000000000000000000000009",
                OptOutType="START",
            ),
        )
        self.assertFalse(entry.active)

    def test_media_is_attached(self):
        media_url = (
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}"
            "/Messages/MM00000000000000000000000000000001/Media/ME00000000000000000000000000000001"
        )
        self.post_signed_twilio_callback(
            self.path,
            self._inbound(
                "+15055550107",
                "",
                NumMedia="1",
                MediaUrl0=media_url,
                MediaContentType0="image/png",
            ),
        )
        attachment = self._conversations("+15055550107").message_ids.attachment_ids
        self.assertEqual(len(attachment), 1)
        self.assertEqual(attachment.mimetype, "image/png")
        self.assertEqual(attachment.datas.decode(), ONE_PIXEL_PNG)
