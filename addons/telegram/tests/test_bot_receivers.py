import time
from unittest.mock import MagicMock, patch

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests import tagged

from .common import TelegramBotHttpCase, TelegramBotTestCase
from .test_web_app_init_data import signed_init_data


@tagged("post_install", "-at_install")
class TestBotReceivers(TelegramBotTestCase):
    def _exchanges(self, receiver):
        self.env.cr.precommit.run()
        return self.env["integration.exchange"].search(
            [("channel_id", "=", f"integration.receiver,{receiver.id}")]
        )

    def _refusals(self, receiver):
        return self.env["integration.exchange"].search(
            [
                ("state", "=", "refused"),
                ("channel_id", "=", f"{receiver._name},{receiver.id}"),
            ]
        )

    def test_a_bot_gets_a_webhook_and_a_mini_app_receiver(self):
        webhook = self.test_bot.webhook_receiver_id
        mini_app = self.test_bot.mini_app_receiver_id

        self.assertEqual(webhook.auth_type, "telegram_secret_token")
        self.assertEqual(mini_app.auth_type, "telegram_init_data")
        self.assertEqual((webhook | mini_app).mapped("res_id"), [self.test_bot.id] * 2)
        self.assertTrue(webhook.rate_limit_enabled)

    def test_renaming_the_bot_renames_its_receivers(self):
        self.test_bot.name = "Renamed bot"

        self.assertEqual(self.test_bot.webhook_receiver_id.name, "Renamed bot webhook")

    def test_the_receivers_speak_for_the_bot_company(self):
        receivers = (
            self.test_bot.webhook_receiver_id | self.test_bot.mini_app_receiver_id
        )
        self.assertEqual(receivers.company_id, self.test_bot.company_id)

        self.test_bot.company_id = self.env["res.company"].create({"name": "Xiuman"})

        self.assertEqual(receivers.company_id, self.test_bot.company_id)

    def test_a_forged_update_is_refused_and_recorded(self):
        self.test_bot._update_webhook_secret("update-secret")
        receiver = self.test_bot.webhook_receiver_id

        allowed, status, _reason = receiver._check_inbound_request(
            {"X-Telegram-Bot-Api-Secret-Token": "forged"},
            body=b'{"message": {}}',
            remote_addr="149.154.167.220",
        )

        self.assertFalse(allowed)
        self.assertEqual(status, 401)
        self.assertEqual(
            self._refusals(receiver).mapped("refusal_reason"), ["authentication_failed"]
        )
        self.assertFalse(
            self._exchanges(receiver).filtered(lambda row: row.state != "refused"),
            "the refusal is the only row",
        )

    def test_a_bot_whose_webhook_refused_a_call_can_be_deleted(self):
        self.test_bot._update_webhook_secret("update-secret")
        receiver = self.test_bot.webhook_receiver_id
        receiver._check_inbound_request(
            {"X-Telegram-Bot-Api-Secret-Token": "forged"},
            body=b'{"message": {}}',
            remote_addr="149.154.167.220",
        )
        refusal = self._refusals(receiver)

        self.test_bot.unlink()

        self.assertFalse(receiver.exists())
        self.assertTrue(refusal.exists(), "the retention sweep removes it")

    def _mini_app_resolution(self, **params):
        mocked = MagicMock()
        mocked.get_http_params.return_value = params
        mocked.httprequest.mimetype = "application/x-www-form-urlencoded"
        with patch("odoo.addons.telegram.models.telegram_bot_receiver.request", mocked):
            return self.env["telegram.bot"]._receiver_for_mini_app(
                bot_id=self.test_bot.id
            )

    def test_mini_app_calls_are_proven_by_signed_init_data(self):
        fields_ = {"auth_date": str(int(time.time())), "user": json_dumps({"id": 7})}
        signed = signed_init_data(self.TEST_BOT_TOKEN, fields_)

        resolution = self._mini_app_resolution(init_data=signed)
        self.assertEqual(resolution.subject, self.test_bot)
        self.assertEqual(resolution.gate, self.test_bot.mini_app_receiver_id)
        self.assertEqual(resolution.extra["telegram_user_id"], "7")
        self.assertTrue(resolution.verify({}, b""))

        forged = self._mini_app_resolution(init_data=signed + "x")
        self.assertIsNone(forged.extra["telegram_user_id"])
        self.assertFalse(forged.verify({}, b""))

    def test_a_mini_app_session_is_the_bot_s_own_and_names_its_user(self):
        session = self.test_bot._mint_mini_app_session("7")

        resolution = self._mini_app_resolution(s=session)
        self.assertEqual(resolution.extra["telegram_user_id"], "7")
        self.assertTrue(resolution.verify({}, b""))

        self.assertFalse(self._mini_app_resolution(s=session + "x").verify({}, b""))

    def test_an_unknown_bot_is_nobody_s(self):
        resolution = self._mini_app_resolution(init_data="whatever")
        self.assertEqual(resolution.subject, self.test_bot)
        mocked = MagicMock()
        mocked.get_http_params.return_value = {}
        mocked.httprequest.mimetype = "application/x-www-form-urlencoded"
        with patch("odoo.addons.telegram.models.telegram_bot_receiver.request", mocked):
            unknown = self.env["telegram.bot"]._receiver_for_mini_app(bot_id=0)
        self.assertFalse(unknown.subject)
        self.assertEqual(unknown.claimed, "bot 0")

    def test_the_upgrade_gives_existing_bots_their_receivers(self):
        receivers = (
            self.test_bot.webhook_receiver_id | self.test_bot.mini_app_receiver_id
        )
        self.test_bot.write(
            {"webhook_receiver_id": False, "mini_app_receiver_id": False}
        )
        receivers.unlink()

        self.env["telegram.bot"].search([])._create_missing_receivers()

        self.assertTrue(self.test_bot.webhook_receiver_id)
        self.assertTrue(self.test_bot.mini_app_receiver_id)

    def test_deleting_the_bot_deletes_its_webhook_secret_credential(self):
        self.test_bot._update_webhook_secret("secret_to_clean_up")
        receiver = self.test_bot.sudo().webhook_receiver_id
        secret_credential = receiver.credential_id
        token_credential = self.test_bot.credential_id
        self.assertTrue(secret_credential)

        self.test_bot.sudo().unlink()

        self.assertFalse(receiver.exists())
        self.assertFalse(
            secret_credential.exists(),
            "the webhook secret used to outlive its bot in the vault",
        )
        self.assertTrue(
            token_credential.exists(),
            "the bot-token credential belongs to the user and must stay",
        )


@tagged("post_install", "-at_install")
class TestBotReceiversOverHttp(TelegramBotHttpCase):
    def test_a_handled_update_is_recorded_without_its_content(self):
        self.test_bot._update_webhook_secret("update-secret")
        message = self.mock_telegram_message(chat_id=self.test_chat.chat_id, text="hi")
        self.env.flush_all()

        with patch.object(type(self.env["telegram.router"]), "_handle_update"):
            self.url_open(
                f"/telegram/webhook/{self.TEST_BOT_TOKEN}",
                data=json_dumps_bytes({"message": message}),
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-Telegram-Bot-Api-Secret-Token": "update-secret",
                },
            )

        receiver = self.test_bot.webhook_receiver_id
        call = self.env["integration.exchange"].search(
            [("channel_id", "=", f"integration.receiver,{receiver.id}")]
        )
        self.assertEqual(len(call), 1)
        self.assertEqual((call.event_type, call.state), ("message", "success"))
        self.assertFalse(call.request_payload, "chat content stays out of the log")
        self.assertTrue(call.request_payload_hash, "the body is still hashed")
