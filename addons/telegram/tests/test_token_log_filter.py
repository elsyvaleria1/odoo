import logging

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.telegram.tools.logging_filter import (
    TelegramTokenFilter,
    install_token_filter,
)

_TOKEN = "123456789:AAEwYtR9xQ_kLmN0pQrStUvWxYz12345678"


@tagged("post_install", "-at_install")
class TestTokenLogFilter(TransactionCase):
    def _record(self, msg, args=None):
        return logging.LogRecord(
            name="werkzeug",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=msg,
            args=args,
            exc_info=None,
        )

    def test_a_token_in_the_message_is_masked(self):
        record = self._record(f'"POST /telegram/webhook/{_TOKEN} HTTP/1.1" 200')
        TelegramTokenFilter().filter(record)
        self.assertNotIn(
            _TOKEN, record.msg, "the whole token must not survive in the message"
        )
        self.assertIn("123456789:***...5678", record.msg)

    def test_a_token_in_the_args_is_masked(self):
        record = self._record("%s", (f"/telegram/webhook/{_TOKEN}",))
        TelegramTokenFilter().filter(record)
        self.assertNotIn(_TOKEN, record.args[0])
        self.assertIn("123456789:***...5678", record.args[0])

    def test_the_filter_keeps_the_record(self):
        self.assertTrue(TelegramTokenFilter().filter(self._record("nothing secret")))

    def test_text_without_a_token_is_untouched(self):
        line = '"GET /web/login HTTP/1.1" 200 -'
        record = self._record(line)
        TelegramTokenFilter().filter(record)
        self.assertEqual(record.msg, line)

    def test_it_lands_on_every_access_logger_and_installing_twice_adds_one(self):
        install_token_filter()
        install_token_filter()
        for name in ("odoo.service.http.access", "werkzeug"):
            installed = [
                f
                for f in logging.getLogger(name).filters
                if isinstance(f, TelegramTokenFilter)
            ]
            self.assertEqual(
                len(installed), 1, f"{name}: install_token_filter must stay idempotent"
            )


@tagged("post_install", "-at_install")
class TestWebhookAccessLine(HttpCase):
    @mute_logger("odoo.addons.telegram.controllers.telegram_controller")
    def test_a_webhook_request_logs_its_access_line_without_the_token(self):
        with self.assertLogs(level="INFO") as capture:
            response = self.url_open(
                f"/telegram/webhook/{_TOKEN}",
                data="{}",
                headers={"Content-Type": "application/json"},
            )
        self.assertEqual(response.status_code, 200)
        access = [line for line in capture.output if "/telegram/webhook/" in line]
        self.assertTrue(access, "the webhook request must still be logged")
        self.assertNotIn(_TOKEN, "\n".join(capture.output))
        self.assertIn("123456789:***...5678", "\n".join(access))
