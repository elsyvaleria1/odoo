from types import SimpleNamespace
from unittest.mock import patch

import psycopg

from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests import tagged
from odoo.tests.common import BaseCase
from odoo.tools import mute_logger

from .common import TelegramBotHttpCase, TelegramBotTestCase
from odoo.addons.telegram.tools import dispatch
from odoo.addons.telegram.tools.dispatch import log_command_execution


def _conflict(self, bot, chat, args, partner=False, internal_user=False):
    raise psycopg.errors.SerializationFailure(
        "could not serialize access due to concurrent update"
    )


class TestSendTrackedSeparatesDatabaseErrors(TelegramBotTestCase):
    def test_a_database_error_is_not_recorded_as_a_delivery_failure(self):
        def call():
            raise psycopg.errors.SerializationFailure(
                "could not serialize access due to concurrent update"
            )

        with self.assertRaises(psycopg.errors.SerializationFailure):
            self.test_bot._send_tracked(
                self.test_chat.chat_id,
                "sendMessage",
                "text",
                {"text": "hola"},
                call,
            )

    def test_an_api_error_is_still_recorded_on_the_outbound_row(self):
        def call():
            raise ValueError("telegram is unreachable")

        self.assertFalse(
            self.test_bot._send_tracked(
                self.test_chat.chat_id,
                "sendMessage",
                "text",
                {"text": "hola"},
                call,
            )
        )
        message = self.env["telegram.message"].search(
            [("chat_id", "=", self.test_chat.id), ("message_type", "=", "outbound")],
            limit=1,
        )
        self.assertEqual(message.state, "error")
        self.assertIn("unreachable", message.error_message)


class TestDispatchLetsConcurrencyRetry(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]
        conflict = self.extra_command("/conflict", _conflict, starts_flow=True)
        conflict.__enter__()
        self.addCleanup(conflict.__exit__, None, None, None)
        self.test_bot.command_ids = [
            (4, self.env["telegram.command"]._for_name("/conflict").id)
        ]

    def test_a_conflicting_handler_is_not_reported_to_the_user(self):
        response = self.mock_telegram_response(success=True, result={"message_id": 1})

        with self.mock_api_gateway_post(response) as mock_post:
            with self.assertRaises(psycopg.errors.SerializationFailure):
                self.controller._dispatch_command(
                    self.test_bot,
                    self.test_chat,
                    "/conflict",
                    [],
                    self.test_partner,
                    internal_user=False,
                )

        self.assertFalse(
            mock_post.called,
            "a retryable conflict is not the user's fault: notifying them here "
            "writes on a transaction Postgres may already have aborted",
        )
        self.test_chat.invalidate_recordset()
        self.assertEqual(
            self.test_chat.failed_command_count,
            0,
            "the failure counter is for the user's mistakes, not for concurrency",
        )


@tagged("post_install", "-at_install")
class TestWebhookLetsConcurrencyRetry(TelegramBotHttpCase):
    def test_a_concurrency_conflict_is_retried_and_never_answered_with_ok(self):
        data = {"message": self.mock_telegram_message(chat_id=self.test_chat.chat_id)}
        conflict = psycopg.errors.SerializationFailure(
            "could not serialize access due to concurrent update"
        )

        self.test_bot._update_webhook_secret("conflict_secret_1")
        self.env.flush_all()

        with (
            patch.object(
                type(self.env["telegram.router"]),
                "_handle_update",
                side_effect=conflict,
            ),
            mute_logger("odoo.http.application", "odoo.http._serve"),
        ):
            response = self.url_open(
                f"/telegram/webhook/{self.TEST_BOT_TOKEN}",
                data=json_dumps_bytes(data),
                headers={
                    "Content-Type": "application/json",
                    "X-Telegram-Bot-Api-Secret-Token": "conflict_secret_1",
                },
            )

        self.assertEqual(response.status_code, 500, "Telegram redelivers on this")


class TestCommandLogLetsConcurrencyRetry(BaseCase):
    """No database: only what `log_command_execution` writes to the log."""

    def _decorated(self, error):
        @log_command_execution
        def _handle_check_in_command(
            slf, bot, chat, args, partner=False, internal_user=False
        ):
            raise error

        return _handle_check_in_command

    def _run(self, error):
        chat = SimpleNamespace(id=1)
        with patch.object(dispatch, "_logger") as logger:
            with self.assertRaises(type(error)):
                self._decorated(error)(None, None, chat, [])
        return logger

    def test_a_concurrency_conflict_is_not_logged_as_a_failure(self):
        logger = self._run(
            psycopg.errors.SerializationFailure(
                "could not serialize access due to concurrent update"
            )
        )

        self.assertFalse(
            logger.exception.called,
            "the retry loop replays the command and it succeeds: a traceback "
            "here reports a working command as broken",
        )
        self.assertTrue(
            any(
                "concurrency conflict" in call.args[0]
                for call in logger.info.call_args_list
            )
        )

    def test_a_real_failure_is_still_logged_with_its_traceback(self):
        logger = self._run(ValueError("telegram is unreachable"))

        self.assertTrue(logger.exception.called)
