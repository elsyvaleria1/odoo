from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.service.model import call_kw

from .common import (
    TelegramBotTestCase,
    rpc_exposed_methods,
    telegram_family_modules,
)
from odoo.addons.telegram.tools.telegram_client import TelegramClient


class TestChatRpcBoundary(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.test_chat._flow_start("telegram.handler.base", "real", {"k": "real"})
        self.chats_as_user = self.env["telegram.chat"].with_user(self.test_user)

    def _snapshot(self):
        self.test_chat.invalidate_recordset()
        return (
            self.test_chat.flow_step,
            self.test_chat.flow_data,
            self.test_chat.context_data,
            self.test_chat.failed_command_count,
            self.test_chat.last_error,
        )

    def test_the_owner_reads_the_chat_and_cannot_write_it(self):
        self.assertTrue(self.test_chat.with_user(self.test_user).has_access("read"))
        self.assertFalse(self.test_chat.with_user(self.test_user).has_access("write"))

    def test_no_chat_method_is_an_rpc_entry_point(self):
        self.assertFalse(
            rpc_exposed_methods(self.chats_as_user, telegram_family_modules(self.env)),
            "the bot's conversation flow writes the chat with elevated rights; "
            "a public name hands that write to whoever can read the chat",
        )

    def test_the_owner_cannot_drive_the_conversation_over_rpc(self):
        before = self._snapshot()
        calls = [
            ("flow_start", ["telegram.handler.base", "forged"]),
            ("flow_end", []),
            ("set_context", ["step", "forged"]),
            ("increment_failed_state", ["forged"]),
            ("reset_failed_state", []),
            ("check_rate_limit", []),
            ("_flow_start", ["telegram.handler.base", "forged"]),
            ("_flow_advance", ["forged"]),
            ("_flow_update", [{"step": "forged"}]),
            ("_flow_end", []),
            ("_set_context", ["step", "forged"]),
            ("_increment_failed_state", ["forged"]),
        ]
        for method, args in calls:
            with (
                self.subTest(method=method),
                self.assertRaises((AccessError, AttributeError)),
            ):
                call_kw(self.chats_as_user, method, [[self.test_chat.id], *args], {})
        self.assertEqual(self._snapshot(), before)

    def test_the_flow_still_moves_the_chat_of_its_own_user(self):
        chat = self.test_chat.with_user(self.test_user)

        chat._flow_start("telegram.handler.base", "flow", {"k": "flow"})
        chat._flow_update({"retries": 1})
        chat._set_context("parked", 1)

        self.assertEqual(
            self._snapshot()[:3], ("flow", {"k": "flow", "retries": 1}, {"parked": 1})
        )
        self.assertFalse(chat.env.privileges)


class TestBotRpcBoundary(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.bots_as_user = self.env["telegram.bot"].with_user(self.test_user)

    def test_a_reader_of_the_bot_reaches_no_transport(self):
        self.assertTrue(self.test_bot.with_user(self.test_user).has_access("read"))
        self.assertFalse(
            rpc_exposed_methods(
                self.bots_as_user,
                "telegram.",
                allowed={
                    "action_register_webhook",
                    "get_lang",
                },
            ),
            "a user who reads the bot would speak through it to any chat, or "
            "download any file it was sent",
        )

    def test_a_reader_cannot_send_as_the_bot(self):
        messages = self.env["telegram.message"].search_count([])
        with patch.object(TelegramClient, "_post") as post:
            for method, args in (
                ("send_message", ["424242", "phish"]),
                ("send_document", ["424242", b"x", "x.pdf"]),
                ("get_file", ["file-1"]),
                ("get_file_content", ["file-1"]),
                ("answer_callback_query", ["cb-1", "phish"]),
                ("edit_message_reply_markup", ["424242", 7, {}]),
            ):
                with self.subTest(method=method), self.assertRaises(AccessError):
                    call_kw(self.bots_as_user, method, [[self.test_bot.id], *args], {})
        post.assert_not_called()
        self.assertEqual(self.env["telegram.message"].search_count([]), messages)

    def test_no_user_looks_a_bot_up_by_its_token(self):
        with self.assertRaises(AccessError):
            call_kw(self.bots_as_user, "find_by_token", [self.TEST_BOT_TOKEN], {})

    def test_a_reader_cannot_register_the_webhook(self):
        with (
            patch.object(TelegramClient, "_post") as post,
            self.assertRaises(AccessError),
        ):
            call_kw(
                self.bots_as_user, "action_register_webhook", [[self.test_bot.id]], {}
            )
        post.assert_not_called()
