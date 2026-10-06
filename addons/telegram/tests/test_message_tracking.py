from datetime import datetime, timedelta

from psycopg import IntegrityError

from .common import TelegramBotTestCase


class TestMessageCreation(TelegramBotTestCase):
    def test_create_outbound_message(self):
        message = self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "text": "Hello, World!",
                "message_type": "outbound",
                "state": "outgoing",
            }
        )

        self.assertEqual(message.message_type, "outbound")
        self.assertEqual(message.state, "outgoing")
        self.assertEqual(message.text, "Hello, World!")
        self.assertEqual(message.bot_id, self.test_bot)
        self.assertEqual(message.chat_id, self.test_chat)

    def test_create_inbound_message(self):
        message = self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "text": "/start",
                "command": "/start",
                "message_type": "inbound",
                "state": "received",
                "msg_uid": "12345",
            }
        )

        self.assertEqual(message.message_type, "inbound")
        self.assertEqual(message.state, "received")
        self.assertEqual(message.command, "/start")
        self.assertEqual(message.msg_uid, "12345")


class TestMessageStateTransitions(TelegramBotTestCase):
    def test_message_state_outgoing_to_sent(self):
        message = self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "text": "Test message",
                "message_type": "outbound",
                "state": "outgoing",
            }
        )

        message.write({"state": "sent", "msg_uid": "99999"})

        self.assertEqual(message.state, "sent")
        self.assertEqual(message.msg_uid, "99999")

    def test_message_state_outgoing_to_error(self):
        message = self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "text": "Failed message",
                "message_type": "outbound",
                "state": "outgoing",
            }
        )

        message.write(
            {
                "state": "error",
                "error_message": "Network timeout",
            }
        )

        self.assertEqual(message.state, "error")
        self.assertEqual(message.error_message, "Network timeout")


class TestMessageDeduplication(TelegramBotTestCase):
    def test_unique_msg_uid_constraint(self):
        self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "text": "Message 1",
                "message_type": "inbound",
                "state": "received",
                "msg_uid": "unique_id_123",
            }
        )

        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["telegram.message"].create(
                {
                    "bot_id": self.test_bot.id,
                    "chat_id": self.test_chat.id,
                    "text": "Message 2",
                    "message_type": "inbound",
                    "state": "received",
                    "msg_uid": "unique_id_123",
                }
            )

    def test_null_msg_uid_allowed_multiple(self):
        msg1 = self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "text": "Message 1",
                "message_type": "outbound",
                "state": "outgoing",
                "msg_uid": False,
            }
        )
        msg2 = self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "text": "Message 2",
                "message_type": "outbound",
                "state": "outgoing",
                "msg_uid": False,
            }
        )

        self.assertTrue(msg1.id)
        self.assertTrue(msg2.id)


class TestMessageDisplayName(TelegramBotTestCase):
    def test_message_display_name_text(self):
        message = self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "text": "Short text",
                "message_type": "outbound",
                "state": "sent",
            }
        )

        self.assertIn("[outbound]", message.display_name)
        self.assertIn("Short text", message.display_name)

    def test_message_display_name_truncates_long_text(self):
        long_message = self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "text": "A" * 60,
                "message_type": "inbound",
                "state": "received",
            }
        )

        self.assertIn("...", long_message.display_name)

    def test_message_display_name_with_media_type(self):
        photo_message = self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "media_type": "photo",
                "caption": "Nice photo",
                "message_type": "outbound",
                "state": "sent",
            }
        )

        self.assertIn("📷", photo_message.display_name)
        self.assertIn("Nice photo", photo_message.display_name)

    def test_message_display_name_media_without_caption(self):
        video_message = self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "media_type": "video",
                "message_type": "outbound",
                "state": "sent",
            }
        )

        self.assertIn("🎥", video_message.display_name)


class TestMessageRelationships(TelegramBotTestCase):
    def test_message_relationships(self):
        message = self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "text": "Test",
                "message_type": "outbound",
                "state": "sent",
            }
        )

        self.assertEqual(message.bot_id, self.test_bot)
        self.assertEqual(message.chat_id, self.test_chat)

    def _create_old_message(self, days_old, state="sent"):
        old_date = datetime.now() - timedelta(days=days_old)
        message = self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "text": f"Old message ({days_old} days)",
                "message_type": "outbound",
                "state": state,
            }
        )
        self.env.cr.execute(
            "UPDATE telegram_message SET create_date = %s WHERE id = %s",
            (old_date, message.id),
        )
        return message

    def test_gc_removes_old_sent_messages(self):
        old_message = self._create_old_message(days_old=16, state="sent")
        message_id = old_message.id

        removed_count = self.env["telegram.message"]._gc_telegram_messages()

        self.assertGreaterEqual(removed_count, 1)
        self.assertFalse(
            self.env["telegram.message"].browse(message_id).exists(),
            "Old sent message should be removed by auto-vacuum",
        )

    def test_gc_removes_old_received_messages(self):
        old_message = self._create_old_message(days_old=16, state="received")
        message_id = old_message.id

        removed_count = self.env["telegram.message"]._gc_telegram_messages()

        self.assertGreaterEqual(removed_count, 1)
        self.assertFalse(
            self.env["telegram.message"].browse(message_id).exists(),
            "Old received message should be removed by auto-vacuum",
        )

    def test_gc_keeps_recent_messages(self):
        recent_message = self._create_old_message(days_old=5, state="sent")

        self.env["telegram.message"]._gc_telegram_messages()

        recent_message.invalidate_recordset()
        self.assertTrue(
            recent_message.exists(),
            "Recent messages should not be removed",
        )

    def test_gc_keeps_outgoing_messages(self):
        outgoing_message = self._create_old_message(days_old=20, state="outgoing")

        self.env["telegram.message"]._gc_telegram_messages()

        outgoing_message.invalidate_recordset()
        self.assertTrue(
            outgoing_message.exists(),
            "Outgoing messages should be kept for debugging",
        )

    def test_gc_keeps_error_messages(self):
        error_message = self._create_old_message(days_old=20, state="error")

        self.env["telegram.message"]._gc_telegram_messages()

        error_message.invalidate_recordset()
        self.assertTrue(
            error_message.exists(),
            "Error messages should be kept for debugging",
        )


class TestInboundDeduplication(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.controller = self.env["telegram.router"]

    def test_another_bot_may_reuse_a_message_id(self):
        other_credential = self._make_bot_credential(
            "Other bot credential", "222222222:OTHERtokenAAAAAAAAAAAAAAAAAAAAAAAA"
        )
        other_bot = self.env["telegram.bot"].create(
            {"name": "Other Bot", "credential_id": other_credential.id}
        )
        other_chat = self.env["telegram.chat"].create(
            {"chat_id": "31415", "bot_id": other_bot.id}
        )

        self.controller._log_inbound_message(
            self.test_bot, self.test_chat, {"message_id": 314}, "hola"
        )
        self.controller._log_inbound_message(
            other_bot, other_chat, {"message_id": 314}, "hola"
        )
        self.env.flush_all()

        self.assertEqual(
            self.env["telegram.message"].search_count([("msg_uid", "=", "314")]),
            2,
            "the dedup search was not scoped to the bot, so one bot's history "
            "silently swallowed another's",
        )

    def test_the_same_message_is_only_logged_once(self):
        for _ in range(2):
            self.controller._log_inbound_message(
                self.test_bot, self.test_chat, {"message_id": 271}, "/start"
            )
        self.env.flush_all()

        messages = self.env["telegram.message"].search([("msg_uid", "=", "271")])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages.command, "/start")
