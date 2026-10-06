from unittest.mock import patch

from odoo.addons.mail_telegram.tests.test_mail_telegram import MailTelegramCase


class TestVoiceReplies(MailTelegramCase):
    def _voice_reply(self):
        update = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id, text="", message_id=970
        )
        update.pop("text")
        update["voice"] = {"file_id": "voice-1", "duration": 3}
        update["reply_to_message"] = {"message_id": 900}
        with self.mock_api_gateway_post() as post, self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_message(self.test_bot, update)
        return post

    def _delivered(self, message):
        return self.env["telegram.message"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "message_type": "outbound",
                "state": "sent",
                "msg_uid": "900",
                "mail_message_id": message.id,
                "recipient_partner_id": self.test_partner.id,
            }
        )

    def test_a_voice_reply_is_posted_as_its_transcript(self):
        parent = self._post_to_user()
        self._delivered(parent)
        bot = type(self.test_bot)
        with (
            patch.object(bot, "_hears_voice_notes", return_value=True),
            patch.object(bot, "get_file_content", return_value=b"OggS"),
            patch.object(bot, "_hear_voice_note", return_value="ya quedó listo"),
        ):
            post = self._voice_reply()

        posted = self.record.message_ids.filtered(lambda m: m.parent_id == parent)
        self.assertIn("🎤 ya quedó listo", posted.body)
        self.assertFalse(posted.attachment_ids, "the recording is kept nowhere")
        self.assertIn(
            "/sendChatAction",
            " ".join(str(call.args[0]) for call in post.call_args_list),
            "the chat sees the bot typing while the note is heard",
        )

    def test_an_unheard_voice_reply_asks_to_type(self):
        parent = self._post_to_user()
        self._delivered(parent)
        bot = type(self.test_bot)
        with (
            patch.object(bot, "_hears_voice_notes", return_value=True),
            patch.object(bot, "get_file_content", return_value=b"OggS"),
            patch.object(bot, "_hear_voice_note", return_value=None),
        ):
            post = self._voice_reply()

        self.assertFalse(
            self.record.message_ids.filtered(lambda m: m.parent_id == parent)
        )
        self.assertIn("type", post.call_args.kwargs["json"]["text"])
