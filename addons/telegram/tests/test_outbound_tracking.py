from datetime import timedelta

from odoo import fields

from .common import TelegramBotTestCase
from odoo.addons.telegram.tools import format as tg


class TestOutboundTracking(TelegramBotTestCase):
    def test_sending_to_an_unknown_chat_does_not_break_the_transaction(self):
        response = self.mock_telegram_response(success=True, result={"message_id": 3})

        with self.mock_api_gateway_post(response):
            self.test_bot.send_message("909090909", "hola")

        self.env.flush_all()

        chat = self.env["telegram.chat"].search(
            [("chat_id", "=", "909090909"), ("bot_id", "=", self.test_bot.id)]
        )
        self.assertTrue(
            chat,
            "telegram.message.chat_id is required, so a send to an unseen chat "
            "used to raise NotNullViolation at flush, outside every except block",
        )
        message = self.env["telegram.message"].search(
            [("chat_id", "=", chat.id), ("message_type", "=", "outbound")]
        )
        self.assertEqual(message.state, "sent")

    def test_a_failed_send_is_recorded_as_an_error(self):
        response = self.mock_telegram_response(
            success=False, error_code=400, description="Bad Request: chat not found"
        )

        with self.mock_api_gateway_post(response):
            self.test_bot.send_message(self.test_chat.chat_id, "hola")

        message = self.env["telegram.message"].search(
            [("chat_id", "=", self.test_chat.id), ("message_type", "=", "outbound")],
            limit=1,
        )
        self.assertEqual(message.state, "error")
        self.assertIn("chat not found", message.error_message)

    def test_the_same_message_id_may_repeat_across_chats(self):
        other_chat = self.env["telegram.chat"].create(
            {"chat_id": "70707", "bot_id": self.test_bot.id}
        )
        for chat in (self.test_chat, other_chat):
            self.env["telegram.message"].create(
                {
                    "bot_id": self.test_bot.id,
                    "chat_id": chat.id,
                    "message_type": "inbound",
                    "state": "received",
                    "msg_uid": "555",
                }
            )
        self.env.flush_all()
        self.assertEqual(
            self.env["telegram.message"].search_count([("msg_uid", "=", "555")]),
            2,
            "message_id is per chat in groups, so the uniqueness key must include it",
        )


class TestRepeatedMessageIds(TelegramBotTestCase):
    def test_a_repeated_message_id_costs_the_id_not_the_request(self):
        response = self.mock_telegram_response(success=True, result={"message_id": 42})

        with self.mock_api_gateway_post(response):
            self.test_bot.send_message(self.test_chat.chat_id, "first")
            self.test_bot.send_message(self.test_chat.chat_id, "second")

        self.env.flush_all()

        messages = self.env["telegram.message"].search(
            [("chat_id", "=", self.test_chat.id), ("message_type", "=", "outbound")],
            order="id",
        )
        self.assertEqual(len(messages), 2)
        self.assertEqual(
            messages.mapped("state"),
            ["sent", "sent"],
            "the unique index fires at flush, outside every except block, so a "
            "repeated id used to abort the whole webhook",
        )
        self.assertEqual(messages[0].msg_uid, "42")
        self.assertFalse(messages[1].msg_uid)


class TestOutboundEscaping(TelegramBotTestCase):
    def _whoami_text(self):
        response = self.mock_telegram_response(success=True, result={"message_id": 1})
        with self.mock_api_gateway_post(response) as mock_post:
            self.env["telegram.router"]._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/quiensoy",
                [],
                self.test_partner,
                internal_user=False,
            )
        return mock_post.call_args.kwargs["json"]

    def test_a_name_arrives_as_literal_html_text(self):
        self.test_partner.name = "Ana_<Bold>*&co"
        payload = self._whoami_text()

        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn("Ana_&lt;Bold&gt;*&amp;co", payload["text"])
        self.assertNotIn(
            "<Bold>",
            payload["text"],
            "an unescaped tag in a name makes Telegram refuse the whole message",
        )

    def test_link_syntax_in_a_name_stays_text(self):
        self.test_partner.name = 'Jose <a href="http://evil.example">x</a>'
        payload = self._whoami_text()

        self.assertIn("&lt;a href=", payload["text"])
        self.assertNotIn("<a ", payload["text"])

    def test_escape_neutralises_every_html_metacharacter(self):
        self.assertEqual(tg.escape("a<b>c&d_e*f`g[h"), "a&lt;b&gt;c&amp;d_e*f`g[h")

    def test_escape_renders_a_missing_value_as_empty(self):
        self.assertEqual(tg.escape(None), "")


class TestMessageGarbageCollection(TelegramBotTestCase):
    def _age(self, message, days):
        self.env.cr.execute(
            "UPDATE telegram_message SET create_date = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(days=days), message.id),
        )
        message.invalidate_recordset(["create_date"])

    def _make(self, state, msg_uid):
        return self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "message_type": "outbound",
                "state": state,
                "msg_uid": msg_uid,
                "text": "x",
            }
        )

    def test_old_failures_are_collected_too(self):
        failed = self._make("error", "gc-error")
        self._age(failed, 200)
        self.env["telegram.message"]._gc_telegram_messages()
        self.assertFalse(
            failed.exists(),
            "the vacuum only swept sent/received, so the failure tail grew forever",
        )

    def test_recent_failures_are_kept_for_diagnosis(self):
        failed = self._make("error", "gc-recent-error")
        self._age(failed, 20)
        self.env["telegram.message"]._gc_telegram_messages()
        self.assertTrue(failed.exists())

    def test_delivered_messages_are_collected_after_the_short_window(self):
        sent = self._make("sent", "gc-sent")
        self._age(sent, 20)
        self.env["telegram.message"]._gc_telegram_messages()
        self.assertFalse(sent.exists())
