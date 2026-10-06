import hashlib
from urllib.parse import parse_qs, urljoin

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger

from odoo.addons.integration_twilio.hooks import _rehome_twilio_service, uninstall_hook
from odoo.addons.integration_twilio.tests.common import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    MockSmsTwilio,
)
from odoo.addons.integration_twilio.tools.twilio_signature import compute_signature
from odoo.addons.mail.tests.common import mail_new_test_user

EMPTY_BODY_HASH = hashlib.sha256(b"").hexdigest()


@tagged("post_install", "-at_install", "twilio")
class TestTwilioReviewWebhooks(MockSmsTwilio, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sms_twilio(cls.company_admin)
        cls.number = cls.company_admin.twilio_number_ids.filtered(
            lambda number: number.number == "+32455998877"
        )
        cls.number.twilio_sid = "PN11111111111111111111111111111111"
        cls.path = f"/integration_twilio/sms/inbound/{cls.number.twilio_sid}"

    def _inbound(self, sender, body, **extra):
        return {
            "AccountSid": TWILIO_ACCOUNT_SID,
            "MessageSid": "SM00000000000000000000000000000077",
            "From": sender,
            "To": self.number.number,
            "Body": body,
            "NumMedia": "0",
            **extra,
        }

    def _send_one_sms(self):
        composer = (
            self.env["wizard.sms.sms.send"]
            .with_context(active_model="res.partner", active_id=self.valid_partner)
            .create({"body": "Body msg"})
        )
        composer._action_send_sms()
        return self._new_sms[-1]

    def test_status_after_the_sms_was_vacuumed_reaches_its_tracker(self):
        with self.mock_sms_twilio_gateway():
            sms = self._send_one_sms()
            uuid, tracker = sms.uuid, sms.sms_tracker_id
            self.assertEqual(tracker.twilio_company_id, self.company_admin)
            sms.unlink()
            response = self.post_signed_twilio_callback(
                f"/integration_twilio/sms/status/{uuid}", self.webhook_ok_response
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tracker.mail_notification_id.notification_status, "sent")

    def test_the_gate_reads_and_hashes_the_body(self):
        self.post_signed_twilio_callback(self.path, self._inbound("+15055550201", "Hi"))
        self.env.flush_all()
        self.env.cr.precommit.run()
        row = (
            self.env["integration.exchange"]
            .sudo()
            .search(
                [
                    ("direction", "=", "inbound"),
                    ("event_type", "=", "twilio_sms_inbound"),
                ],
                order="id desc",
                limit=1,
            )
        )
        self.assertTrue(row)
        self.assertNotEqual(row.request_payload_hash, EMPTY_BODY_HASH)

    @mute_logger(
        "odoo.addons.integration_twilio.models.integration_twilio_config",
        "odoo.addons.integration.models.mixin_inbound_gate",
    )
    def test_refusals_name_no_company(self):
        response = self.url_open(
            self.path,
            self._inbound("+15055550202", "Hi"),
            headers={"X-Twilio-Signature": "forged"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(self.company_admin.name, response.text)

    @mute_logger(
        "odoo.addons.integration_twilio.models.integration_twilio_config",
        "odoo.addons.integration.models.mixin_inbound_gate",
    )
    def test_the_request_host_is_not_a_signed_url(self):
        params = self._inbound("+15055550203", "Hi")
        forged = compute_signature(
            TWILIO_AUTH_TOKEN, urljoin("http://evil.example", self.path), params.items()
        )
        response = self.url_open(
            self.path,
            params,
            headers={"X-Twilio-Signature": forged, "Host": "evil.example"},
        )
        self.assertEqual(response.status_code, 401)

    def test_a_status_sms_does_not_have_is_acknowledged(self):
        with self.mock_sms_twilio_gateway():
            sms = self._send_one_sms()
            response = self.post_signed_twilio_callback(
                f"/integration_twilio/sms/status/{sms.uuid}",
                {
                    **self.webhook_ok_response,
                    "MessageStatus": "read",
                    "SmsStatus": "read",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sms.sms_tracker_id.mail_notification_id.notification_status, "pending"
        )

    def test_malformed_media_count_still_files_the_message(self):
        response = self.post_signed_twilio_callback(
            self.path, self._inbound("+15055550204", "Hi", NumMedia="many")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            self.env["discuss.channel"]
            .sudo()
            .search([("sms_number", "=", "+15055550204")])
        )

    def test_stop_keyword_without_advanced_opt_out(self):
        sender = "+15055550205"
        blacklist = self.env["phone.blacklist"].sudo().with_context(active_test=False)
        self.post_signed_twilio_callback(
            self.path, self._inbound(sender, " stop "), idempotency_token="s-1"
        )
        self.assertTrue(blacklist.search([("number", "=", sender)]).active)
        self.post_signed_twilio_callback(
            self.path,
            self._inbound(
                sender, "START", MessageSid="SM00000000000000000000000000000078"
            ),
            idempotency_token="s-2",
        )
        self.assertFalse(blacklist.search([("number", "=", sender)]).active)

    @mute_logger("odoo.addons.integration.models.mixin_inbound_gate")
    def test_a_company_without_an_account_gets_no_receiver(self):
        other = self.env["res.company"].create({"name": "No Twilio Co"})
        sms = (
            self.env["sms.sms"]
            .sudo()
            .create(
                {"number": "+15055550206", "body": "x", "record_company_id": other.id}
            )
        )
        receivers = (
            self.env["integration.receiver"].sudo().with_context(active_test=False)
        )
        before = receivers.search_count([])
        response = self.post_signed_twilio_callback(
            f"/integration_twilio/sms/status/{sms.uuid}", self.webhook_ok_response
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(receivers.search_count([]), before)

    def test_a_number_nobody_answers_still_has_a_member(self):
        self.number.user_ids = [Command.clear()]
        self.post_signed_twilio_callback(self.path, self._inbound("+15055550207", "Hi"))
        channel = (
            self.env["discuss.channel"]
            .sudo()
            .search([("sms_number", "=", "+15055550207")])
        )
        self.assertEqual(
            channel.channel_member_ids.partner_id,
            self.env.ref("base.user_admin").partner_id,
        )


@tagged("post_install", "-at_install", "twilio")
class TestTwilioReviewAccount(MockSmsTwilio):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sms_twilio(cls.company_admin)
        cls.config = cls.company_admin.integration_twilio_config_id.sudo()

    def _send(self, number, error_type):
        with self.mock_sms_twilio_gateway(error_type=error_type):
            composer = self.env["wizard.sms.sms.send"].create(
                {"body": "x", "composition_mode": "numbers", "numbers": number}
            )
            composer._action_send_sms()
        return self._new_sms[-1]

    def test_a_recipient_who_replied_stop_is_blacklisted(self):
        sms = self._send("+15055550301", "twilio_opted_out")
        self.assertEqual(sms.failure_type, "sms_optout")
        self.assertTrue(
            self.env["phone.blacklist"].sudo().search([("number", "=", "+15055550301")])
        )

    def test_an_opted_out_partner_fails_on_the_chatter_too(self):
        with self.mock_sms_twilio_gateway(error_type="twilio_opted_out"):
            composer = (
                self.env["wizard.sms.sms.send"]
                .with_context(
                    active_model="res.partner", active_id=self.valid_partner.id
                )
                .create({"body": "x"})
            )
            message = composer._action_send_sms()
        self.assertEqual(message.notification_ids.failure_type, "sms_optout")

    def test_rate_limited_is_a_server_error_not_unknown(self):
        sms = self._send("+15055550302", "rate_limited")
        self.assertEqual(sms.failure_type, "sms_server")

    def test_sync_archives_a_vanished_number_a_conversation_names(self):
        numbers = self.company_admin.sudo().twilio_number_ids
        numbers._sync_from_account(self.company_admin)
        gone = numbers.search(
            [("twilio_sid", "=", "PN22222222222222222222222222222222")]
        )
        self.env["discuss.channel"].sudo().create(
            {
                "name": "x",
                "channel_type": "sms",
                "sms_number": "+15055550303",
                "twilio_number_id": gone.id,
            }
        )
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
        self.assertFalse(gone.active)

    def test_an_sms_application_overrides_the_routing(self):
        reported = [
            {**entry, "sms_application_sid": "AP1", "sms_url": ""}
            for entry in self.incoming_phone_numbers_json["incoming_phone_numbers"]
        ]
        self.patch(
            type(self),
            "incoming_phone_numbers_json",
            {"incoming_phone_numbers": reported, "next_page_uri": None},
        )
        numbers = self.company_admin.sudo().twilio_number_ids
        numbers._sync_from_account(self.company_admin)
        number = numbers.search(
            [("twilio_sid", "=", "PN11111111111111111111111111111111")]
        )
        self.assertFalse(number.is_sms_routed)
        self.mock_updated_numbers.clear()
        number._route_sms_to_odoo()
        sent = parse_qs(self.mock_updated_numbers[0], keep_blank_values=True)
        self.assertEqual(sent["SmsApplicationSid"], [""])
        self.assertEqual(number.twilio_sms_url, number._get_inbound_sms_url())

    def test_a_subaccount_has_no_balance_to_alert_on(self):
        self.patch(type(self), "balance_json", {"account_sid": TWILIO_ACCOUNT_SID})
        self.config.amount_twilio_balance_alert = 20
        self.config._refresh_account_state()
        self.assertFalse(self.config.twilio_currency_id)
        self.assertFalse(self.config.activity_ids)

    def test_install_adopts_the_service_integration_seeded(self):
        service = self.env.ref("integration_twilio.service_twilio")
        self.env.cr.execute(
            "UPDATE ir_model_data SET module = 'integration' "
            "WHERE module = 'integration_twilio' AND name = 'service_twilio'"
        )
        self.env.registry.clear_cache()
        _rehome_twilio_service(self.env.cr)
        self.env.registry.clear_cache()
        self.assertEqual(self.env.ref("integration_twilio.service_twilio"), service)

    def test_uninstall_takes_its_credentials_and_receivers(self):
        credential = self.config.credential_id
        with self.sync_env_with_side_cursors():
            self.env["integration.receiver"]._for_record(
                self.company_admin, "Status", "twilio_sms_status"
            )
        uninstall_hook(self.env)
        self.assertFalse(credential.exists())
        self.assertFalse(
            self.env["integration.receiver"]
            .sudo()
            .with_context(active_test=False)
            .search([("res_purpose", "=", "twilio_sms_status")])
        )


@tagged("post_install", "-at_install", "twilio")
class TestTwilioReviewConversations(MockSmsTwilio, HttpCase):
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
        cls.channel = cls.env["discuss.channel"]._get_sms_channel(
            cls.number, "+15055550401"
        )
        cls.other_user = mail_new_test_user(
            cls.env,
            company_id=cls.company_admin.id,
            groups="base.group_user",
            login="other_answerer",
        )

    def _sent_bodies(self):
        return [
            parse_qs(request.body)["Body"][0]
            for request in self.mock_requests
            if request.url.endswith("/Messages.json")
        ]

    def test_the_sms_tab_loads_with_discuss(self):
        self.authenticate("employee", "employee")
        data = self.call_jsonrpc(
            "/mail/data",
            {
                "fetch_params": [
                    [
                        "/mail/messaging_menu/initialize_counters",
                        {
                            "filter_id_by_tab_id_by_record_type": {
                                "discuss.channel": {"sms": None, "chat": None}
                            }
                        },
                    ],
                    [
                        "/mail/messaging_menu/discuss.channel/load_more",
                        {"tab_id": "sms", "limit": 10, "filter_ids": ["sms_unread"]},
                        "sms",
                    ],
                ]
            },
        )
        counters = {tab["id"]: tab for tab in data["MessagingMenuTab"]}
        self.assertIn("sms", counters)

    def test_notes_and_odoobot_posts_stay_in_odoo(self):
        self.mock_requests.clear()
        with self.mock_sms_twilio_gateway():
            self.channel.with_user(self.basic_user).message_post(
                body="internal remark",
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
            self.channel.message_post(
                body="bot says hi",
                author_id=self.env.ref("base.partner_root").id,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            self.channel.with_user(self.basic_user).message_post(
                body="to the customer",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        self.assertEqual(self._sent_bodies(), ["to the customer"])

    def test_a_blacklisted_person_is_not_written_to(self):
        self.env["phone.blacklist"].sudo()._add(["+15055550401"])
        self.mock_requests.clear()
        with self.mock_sms_twilio_gateway():
            message = self.channel.with_user(self.basic_user).message_post(
                body="hello?", message_type="comment", subtype_xmlid="mail.mt_comment"
            )
        self.assertFalse(self._sent_bodies())
        self.assertEqual(message.notification_ids.failure_type, "sms_blacklist")

    def test_a_reply_without_text_is_refused(self):
        with self.assertRaises(UserError):
            self.channel.with_user(self.basic_user).message_post(
                body="",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                attachments=[("photo.png", b"x")],
            )

    def test_no_guest_or_portal_user_joins(self):
        portal = mail_new_test_user(
            self.env, groups="base.group_portal", login="sms_portal"
        )
        guest = self.env["mail.guest"].create({"name": "Visitor"})
        with self.assertRaises(UserError):
            self.channel._add_members(partners=portal.partner_id)
        with self.assertRaises(UserError):
            self.channel._add_members(guests=guest)

    def test_members_follow_the_number(self):
        self.number.user_ids = [Command.set(self.other_user.ids)]
        self.assertEqual(
            self.channel.channel_member_ids.partner_id, self.other_user.partner_id
        )
        self.number.user_ids = [Command.link(self.basic_user.id)]
        self.assertEqual(
            self.channel.channel_member_ids.partner_id,
            self.other_user.partner_id | self.basic_user.partner_id,
        )

    def test_the_last_member_stays(self):
        self.channel.with_user(self.basic_user).action_unfollow()
        self.assertIn(
            self.basic_user.partner_id, self.channel.channel_member_ids.partner_id
        )

    def test_a_number_is_answered_by_its_company_only(self):
        other = self.env["res.company"].create({"name": "Elsewhere"})
        stranger = mail_new_test_user(
            self.env, company_id=other.id, groups="base.group_user", login="stranger"
        )
        with self.assertRaises(ValidationError):
            self.number.user_ids = [Command.link(stranger.id)]
