from unittest.mock import patch

import psycopg

from odoo.exceptions import ValidationError

from .common import TelegramBotTestCase
from odoo.addons.telegram.models import telegram_chat as chat_module


class TestRateLimitingConfiguration(TelegramBotTestCase):
    def test_rate_limit_default_values(self):
        chat = self.env["telegram.chat"].create(
            {
                "chat_id": "55555",
                "bot_id": self.test_bot.id,
            }
        )

        self.assertTrue(chat.rate_limit_enabled)
        self.assertEqual(chat.rate_limit_requests, 20)
        self.assertEqual(chat.rate_limit_period, "minute")

    def test_rate_limit_requests_positive_constraint(self):
        with self.assertRaises(ValidationError):
            self.env["telegram.chat"].create(
                {
                    "chat_id": "44444",
                    "bot_id": self.test_bot.id,
                    "rate_limit_enabled": True,
                    "rate_limit_requests": 0,
                }
            )

    def test_rate_limit_requests_negative_constraint(self):
        with self.assertRaises(ValidationError):
            self.env["telegram.chat"].create(
                {
                    "chat_id": "44445",
                    "bot_id": self.test_bot.id,
                    "rate_limit_enabled": True,
                    "rate_limit_requests": -5,
                }
            )

    def test_enabling_the_limit_over_a_zero_budget_is_caught(self):
        chat = self.env["telegram.chat"].create(
            {
                "chat_id": "44446",
                "bot_id": self.test_bot.id,
                "rate_limit_enabled": False,
                "rate_limit_requests": 0,
            }
        )

        with self.assertRaises(ValidationError):
            chat.write({"rate_limit_enabled": True})
            chat.flush_recordset()


class TestRateLimitingToggle(TelegramBotTestCase):
    def test_rate_limit_disabled_always_allows(self):
        chat = self.env["telegram.chat"].create(
            {
                "chat_id": "44444",
                "bot_id": self.test_bot.id,
                "rate_limit_enabled": False,
            }
        )

        is_allowed = chat._consume_rate_limit()

        self.assertTrue(is_allowed)

    def test_rate_limit_enabled_checks_limiter(self):
        self.test_chat.write(
            {
                "rate_limit_enabled": True,
                "rate_limit_requests": 20,
            }
        )

        with self.mock_rate_limiter(is_allowed=True):
            is_allowed = self.test_chat._consume_rate_limit()

            self.assertTrue(is_allowed)
        self.env["telegram.chat"]._flush_activity()
        self.assertTrue(self.test_chat.last_message_time)


class TestRateLimitingBehavior(TelegramBotTestCase):
    def test_rate_limit_within_limit(self):
        self.test_chat.write(
            {
                "rate_limit_enabled": True,
                "rate_limit_requests": 20,
            }
        )

        with self.mock_rate_limiter(is_allowed=True):
            is_allowed = self.test_chat._consume_rate_limit()

            self.assertTrue(is_allowed)

    def test_rate_limit_exceeded(self):
        self.test_chat.write(
            {
                "rate_limit_enabled": True,
                "rate_limit_requests": 5,
            }
        )

        with self.mock_rate_limiter(is_allowed=False):
            is_allowed = self.test_chat._consume_rate_limit()

            self.assertFalse(is_allowed)

    def test_activity_stamp_lands_at_commit_not_during_the_request(self):
        self.test_chat.write(
            {
                "rate_limit_enabled": True,
                "last_message_time": False,
            }
        )
        self.env.cr.flush()

        with self.mock_rate_limiter(is_allowed=True):
            self.test_chat._consume_rate_limit()

        self.env.cr.flush()
        self.assertFalse(
            self.test_chat.last_message_time,
            "stamping it up front locks the chat row for the whole request, "
            "which is what turns concurrent updates into serialisation failures; "
            "a flush must not be enough to trigger it either, because every "
            "cr.savepoint() flushes",
        )

        self.env["telegram.chat"]._flush_activity()
        self.assertTrue(self.test_chat.last_message_time)

    def test_rate_limit_does_not_update_time_when_denied(self):
        self.test_chat.write({"rate_limit_enabled": True})
        self.env.cr.flush()
        old_time = self.test_chat.last_message_time

        with self.mock_rate_limiter(is_allowed=False):
            self.test_chat._consume_rate_limit()

        self.env["telegram.chat"]._flush_activity()
        self.assertEqual(self.test_chat.last_message_time, old_time)


class TestMultipleChatRateLimits(TelegramBotTestCase):
    def test_multiple_chats_independent_rate_limits(self):
        chat1 = self.env["telegram.chat"].create(
            {
                "chat_id": "chat1",
                "bot_id": self.test_bot.id,
                "rate_limit_enabled": True,
                "rate_limit_requests": 10,
            }
        )
        chat2 = self.env["telegram.chat"].create(
            {
                "chat_id": "chat2",
                "bot_id": self.test_bot.id,
                "rate_limit_enabled": True,
                "rate_limit_requests": 20,
            }
        )

        self.assertEqual(chat1.rate_limit_requests, 10)
        self.assertEqual(chat2.rate_limit_requests, 20)

        with self.mock_rate_limiter(is_allowed=True):
            allowed1 = chat1._consume_rate_limit()
            allowed2 = chat2._consume_rate_limit()

            self.assertTrue(allowed1)
            self.assertTrue(allowed2)

    def test_rate_limit_different_periods(self):
        chat_minute = self.env["telegram.chat"].create(
            {
                "chat_id": "chat_minute",
                "bot_id": self.test_bot.id,
                "rate_limit_enabled": True,
                "rate_limit_period": "minute",
            }
        )
        chat_hour = self.env["telegram.chat"].create(
            {
                "chat_id": "chat_hour",
                "bot_id": self.test_bot.id,
                "rate_limit_enabled": True,
                "rate_limit_period": "hour",
            }
        )

        self.assertEqual(chat_minute.rate_limit_period, "minute")
        self.assertEqual(chat_hour.rate_limit_period, "hour")


class TestActivityStampIsBestEffort(TelegramBotTestCase):
    def test_a_conflicting_stamp_does_not_take_the_request_with_it(self):
        self.env.flush_all()
        chat_module._pending_activity.ids = {self.test_chat.id}
        original_execute = type(self.env.cr).execute

        def failing_execute(cursor, query, *args, **kwargs):
            if "UPDATE telegram_chat SET last_message_time" in str(query):
                raise psycopg.errors.SerializationFailure(
                    "could not serialize access due to concurrent update"
                )
            return original_execute(cursor, query, *args, **kwargs)

        with patch.object(type(self.env.cr), "execute", failing_execute):
            self.env["telegram.chat"]._flush_activity()

        self.assertTrue(
            self.env["telegram.chat"].search([("id", "=", self.test_chat.id)]),
            "the cursor must still be usable: the stamp feeds a 90-day vacuum, "
            "it must never cost the request that carried the user's work",
        )
