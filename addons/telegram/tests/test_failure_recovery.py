from unittest.mock import patch

from .common import TelegramBotTestCase


def _boom(self, bot, chat, args, partner=False, internal_user=False):
    chat._flow_start("telegram.handler.base", "half-done")
    raise ValueError("handler exploded after a partial write")


class TestHandlerFailureRecovery(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]
        boom = self.extra_command("/boom", _boom, starts_flow=True)
        boom.__enter__()
        self.addCleanup(boom.__exit__, None, None, None)
        self.test_bot.command_ids = [
            (4, self.env["telegram.command"]._for_name("/boom").id)
        ]
        self.response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

    def _dispatch_boom(self):
        with self.mock_api_gateway_post(self.response) as mock_post:
            self.controller._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/boom",
                [],
                self.test_partner,
                internal_user=False,
            )
        return mock_post

    def test_a_crashing_handler_leaves_no_half_finished_flow(self):
        self._dispatch_boom()

        self.test_chat.invalidate_recordset()
        self.assertFalse(
            self.test_chat.flow_owner,
            "without the savepoint the chat stayed in its flow and the flow guard "
            "refused every later command until the flow expired",
        )
        self.assertFalse(self.test_chat.flow_data)

    def test_the_user_is_told_and_can_start_over(self):
        mock_post = self._dispatch_boom()
        text = mock_post.call_args.kwargs["json"]["text"]
        self.assertIn("error", text.lower())

        self.test_chat.invalidate_recordset()
        self.assertIsNone(
            self.controller._flow_owner(self.test_chat),
            "the next command must not be refused as 'already in progress'",
        )

    def test_the_failure_counter_survives_the_rollback(self):
        self._dispatch_boom()
        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.failed_command_count, 1)

    def test_three_failures_send_the_help_hint_and_reset(self):
        for _ in range(3):
            self._dispatch_boom()

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.failed_command_count, 0)

    def test_increment_needs_a_single_chat(self):
        with self.assertRaises(ValueError):
            (self.test_chat + self.unlinked_chat)._increment_failed_state("boom")


class TestRateLimitNotice(TelegramBotTestCase):
    def test_the_throttle_notice_is_not_sent_once_per_refused_message(self):
        controller = self.env["telegram.router"]
        response = self.mock_telegram_response(success=True, result={"message_id": 1})

        with (
            self.mock_api_gateway_post(response) as mock_post,
            self.mock_rate_limiter(is_allowed=False),
        ):
            for index in range(5):
                controller._dispatch_message(
                    self.test_bot,
                    self.mock_telegram_message(
                        chat_id=self.test_chat.chat_id,
                        text="spam",
                        message_id=8000 + index,
                    ),
                )

        self.assertEqual(
            mock_post.call_count,
            1,
            "replying to every throttled message makes the bot amplify the flood",
        )


class TestCallbackQueryThrottling(TelegramBotTestCase):
    def test_button_presses_are_rate_limited_too(self):
        controller = self.env["telegram.router"]
        response = self.mock_telegram_response(success=True, result={"message_id": 1})

        with (
            patch.object(
                type(self.test_chat), "_consume_rate_limit", return_value=False
            ) as limiter,
            self.mock_api_gateway_post(response),
        ):
            controller._dispatch_callback_query(
                self.test_bot,
                self.mock_telegram_callback_query(chat_id=self.test_chat.chat_id),
            )

        self.assertTrue(
            limiter.called,
            "callback queries reach the same handlers and used to skip the limiter",
        )
