from unittest.mock import patch

from .common import TelegramBotTestCase
from odoo.addons.telegram.tools.telegram_client import TelegramClient


class TestSendMessagePayload(TelegramBotTestCase):
    def _captured_payload(self, **kwargs):
        client = TelegramClient(self.env, self.TEST_BOT_TOKEN)
        response = {"body": {"ok": True, "result": {"message_id": 1}}}

        with patch.object(client._client, "post", return_value=response) as post:
            client.send_message("42", "hola", **kwargs)

        return post.call_args.kwargs["json"]

    def test_a_none_parse_mode_is_omitted_rather_than_sent_as_null(self):
        payload = self._captured_payload(parse_mode=None)
        self.assertNotIn(
            "parse_mode",
            payload,
            "Telegram rejects a null parse_mode with 400 unsupported parse_mode; "
            "absent is how the Bot API spells plain text",
        )

    def test_the_default_parse_mode_still_reaches_telegram(self):
        payload = self._captured_payload()
        self.assertEqual(payload["parse_mode"], "HTML")

    def test_an_explicit_parse_mode_still_reaches_telegram(self):
        payload = self._captured_payload(parse_mode="MarkdownV2")
        self.assertEqual(payload["parse_mode"], "MarkdownV2")
