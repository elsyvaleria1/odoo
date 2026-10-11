from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError

from .test_mail_telegram import MailTelegramCase
from odoo.addons.telegram.tests.common import NOT_A_MENU as _NOT_A_MENU
from odoo.addons.telegram.tools import errors

_CALL = "odoo.addons.telegram.tools.telegram_client.TelegramClient.call"
_ALERT = "Telegram is not delivering your notifications"


class DestinationCase(MailTelegramCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_bot.bot_username = "notify_bot"
        cls.test_user._telegram_settings().telegram_notify_inbox = "always"

    def _second_chat(self, tg_user_id="55501", bot=None, active_at=None):
        account = self._bound_account(
            tg_user_id, self.test_partner, user=self.test_user
        )
        return self.env["telegram.chat"].create(
            {
                "chat_id": tg_user_id,
                "chat_type": "private",
                "bot_id": (bot or self.test_bot).id,
                "account_id": account.id,
                "last_message_time": active_at or fields.Datetime.now(),
            }
        )

    def _outbound(self, chat):
        return self.env["telegram.message"].search(
            [("chat_id", "=", chat.id), ("message_type", "=", "outbound"), _NOT_A_MENU]
        )

    def _alerts(self):
        self._run_alert_jobs()
        return self.env["mail.message"].search(
            [("subject", "=", _ALERT), ("partner_ids", "in", self.test_partner.ids)]
        )


class TestOneDestination(DestinationCase):

    def test_the_last_used_chat_gets_it_when_none_is_chosen(self):
        self.test_chat.last_message_time = fields.Datetime.now() - timedelta(days=2)
        recent = self._second_chat()

        self._post_to_user()

        self.assertEqual(len(self._outbound(recent)), 1)
        self.assertFalse(self._outbound(self.test_chat))

    def test_the_chosen_chat_gets_it(self):
        self._second_chat()
        self.test_user._update_telegram_notify_chat(self.test_chat)

        self._post_to_user()

        self.assertEqual(len(self._outbound(self.test_chat)), 1)

    def test_a_blocked_chat_gives_way_when_none_is_chosen(self):
        blocked = self._second_chat()
        blocked._side_block()

        self.assertEqual(self.test_user._get_telegram_notify_chat(), self.test_chat)

    def test_a_chosen_chat_that_blocked_the_bot_gets_nothing(self):
        self._second_chat()
        self.test_user._update_telegram_notify_chat(self.test_chat)
        self.test_chat._side_block()

        self._post_to_user()

        self.assertFalse(
            self.env["telegram.message"].search(
                [
                    ("mail_message_id", "!=", False),
                    ("message_type", "=", "outbound"),
                    _NOT_A_MENU,
                ]
            )
        )

    def test_a_queued_notification_follows_a_change_of_destination(self):
        self._post_to_user()
        queued = self._outbound(self.test_chat)
        self.test_user._update_telegram_notify_chat(self._second_chat())

        self.assertFalse(queued._still_wanted())

    def test_only_an_own_chat_can_be_chosen(self):
        stranger = self.unlinked_chat
        with self.assertRaises(ValidationError):
            self.test_user._update_telegram_notify_chat(stranger)

    def test_a_bot_of_another_company_delivers_nothing(self):
        other = self.env["res.company"].create({"name": "TG Destination Other"})
        self.test_bot.company_id = other

        self._post_to_user()

        self.assertFalse(self._outbound(self.test_chat))
        self.assertEqual(self.test_user._get_telegram_notify_status()[0], "no_bot")

    def test_a_bot_of_another_company_leaves_their_own_bot_delivering(self):
        self._bot_of_another_company("Other Notify Bot").notify_mail = True
        self.env.invalidate_all()

        self._post_to_user()

        self.assertEqual(len(self._outbound(self.test_chat)), 1)
        self.assertEqual(
            self.test_user.with_user(self.test_user)._get_telegram_connect_bot(),
            self.test_bot,
        )


class TestConnecting(DestinationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plain_bot = cls.env["telegram.bot"].create(
            {
                "name": "Plain Bot",
                "credential_id": cls._make_bot_credential(
                    "Plain Bot Credential",
                    "423456789:XYZ-DEF1234ghIkl-zyx57W2v1u123ew44",
                ).id,
            }
        )
        cls.plain_bot.bot_username = "aaa_plain_bot"

    def _start(self, bot, tg_user_id="880021"):
        token = (
            self.env["telegram.link.token"]
            .with_user(self.test_user)
            ._issue_for_session(bot)
        )
        update = {
            "message_id": 1,
            "from": {"id": int(tg_user_id), "first_name": "Teléfono"},
            "chat": {"id": int(tg_user_id), "type": "private"},
            "date": 1,
            "text": f"/start {token}",
        }
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_message(bot, update)
        return self.env["telegram.chat"].search(
            [("chat_id", "=", tg_user_id), ("bot_id", "=", bot.id)]
        )

    def test_connect_opens_the_bot_that_delivers_notifications(self):
        bot = self.test_user.with_user(self.test_user)._get_telegram_connect_bot()

        self.assertEqual(bot, self.test_bot)

    def test_connecting_through_it_makes_the_chat_the_destination(self):
        chat = self._start(self.test_bot)

        self.assertEqual(
            self.test_user._telegram_settings().telegram_notify_chat_id, chat
        )
        self.assertEqual(self.test_user._get_telegram_notify_chat(), chat)
        texts = self._outbound(chat).mapped("text")
        self.assertTrue(any("will arrive here" in (text or "") for text in texts))

    def test_connecting_through_another_bot_points_to_the_right_one(self):
        chat = self._start(self.plain_bot, tg_user_id="880022")

        texts = " ".join(self._outbound(chat).mapped("text"))
        self.assertIn("https://t.me/notify_bot", texts)
        self.assertFalse(self.test_user._telegram_settings().telegram_notify_chat_id)


class TestUnreachable(DestinationCase):

    def setUp(self):
        super().setUp()
        patcher = patch.object(
            type(self.env["ir.job"]), "_defer", lambda *args, **kwargs: None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fail_next(self, error):
        self._post_to_user()
        queued = self._outbound(self.test_chat).filtered(
            lambda m: m.state == "outgoing"
        )
        with patch(_CALL, side_effect=error):
            for message in queued:
                message._deliver()

    def test_the_first_refused_notification_alerts_the_user(self):
        self._fail_next(errors.TelegramBadRequest(400, "Bad Request: chat not found"))

        alert = self._alerts()
        self.assertEqual(len(alert), 1)
        self.assertIn("chat not found", alert.body)
        self.assertEqual(alert.author_id, self.env.ref("base.partner_root"))
        self.assertFalse(
            self.env["telegram.message"].search([("mail_message_id", "=", alert.id)])
        )
        self.assertEqual(self.test_user._get_telegram_notify_status()[0], "failing")

    def test_a_failing_chat_alerts_only_once(self):
        error = errors.TelegramBadRequest(400, "Bad Request: chat not found")
        self._fail_next(error)
        self._fail_next(error)

        self.assertEqual(len(self._alerts()), 1)

    def test_blocking_the_bot_alerts_the_user(self):
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_my_chat_member(
                self.test_bot,
                {
                    "chat": {"id": 12345, "type": "private"},
                    "from": {"id": 12345, "first_name": "Test"},
                    "new_chat_member": {"status": "kicked"},
                },
            )

        self.assertEqual(len(self._alerts()), 1)
        self.assertEqual(self.test_user._get_telegram_notify_status()[0], "blocked")

    def test_blocking_one_of_two_chats_alerts_nobody(self):
        self._second_chat()
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_my_chat_member(
                self.test_bot,
                {
                    "chat": {"id": 55501, "type": "private"},
                    "from": {"id": 55501, "first_name": "Test"},
                    "new_chat_member": {"status": "kicked"},
                },
            )

        self.assertFalse(self._alerts())
        self.assertEqual(self.test_user._get_telegram_notify_chat(), self.test_chat)


class TestStatus(DestinationCase):

    def _state(self):
        return self.test_user.with_user(self.test_user).telegram_notify_state

    def test_ready(self):
        self.assertEqual(self._state(), "ready")

    def test_unconnected(self):
        self.test_binding._revoke("user")
        self.assertEqual(self._state(), "unconnected")

    def test_no_bot(self):
        self.test_bot.notify_mail = False
        self.assertEqual(self._state(), "no_bot")

    def test_start_bot(self):
        self.test_chat.bot_id = self.env["telegram.bot"].create(
            {
                "name": "Other Bot",
                "credential_id": self._make_bot_credential(
                    "Status Other Credential",
                    "523456789:XYZ-DEF1234ghIkl-zyx57W2v1u123ew55",
                ).id,
            }
        )
        self.assertEqual(self._state(), "start_bot")
