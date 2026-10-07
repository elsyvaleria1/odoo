from datetime import timedelta

from odoo import fields

from .test_mail_telegram import MailTelegramCase


class TestConversationFromTelegram(MailTelegramCase):
    """/escribir chooses where what is written in the bot's chat goes: a
    colleague or a recent conversation of Discuss. From then on what the
    person sends there goes to it, as in a chat."""

    def _send(self, text=None, **extra):
        message = self.mock_telegram_message(
            chat_id="12345", text=text, message_id=extra.pop("message_id", 700)
        )
        if text is None:
            message.pop("text")
        message.update(extra)
        with self.mock_api_gateway_post() as post, self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_message(self.test_bot, message)
        return post

    def _press(self, data):
        query = self.mock_telegram_callback_query(callback_data=data)
        with self.mock_api_gateway_post() as post, self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_callback_query(self.test_bot, query)
        return post

    @staticmethod
    def _sent(post):
        return " ".join(str(call.kwargs or call.args) for call in post.call_args_list)

    def _dm(self):
        return (
            self.env["discuss.channel"]
            .with_user(self.test_user)
            ._get_or_create_chat(partners_to=self.author_partner.ids)
        )

    def _posted(self, channel, text):
        return channel.message_ids.filtered(lambda m: text in (m.body or ""))

    def test_a_colleague_is_looked_up_by_name(self):
        post = self._send("/escribir Colle")

        self.assertIn(f"mt:dm:{self.author.id}", self._sent(post))

    def test_picking_a_colleague_opens_the_direct_chat(self):
        post = self._press(f"mt:dm:{self.author.id}")

        self.assertIn("You now write to", self._sent(post))
        self.assertIn("Colleague", self._sent(post))
        self._send("hola Ana")
        self.assertEqual(
            self._posted(self._dm(), "hola Ana").author_id, self.test_partner
        )

    def test_a_message_written_to_the_conversation_is_acknowledged(self):
        self._press(f"mt:dm:{self.author.id}")

        self._send("con reacción", message_id=701)

        reaction = self.env["telegram.message"].search(
            [
                ("chat_id", "=", self.test_chat.id),
                ("api_method", "=", "setMessageReaction"),
            ]
        )
        self.assertEqual(reaction.payload["message_id"], 701)

    def test_a_recent_conversation_is_offered_and_opened(self):
        channel = self._dm()

        post = self._send("/escribir")
        self.assertIn(f"mt:cv:{channel.id}", self._sent(post))
        self.assertIn("mt:new", self._sent(post))

        self._press(f"mt:cv:{channel.id}")
        self._send("seguimos aquí")
        self.assertTrue(self._posted(channel, "seguimos aquí"))

    def test_a_new_conversation_asks_for_a_name(self):
        self._press("mt:new")

        post = self._send("Colle")

        self.assertIn(f"mt:dm:{self.author.id}", self._sent(post))

    def test_a_reply_to_a_notification_still_goes_to_its_record(self):
        self._press(f"mt:dm:{self.author.id}")
        notified = self._post_to_user()
        delivered = self._queued().filtered(lambda m: m.mail_message_id == notified)
        delivered.sudo().msg_uid = "601"

        self._send("sobre el registro", reply_to_message={"message_id": 601})

        self.assertTrue(self._posted(self.record, "sobre el registro"))
        self.assertFalse(self._posted(self._dm(), "sobre el registro"))

    def test_ending_the_conversation_stops_writing_to_it(self):
        self._press(f"mt:dm:{self.author.id}")

        self._press("mt:end")
        self._send("ya no va")

        self.assertFalse(self._posted(self._dm(), "ya no va"))

    def test_a_quiet_conversation_closes_by_itself(self):
        channel = self._dm()
        self._press(f"mt:cv:{channel.id}")
        self.test_chat._set_context(
            "mail_focus",
            {
                "channel_id": channel.id,
                "until": fields.Datetime.to_string(
                    fields.Datetime.now() - timedelta(minutes=1)
                ),
            },
        )

        self._send("tarde")

        self.assertFalse(self._posted(channel, "tarde"))

    def test_sharing_one_s_number_is_not_written_to_the_conversation(self):
        self._press(f"mt:dm:{self.author.id}")

        self._send(
            contact={
                "phone_number": "5215511112222",
                "user_id": 12345,
                "first_name": "Test",
            }
        )

        self.assertEqual(self.test_account.phone, "+5215511112222")
        self.assertFalse(
            self._dm().message_ids.filtered(lambda m: m.author_id == self.test_partner)
        )

    def test_the_help_names_the_command(self):
        post = self._send("/ayuda")

        self.assertIn("/escribir", self._sent(post))

    def test_a_bot_delivering_no_notifications_says_it_does_not_know_it(self):
        # it used to read the command and answer nothing at all
        self.test_bot.notify_mail = False

        post = self._send("/escribir Colle")

        self.assertIn("Unknown command", self._sent(post))
        self.assertNotIn(f"mt:dm:{self.author.id}", self._sent(post))

    def test_the_menu_offers_it_only_where_notifications_are_delivered(self):
        self.test_chat._sync_command_menu()
        commands = [e["command"] for e in self.test_chat.command_menu]
        self.assertIn("escribir", commands)
        # alphabetical, then the way out and the help
        self.assertEqual(commands[-2:], ["cancelar", "ayuda"])
        self.assertEqual(commands[:-2], sorted(commands[:-2]))

        self.test_bot.notify_mail = False

        self.assertNotIn(
            "escribir", [e["command"] for e in self.test_chat.command_menu]
        )
