from contextlib import contextmanager
from unittest.mock import patch

from odoo import Command
from odoo.tools.translate import LazyTranslate

from .common import TelegramBotTestCase
from odoo.addons.telegram.models.telegram_bot import TelegramBot
from odoo.addons.telegram.tools.dispatch import TelegramCommand

_lt = LazyTranslate(__name__)


class TestCommandPermissions(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.router = self.env["telegram.router"]
        self.handler = type(self.env["telegram.handler.base"])

    @contextmanager
    def guarded(self, command="/guardada", **grants):
        """Make every bot answer `command`, declared with `grants`; yield the
        users it ran as."""
        original = self.handler._telegram_commands
        ran = []

        def commands(this):
            return {
                **original(this),
                command: TelegramCommand(
                    "_test_guarded_command", "internal", builtin=True, **grants
                ),
            }

        def run(this, bot, chat, args, partner=False, internal_user=False):
            ran.append(internal_user)

        with (
            patch.object(self.handler, "_telegram_commands", commands),
            patch.object(self.handler, "_test_guarded_command", run, create=True),
        ):
            yield ran

    def _dispatch(self, command):
        with patch.object(TelegramBot, "send_message") as send:
            self.router._dispatch_command(
                self.test_bot,
                self.test_chat,
                command,
                [],
                self.test_partner,
                self.test_user,
            )
        return [call.args[1] for call in send.call_args_list]

    def test_an_access_the_user_lacks_refuses_the_command(self):
        with self.guarded(access=("res.users", "unlink")) as ran:
            sent = self._dispatch("/guardada")
        self.assertFalse(ran)
        self.assertIn("permission", sent[0])

    def test_an_access_the_user_has_runs_it(self):
        with self.guarded(access=("res.partner", "read")) as ran:
            self._dispatch("/guardada")
        self.assertEqual(ran, [self.test_user])

    def test_grants_are_an_internal_users(self):
        with self.assertRaises(ValueError):
            TelegramCommand("_m", "partner", access=("res.partner", "read"))

    def test_a_builtin_of_a_feature_the_bot_does_not_run_is_unknown(self):
        with (
            self.guarded() as ran,
            patch.object(self.handler, "_feature_enabled", lambda this, bot: False),
        ):
            sent = self._dispatch("/guardada")
        self.assertFalse(ran)
        self.assertIn("Unknown command", sent[0])

    def test_asking_whether_a_command_is_allowed_sends_nothing(self):
        refuse = patch.object(
            self.handler, "_command_allowed", lambda this, *args: False
        )
        with self.guarded() as ran, refuse:
            with patch.object(TelegramBot, "send_message") as send:
                available = self.router._available_commands(
                    self.test_bot, self.test_chat, self.test_partner, self.test_user
                )
            self.assertFalse(send.called)
            self.assertNotIn("/guardada", dict(available))
            sent = self._dispatch("/guardada")
        self.assertFalse(ran)
        self.assertIn("permission", sent[0])


class TestCommandMenu(TelegramBotTestCase):
    def _menus(self, chat=None):
        return self.env["telegram.message"].search(
            [
                ("chat_id", "=", (chat or self.test_chat).id),
                ("api_method", "=", "setMyCommands"),
            ],
            order="id",
        )

    def _commands(self, menu):
        return [entry["command"] for entry in menu.payload["commands"]]

    def test_the_menu_names_what_the_person_may_run(self):
        self.test_chat._sync_command_menu()
        menu = self._menus()
        self.assertEqual(len(menu), 1)
        # /start is Telegram's own button, /desconectar is never one tap away
        self.assertEqual(self._commands(menu), ["quiensoy", "cancelar", "ayuda"])
        self.assertEqual(menu.payload["scope"], {"type": "chat", "chat_id": 12345})
        self.assertEqual(self.test_chat.command_menu, menu.payload["commands"])

    def test_the_menu_is_sent_again_only_when_it_changes(self):
        self.test_chat._sync_command_menu()
        self.test_chat._sync_command_menu()
        self.assertEqual(len(self._menus()), 1)

        handler = type(self.env["telegram.handler.base"])
        original = handler._telegram_commands

        def commands(this):
            return {
                **original(this),
                "/nuevo": TelegramCommand(
                    "_m", "internal", builtin=True, description=_lt("A new one")
                ),
            }

        with patch.object(handler, "_telegram_commands", commands):
            self.test_chat._sync_command_menu()
        menus = self._menus()
        self.assertEqual(len(menus), 2)
        self.assertIn("nuevo", self._commands(menus[-1]))

    def test_a_group_given_in_odoo_reaches_the_menu(self):
        handler = type(self.env["telegram.handler.base"])
        original = handler._telegram_commands

        def commands(this):
            return {
                **original(this),
                "/admin": TelegramCommand(
                    "_m",
                    "internal",
                    builtin=True,
                    access=("res.users", "unlink"),
                    description=_lt("Administer"),
                ),
            }

        with patch.object(handler, "_telegram_commands", commands):
            self.test_chat._sync_command_menu()
            self.assertNotIn("admin", self._commands(self._menus()[-1]))
            self.test_user.write(
                {"group_ids": [Command.link(self.env.ref("base.group_system").id)]}
            )
        self.assertIn("admin", self._commands(self._menus()[-1]))

    def test_disconnecting_leaves_what_anyone_may_run(self):
        self.test_chat._sync_command_menu()
        self.test_binding._revoke("user")
        self.assertEqual(self._commands(self._menus()[-1]), ["cancelar", "ayuda"])

    def test_a_command_brings_the_menu_up_to_date(self):
        with self.mock_api_gateway_post():
            self.env["telegram.router"]._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/cancelar",
                [],
                self.test_partner,
                self.test_user,
            )
        self.assertEqual(len(self._menus()), 1)

    def test_a_bot_of_another_company_offers_its_foreign_user_nothing(self):
        bot = self._bot_of_another_company()
        chat = self.env["telegram.chat"].create(
            {
                "chat_id": "12345",
                "chat_type": "private",
                "bot_id": bot.id,
                "account_id": self.test_account.id,
            }
        )
        self.assertEqual(chat._get_command_menu(), [])

    def test_a_group_chat_has_no_personal_menu(self):
        group = self.env["telegram.chat"].create(
            {"chat_id": "-100777", "chat_type": "group", "bot_id": self.test_bot.id}
        )
        group._sync_command_menu()
        self.assertFalse(self._menus(group))

    def test_registering_the_webhook_publishes_the_menu_of_the_unconnected(self):
        with self.mock_api_gateway_post() as post:
            self.test_bot._publish_default_command_menu()
        payload = post.call_args.kwargs["json"]
        self.assertTrue(post.call_args.args[0].endswith("/setMyCommands"))
        self.assertEqual(
            [entry["command"] for entry in payload["commands"]], ["cancelar", "ayuda"]
        )
        self.assertNotIn("scope", payload)
