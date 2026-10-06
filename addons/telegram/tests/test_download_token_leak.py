import logging
from unittest.mock import MagicMock, patch

import requests

from .common import TelegramBotTestCase
from odoo.addons.integration.tools.exceptions import CommError
from odoo.addons.telegram.tools.logging_filter import TelegramTokenFilter
from odoo.addons.telegram.tools.telegram_client import TelegramClient

_LOGGER = "odoo.addons.telegram.tools.telegram_client"
_TRANSPORT_LOGGER = "odoo.addons.integration.tools.api_client"
_MODEL_LOGGER = "odoo.addons.telegram.models.telegram_bot"


class TestDownloadTokenLeak(TelegramBotTestCase):
    TOKEN = "999888777:SECRETshouldneverbelogged"

    def _leaky_error(self):
        return requests.ConnectionError(
            "HTTPSConnectionPool: failed for url "
            f"https://api.telegram.org/file/bot{self.TOKEN}/doc.jpg"
        )

    def test_download_error_does_not_log_token(self):
        client = TelegramClient(self.env, self.TOKEN)

        with patch.object(requests.Session, "request", side_effect=self._leaky_error()):
            with self.assertLogs(_LOGGER, level="ERROR") as captured:
                with self.assertRaises(CommError):
                    client.download_file("doc.jpg")

        log_text = "\n".join(captured.output)
        self.assertNotIn(
            self.TOKEN, log_text, "bot token must never appear in logs (TG-19)"
        )
        self.assertIn("999888777", log_text, "the bot must still be identifiable")

    def test_the_stored_audit_row_does_not_carry_the_token_either(self):
        client = TelegramClient(self.env, self.TOKEN)

        with patch.object(requests.Session, "request", side_effect=self._leaky_error()):
            with self.assertLogs(_TRANSPORT_LOGGER, level="ERROR"):
                with self.assertRaises(CommError):
                    client.download_file("doc.jpg")

        self.env.cr.precommit.run()
        row = self.env["integration.exchange"].search([], order="id desc", limit=1)
        self.assertTrue(row, "the failed exchange must still be recorded")
        self.assertNotIn(self.TOKEN, row.error_message or "")
        self.assertNotIn(self.TOKEN, row.request_url or "")

    def test_the_exception_reaching_the_caller_is_masked(self):
        client = TelegramClient(self.env, self.TOKEN)

        with patch.object(requests.Session, "request", side_effect=self._leaky_error()):
            with self.assertLogs(_LOGGER, level="ERROR"):
                with self.assertRaises(CommError) as caught:
                    client.download_file("doc.jpg")

        self.assertNotIn(self.TOKEN, str(caught.exception))


class TestTokenShapesTheOldPairMissed(TelegramBotTestCase):
    def _mask(self, text):
        from odoo.libs import redact

        return redact.mask_text(text)

    def test_the_filter_masks_an_eight_digit_bot_id(self):
        secret = "AAHsecretTOKENvalue1234567890abcdef"
        record = logging.LogRecord(
            "werkzeug",
            logging.INFO,
            __file__,
            1,
            f"GET /bot12345678:{secret}/getUpdates",
            None,
            None,
        )
        TelegramTokenFilter().filter(record)
        self.assertNotIn(secret, record.msg)
        self.assertIn("12345678", record.msg, "the bot must stay identifiable")

    def test_a_token_quoted_without_the_bot_prefix_is_masked(self):
        secret = "AAHsecretTOKENvalue1234567890abcde"
        masked = self._mask(f"Unauthorized for 123456789:{secret} — check the token")
        self.assertNotIn(secret, masked)

    def test_the_registration_actually_happened(self):
        from odoo.libs import redact

        self.assertTrue(
            redact.REGISTERED_PATTERNS,
            "telegram_bot must register its token shape with the transport",
        )


class TestSendMessageTokenLeak(TelegramBotTestCase):
    def _leaky_response(self):
        response = MagicMock()
        response.status_code = 400
        response.headers = {}
        response.json.return_value = {
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: unsupported parse_mode",
        }
        response.text = '{"ok": false}'
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "400 Client Error: Bad Request for url: "
            f"https://api.telegram.org/bot{self.TEST_BOT_TOKEN}/sendMessage",
            response=response,
        )
        return response

    def test_a_failed_send_does_not_log_the_token(self):
        secret = self.TEST_BOT_TOKEN.split(":", 1)[1]

        with patch.object(
            requests.Session, "request", return_value=self._leaky_response()
        ):
            with self.assertLogs(_MODEL_LOGGER, level="ERROR") as captured:
                self.test_bot.send_message(self.test_chat.chat_id, "hola")

        log_text = "\n".join(captured.output)
        self.assertNotIn(
            secret, log_text, "bot token must never appear in logs (TG-19)"
        )
        self.assertIn("123456789", log_text, "the bot must still be identifiable")

    def test_the_failure_is_still_reported(self):
        with patch.object(
            requests.Session, "request", return_value=self._leaky_response()
        ):
            with self.assertLogs(_MODEL_LOGGER, level="ERROR") as captured:
                result = self.test_bot.send_message(self.test_chat.chat_id, "hola")

        self.assertFalse(result, "a failed send must not report success")
        self.assertIn("unsupported parse_mode", "\n".join(captured.output))
