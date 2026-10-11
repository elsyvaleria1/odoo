from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import TelegramBotTestCase
from odoo.addons.telegram.models.telegram_bot import TelegramBot


@tagged("post_install", "-at_install")
class TestMovedBot(TelegramBotTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.new_bot = cls._bot_of_another_company("New Home Bot")
        cls.new_bot.bot_username = "new_home_bot"
        cls.test_bot.moved_to_id = cls.new_bot

    def _update(self, data):
        with (
            patch.object(TelegramBot, "send_message") as send,
            patch.object(TelegramBot, "answer_callback_query") as answer,
        ):
            self.env["telegram.router"]._handle_update(self.test_bot, data)
        return send, answer

    def test_a_message_is_pointed_to_the_new_bot(self):
        send, _answer = self._update(
            {"update_id": 1, "message": self.mock_telegram_message(text="/start")}
        )
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[0], "12345")
        self.assertIn("@new_home_bot", send.call_args.args[1])
        self.assertIn("https://t.me/new_home_bot", send.call_args.args[1])

    def test_a_button_is_answered_and_pointed_to_the_new_bot(self):
        send, answer = self._update(
            {"update_id": 2, "callback_query": self.mock_telegram_callback_query()}
        )
        answer.assert_called_once_with("callback_query_id")
        self.assertIn("@new_home_bot", send.call_args.args[1])

    def test_a_group_hears_nothing(self):
        message = self.mock_telegram_message(chat_id="-100555", text="hola")
        message["chat"]["type"] = "group"
        send, _answer = self._update({"update_id": 3, "message": message})
        self.assertFalse(send.called)

    def test_it_offers_no_command_and_carries_no_notification(self):
        self.assertEqual(self.test_chat._get_command_menu(), [])
        self.assertFalse(
            self.env["telegram.chat"]._for_partner(self.test_partner, self.test_bot)
        )
        self.assertNotIn(self.test_bot, self.test_user.telegram_connect_bot_ids)
        self.assertNotIn(
            self.test_bot, self.env["telegram.bot"]._serving("telegram.handler.base")
        )

        self.test_bot.moved_to_id = False
        self.assertTrue(
            self.env["telegram.chat"]._for_partner(self.test_partner, self.test_bot)
        )

    def test_a_bot_moves_to_one_that_stayed(self):
        with self.assertRaises(ValidationError):
            self.new_bot.moved_to_id = self.test_bot
        self.test_bot.moved_to_id = False
        with self.assertRaises(ValidationError):
            self.test_bot.moved_to_id = self.test_bot
