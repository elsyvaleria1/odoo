from datetime import datetime, timedelta

from odoo import fields

from .common import TelegramBotTestCase


class TestExpiredFlowCollection(TelegramBotTestCase):
    def _chat(self, chat_id, expires_at):
        return self.env["telegram.chat"].create(
            {
                "chat_id": chat_id,
                "bot_id": self.test_bot.id,
                "flow_owner": "telegram.handler.base",
                "flow_step": "email_input",
                "flow_data": {"retries": 0},
                "flow_expires_at": expires_at,
            }
        )

    def test_expired_flows_are_cleared(self):
        stale_chat = self._chat("stale", datetime.now() - timedelta(minutes=1))

        count = self.env["telegram.chat"]._gc_expired_flows()

        stale_chat.invalidate_recordset()
        self.assertGreaterEqual(count, 1)
        self.assertFalse(stale_chat.flow_owner)
        self.assertFalse(stale_chat.flow_step)
        self.assertFalse(stale_chat.flow_data)

    def test_open_flows_are_kept(self):
        open_chat = self._chat("open", datetime.now() + timedelta(minutes=30))

        self.env["telegram.chat"]._gc_expired_flows()

        open_chat.invalidate_recordset()
        self.assertEqual(open_chat.flow_step, "email_input")
        self.assertEqual(open_chat.flow_data, {"retries": 0})

    def test_every_move_pushes_the_expiry_back(self):
        chat = self._chat("moving", datetime.now() + timedelta(minutes=1))

        before = fields.Datetime.now()
        chat._flow_advance("next")

        self.assertGreaterEqual(chat.flow_expires_at, before + timedelta(minutes=59))


class TestChatAutoVacuum(TelegramBotTestCase):
    def test_autovacuum_removes_old_unlinked_chats(self):
        old_date = datetime.now() - timedelta(days=91)
        old_chat = self.env["telegram.chat"].create(
            {
                "chat_id": "old_unlinked",
                "bot_id": self.test_bot.id,
                "last_message_time": old_date,
            }
        )

        chat_id = old_chat.id

        removed_count = self.env["telegram.chat"]._gc_telegram_chats()

        self.assertGreaterEqual(removed_count, 1)
        self.assertFalse(
            self.env["telegram.chat"].browse(chat_id).exists(),
            "Old unlinked chat should be removed",
        )

    def test_autovacuum_keeps_partner_linked_chats(self):
        old_date = datetime.now() - timedelta(days=91)
        linked_chat = self.env["telegram.chat"].create(
            {
                "chat_id": "770077",
                "chat_type": "private",
                "bot_id": self.test_bot.id,
                "account_id": self._bound_account("770077", self.test_partner).id,
                "last_message_time": old_date,
            }
        )

        self.env["telegram.chat"]._gc_telegram_chats()

        linked_chat.invalidate_recordset()
        self.assertTrue(
            linked_chat.exists(),
            "Partner-linked chats should be kept indefinitely",
        )

    def test_autovacuum_keeps_recent_chats(self):
        recent_date = datetime.now() - timedelta(days=30)
        recent_chat = self.env["telegram.chat"].create(
            {
                "chat_id": "recent_unlinked",
                "bot_id": self.test_bot.id,
                "last_message_time": recent_date,
            }
        )

        self.env["telegram.chat"]._gc_telegram_chats()

        recent_chat.invalidate_recordset()
        self.assertTrue(
            recent_chat.exists(),
            "Recent chats should not be removed",
        )

    def test_autovacuum_keeps_chats_in_an_open_flow(self):
        old_date = datetime.now() - timedelta(days=91)
        active_chat = self.env["telegram.chat"].create(
            {
                "chat_id": "old_active",
                "bot_id": self.test_bot.id,
                "flow_owner": "telegram.handler.base",
                "flow_step": "email_input",
                "flow_expires_at": datetime.now() + timedelta(minutes=30),
                "last_message_time": old_date,
            }
        )

        self.env["telegram.chat"]._gc_telegram_chats()

        active_chat.invalidate_recordset()
        self.assertTrue(
            active_chat.exists(),
            "Chats in active conversation should not be removed",
        )

    def test_autovacuum_removes_never_messaged_chats(self):
        never_messaged = self.env["telegram.chat"].create(
            {
                "chat_id": "never_messaged",
                "bot_id": self.test_bot.id,
                "last_message_time": False,
            }
        )

        chat_id = never_messaged.id

        self.env["telegram.message"]._gc_telegram_messages()

        self.env["telegram.chat"]._gc_telegram_chats()

        self.assertFalse(
            self.env["telegram.chat"].browse(chat_id).exists(),
            "Never-messaged chats should be removed",
        )

    def test_autovacuum_keeps_chats_with_messages(self):
        old_date = datetime.now() - timedelta(days=91)
        chat_with_messages = self.env["telegram.chat"].create(
            {
                "chat_id": "chat_with_msgs",
                "bot_id": self.test_bot.id,
                "last_message_time": old_date,
            }
        )

        self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": chat_with_messages.id,
                "text": "Test message",
                "message_type": "inbound",
                "state": "received",
            }
        )

        self.env["telegram.chat"]._gc_telegram_chats()

        chat_with_messages.invalidate_recordset()
        self.assertTrue(
            chat_with_messages.exists(),
            "Chats with message history should not be removed",
        )
