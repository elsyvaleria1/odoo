from unittest.mock import patch

from odoo.tests import new_test_user, tagged

from ..tools.authority import OPERATE_BOT
from .common import TelegramBotTestCase


@tagged("post_install", "-at_install")
class TestUpdateAuthority(TelegramBotTestCase):
    """Whatever an update is -- a command, a button, a message -- what it
    reaches runs as its sender, holding the bot's privilege, and never as
    the superuser."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env, login="tg_authority", groups="base.group_user"
        )
        cls.tg_id = "777001"
        cls._bound_account(cls.tg_id, cls.user.partner_id, user=cls.user)
        cls.public = cls.env.ref("base.public_user")
        cls.operate = cls.env["res.groups"]._privilege_ids((OPERATE_BOT,))

    def _webhook_bot(self):
        # the webhook hands the router a superuser bot of the request's user,
        # in a transaction whose real user is that request's
        transaction = self.env.transaction
        self.patch(transaction, "default_env", self.env(user=self.public))
        return self.test_bot.with_user(self.public).sudo()

    def _seen(self, records):
        return {
            "uid": records.env.uid,
            "su": records.env.su,
            "operates": self.operate <= records.env.privileges,
            "real_uid": records.env.transaction.default_env.uid,
        }

    def _button(self, chat_id):
        router = self.env["telegram.router"]
        seen = {}

        def owner(this, bot, data):
            return this.env["telegram.handler.base"]

        def on_callback(handler, bot, chat, query, partner, internal_user):
            seen.update(self._seen(handler), chat=self._seen(chat))
            return True

        query = self.mock_telegram_callback_query(
            chat_id=chat_id, from_user=self._sender_of(chat_id)
        )
        with (
            patch.object(type(router), "_callback_owner", owner),
            patch.object(
                type(self.env["telegram.handler.base"]), "_on_callback", on_callback
            ),
            self.mock_api_gateway_post(),
        ):
            router._handle_update(
                self._webhook_bot(), {"update_id": 9001, "callback_query": query}
            )
        return seen

    def _free_text(self, chat_id):
        router = self.env["telegram.router"]
        seen = {}

        def unhandled(this, bot, chat, message, partner, internal_user):
            seen.update(self._seen(this), bot=self._seen(bot))

        message = self.mock_telegram_message(chat_id=chat_id, text="hola")
        with (
            patch.object(type(router), "_unhandled_message", unhandled),
            patch.object(type(router), "_idle_handler", return_value=None),
            self.mock_api_gateway_post(),
        ):
            router._handle_update(
                self._webhook_bot(), {"update_id": 9002, "message": message}
            )
        return seen

    def test_a_linked_user_s_button_runs_as_that_user(self):
        seen = self._button(self.tg_id)
        self.assertEqual(seen["uid"], self.user.id)
        self.assertEqual(seen["real_uid"], self.user.id)
        self.assertFalse(seen["su"])
        self.assertTrue(seen["operates"])
        self.assertEqual(seen["chat"]["uid"], self.user.id)

    def test_a_linked_user_s_message_runs_as_that_user(self):
        seen = self._free_text(self.tg_id)
        self.assertEqual((seen["uid"], seen["su"]), (self.user.id, False))
        self.assertEqual(seen["bot"]["uid"], self.user.id)
        self.assertTrue(seen["operates"])

    def test_an_unlinked_sender_runs_as_the_request_s_own_user(self):
        seen = self._free_text("777002")
        self.assertEqual((seen["uid"], seen["su"]), (self.public.id, False))
        self.assertEqual(seen["real_uid"], self.public.id)
        self.assertTrue(seen["operates"])
