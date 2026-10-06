from unittest.mock import patch

import requests

from odoo.exceptions import ValidationError
from odoo.libs.guarded_http import GuardedSession
from odoo.libs.json import loads as json_loads

from .common import TelegramBotTestCase
from odoo.addons.telegram.tools.telegram_client import TelegramClient


class TestWebhookSecretProvisioning(TelegramBotTestCase):
    def _new_bot(self, **vals):
        credential = self._make_bot_credential(
            "Provisioning credential", "987654321:ZYX-provisioning_token"
        )
        return self.env["telegram.bot"].create(
            {"name": "Provisioned bot", "credential_id": credential.id, **vals}
        )

    def test_a_new_bot_gets_a_webhook_secret(self):
        bot = self._new_bot()

        self.assertGreaterEqual(len(bot._webhook_secret().reveal()), 32)

    def test_the_secret_lives_in_the_receivers_credential(self):
        bot = self._new_bot()
        credential = bot.webhook_receiver_id.credential_id

        self.assertTrue(credential)
        self.assertNotIn("webhook_secret", bot._fields)
        self.assertEqual(
            credential._use_secret("telegram_bot:webhook_secret"),
            bot._webhook_secret(),
        )

    def test_a_chosen_secret_is_kept(self):
        bot = self._new_bot()
        bot._update_webhook_secret("chosen_secret-1")

        self.assertEqual(bot._webhook_secret().reveal(), "chosen_secret-1")

    def test_a_secret_telegram_would_refuse_is_refused(self):
        bot = self._new_bot()
        for bad in ("has space", "x" * 257, "slash/"):
            with self.subTest(secret=bad), self.assertRaises(ValidationError):
                bot._update_webhook_secret(bad)

    def test_registering_sends_the_secret_with_the_webhook_url(self):
        bot = self._new_bot()
        response = {"body": {"ok": True, "result": True}}

        with patch.object(
            TelegramClient, "_post", return_value=response["body"]
        ) as post:
            bot.action_register_webhook()

        calls = dict(call.args for call in post.call_args_list)
        self.assertEqual(list(calls), ["setWebhook", "getMe"])
        payload = calls["setWebhook"]
        self.assertEqual(payload["secret_token"], bot._webhook_secret())
        # addressed by the token hash: the token never travels in a URL
        self.assertTrue(payload["url"].endswith(f"/telegram/webhook/{bot.token_hash}"))
        self.assertNotIn("ZYX-provisioning_token", payload["url"])

    def test_registering_a_secretless_bot_provisions_a_secret_first(self):
        bot = self._new_bot()
        bot._update_webhook_secret(False)
        self.assertFalse(bot._webhook_secret())

        with patch.object(TelegramClient, "_post", return_value={"ok": True}) as post:
            bot.action_register_webhook()

        self.assertTrue(bot._webhook_secret())
        calls = dict(call.args for call in post.call_args_list)
        self.assertEqual(calls["setWebhook"]["secret_token"], bot._webhook_secret())

    def test_telegram_receives_the_secret_in_clear(self):
        bot = self._new_bot()
        sent = []

        def send(session, prepared, **kwargs):
            sent.append(prepared)
            response = requests.Response()
            response.status_code = 200
            response._content = b'{"ok": true, "result": true}'
            response.headers["Content-Type"] = "application/json"
            response.request = prepared
            response.url = prepared.url
            return response

        with patch.object(GuardedSession, "send", send):
            bot._get_telegram_client().set_webhook(
                "https://example.com/hook", bot._webhook_secret()
            )

        self.assertEqual(
            json_loads(sent[0].body)["secret_token"], bot._webhook_secret().reveal()
        )
