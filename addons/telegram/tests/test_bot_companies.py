from contextlib import contextmanager
from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged

from .common import TelegramBotTestCase
from odoo.addons.telegram.models.telegram_bot import TelegramBot
from odoo.addons.telegram.models.telegram_router import ForeignSender
from odoo.addons.telegram.tools.authority import in_bot_company
from odoo.addons.telegram.tools.dispatch import TelegramCommand


class BotCompaniesCase(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.main = cls.env.company
        cls.other = cls.env["res.company"].create({"name": "TG Served Company"})
        cls.test_bot.company_ids = [Command.link(cls.other.id)]
        cls.test_user.write(
            {
                "company_ids": [Command.link(cls.other.id)],
                "company_id": cls.main.id,
            }
        )
        cls.router = cls.env["telegram.router"]
        cls.handler = type(cls.env["telegram.handler.base"])

    @contextmanager
    def started(self, company="choose", starts_flow=False):
        original = self.handler._telegram_commands
        runs = []

        def commands(this):
            return {
                **original(this),
                "/empezar": TelegramCommand(
                    "_test_start_command",
                    "internal",
                    builtin=True,
                    starts_flow=starts_flow,
                    company=company,
                ),
            }

        def run(this, bot, chat, args, partner=False, internal_user=False):
            runs.append((this.env.company, bot._acting_company(), args))
            if starts_flow:
                this._flow_start(chat, "step")

        with (
            patch.object(self.handler, "_telegram_commands", commands),
            patch.object(self.handler, "_test_start_command", run, create=True),
        ):
            yield runs

    def _sender(self):
        return self.router._as_sender(
            self.test_user, self.test_bot, self.test_chat, self.test_partner
        )

    def _dispatch(self, command, args=()):
        router, bot, chat, partner = self._sender()
        with patch.object(TelegramBot, "send_message") as send:
            router._dispatch_command(
                bot, chat, command, list(args), partner, self.test_user
            )
        return send

    def _press(self, data):
        query = self.mock_telegram_callback_query(callback_data=data)
        with (
            self.mock_rate_limiter(),
            patch.object(TelegramBot, "send_message") as send,
            patch.object(TelegramBot, "answer_callback_query"),
            patch.object(TelegramBot, "edit_message_reply_markup"),
        ):
            self.router._dispatch_callback_query(self.test_bot, query)
        return send


@tagged("post_install", "-at_install")
class TestBotCompanies(BotCompaniesCase):
    def test_a_bot_always_serves_its_own_company(self):
        bot = self._bot_of_another_company("Owned Bot")
        owner = bot.company_id
        self.assertEqual(bot.company_ids, owner)

        bot.company_id = self.main
        self.assertEqual(bot.company_ids, self.main)

        bot.company_ids = [Command.link(self.other.id)]
        bot.company_id = owner
        self.assertEqual(bot.company_ids, self.main | self.other | owner)

        bot.company_ids = [Command.set(self.other.ids)]
        self.assertEqual(bot.company_ids, self.other | owner)

    def test_a_member_of_a_served_company_is_admitted(self):
        self.test_bot.write(
            {"company_id": self.other.id, "company_ids": [Command.set(self.other.ids)]}
        )
        self.test_user.company_ids = [Command.set(self.main.ids)]
        with self.assertRaises(ForeignSender):
            self._sender()

        self.test_bot.company_ids = [Command.link(self.main.id)]
        router, _bot, _chat, _partner = self._sender()
        self.assertEqual(router.env.companies, self.main)

    def test_the_sender_acts_in_every_served_company_of_theirs(self):
        router, bot, _chat, _partner = self._sender()
        self.assertEqual(router.env.companies, self.main | self.other)
        self.assertEqual(router.env.company, self.main)
        self.assertEqual(bot._acting_company(), self.main)

    def test_a_command_starting_something_asks_for_the_company(self):
        with self.started() as runs:
            send = self._dispatch("/empezar", ["x"])
        self.assertFalse(runs)
        buttons = [
            row[0]["callback_data"]
            for row in send.call_args.kwargs["reply_markup"]["inline_keyboard"]
            if row
        ]
        self.assertEqual(buttons, [f"tg_co:{self.main.id}", f"tg_co:{self.other.id}"])

        with self.started() as runs:
            self._press(f"tg_co:{self.other.id}")
        self.assertEqual(runs, [(self.other, self.other, ["x"])])

    def test_a_company_the_person_lost_is_no_choice(self):
        with self.started():
            self._dispatch("/empezar")
        self.test_user.company_ids = [Command.unlink(self.other.id)]

        with self.started() as runs:
            send = self._press(f"tg_co:{self.other.id}")

        self.assertFalse(runs)
        self.assertIn("no longer open", send.call_args.args[1])

    def test_one_possible_company_runs_at_once_in_it(self):
        self.test_bot.company_ids = [Command.set(self.main.ids)]
        with self.started() as runs:
            self._dispatch("/empezar")
        self.assertEqual(runs, [(self.main, self.main, [])])

    def test_a_command_of_any_company_never_asks(self):
        with self.started(company="any") as runs:
            self._dispatch("/empezar")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0][0], self.main)

    def test_the_flow_stays_in_the_company_chosen(self):
        with self.started(starts_flow=True):
            self._dispatch("/empezar")
            self._press(f"tg_co:{self.other.id}")
        self.assertEqual(self.test_chat.flow_company_id, self.other)

        router, bot, _chat, partner = self._sender()
        self.assertEqual(router.env.companies, self.other)
        self.assertEqual(bot._acting_company(), self.other)
        self.assertEqual(partner.env.context["telegram_company_id"], self.other.id)

        self.test_chat._flow_end()
        self.assertFalse(self.test_chat.flow_company_id)
        router, _bot, _chat, _partner = self._sender()
        self.assertEqual(router.env.companies, self.main | self.other)

    def test_the_buttons_of_the_chosen_command_stay_in_its_company(self):
        with self.started():
            self._dispatch("/empezar")
            self._press(f"tg_co:{self.other.id}")
        handler = self.env["telegram.handler.base"]

        company = self.router._command_company(
            self.test_bot, self.test_chat, handler, self.test_user
        )
        self.assertEqual(company, self.other)
        self.assertFalse(
            self.router._command_company(
                self.test_bot,
                self.test_chat,
                self.env["mixin.telegram.handler"],
                self.test_user,
            )
        )

    def test_a_partner_s_command_is_pinned_without_their_companies(self):
        public = self.env.ref("base.public_user")
        bot = self.test_bot.with_user(public)
        (pinned,) = self.router._pin_company(self.other, bot)
        self.assertEqual(pinned._acting_company(), self.other)
        partners = in_bot_company(pinned.env["res.partner"], pinned)
        self.assertEqual(partners.env.context["allowed_company_ids"], self.other.ids)

    def test_a_command_available_in_one_company_acts_there_without_asking(self):
        command = self.env["telegram.command"]._for_name("/empezar")
        command.company_ids = self.other
        with self.started() as runs:
            send = self._dispatch("/empezar")
        self.assertFalse(send.called)
        self.assertEqual(runs, [(self.other, self.other, [])])

    def test_a_command_of_no_company_of_theirs_is_refused_and_not_offered(self):
        third = self.env["res.company"].create({"name": "TG Third Company"})
        self.test_bot.company_ids = [Command.link(third.id)]
        command = self.env["telegram.command"]._for_name("/empezar")
        command.company_ids = third
        with self.started() as runs:
            send = self._dispatch("/empezar")
            menu = [
                entry
                for entry, _spec in self.router._available_commands(
                    self.test_bot, self.test_chat, self.test_partner, self.test_user
                )
            ]
        self.assertFalse(runs)
        self.assertIn("permission", send.call_args.args[1])
        self.assertNotIn("/empezar", menu)

        command.company_ids = False
        with self.started():
            menu = [
                entry
                for entry, _spec in self.router._available_commands(
                    self.test_bot, self.test_chat, self.test_partner, self.test_user
                )
            ]
        self.assertIn("/empezar", menu)


@tagged("post_install", "-at_install")
class TestIdleIntake(BotCompaniesCase):
    CONTACT = {"message_id": 7, "contact": {"phone_number": "+5215550000"}}

    @contextmanager
    def intake(self, command="/empezar", **declared):
        runs = []

        def on_message(this, bot, chat, message, partner, internal_user):
            runs.append(this.env.company)
            return True

        with (
            self.started(**declared),
            patch.object(
                self.handler,
                "_telegram_intake_command",
                lambda this, bot, chat, kind: command,
                create=True,
            ),
            patch.object(self.handler, "_on_message", on_message),
        ):
            yield runs

    def _send(self):
        router, bot, chat, partner = self._sender()
        with patch.object(TelegramBot, "send_message") as send:
            router._dispatch_free_message(
                bot, chat, dict(self.CONTACT), partner, self.test_user
            )
        return send

    def test_an_idle_message_asks_the_company_of_its_command(self):
        with self.intake() as runs:
            send = self._send()
        self.assertFalse(runs)
        self.assertIn("/empezar", send.call_args.args[1])

        with self.intake() as runs:
            self._press(f"tg_co:{self.other.id}")
        self.assertEqual(runs, [self.other])

    def test_an_idle_message_is_not_taken_from_who_may_not_run_its_command(self):
        command = self.env["telegram.command"]._for_name("/empezar")
        third = self.env["res.company"].create({"name": "TG Intake Third"})
        self.test_bot.company_ids = [Command.link(third.id)]
        command.company_ids = third
        with self.intake() as runs:
            send = self._send()
        self.assertFalse(runs)
        self.assertIn("only process commands", send.call_args.args[1])

    def test_what_nothing_took_may_still_be_answered(self):
        answered = []

        def unhandled(this, bot, chat, message, partner, internal_user):
            answered.append(message["message_id"])
            return True

        with patch.object(self.handler, "_on_unhandled_message", unhandled):
            router, bot, chat, partner = self._sender()
            with patch.object(TelegramBot, "send_message") as send:
                router._dispatch_free_message(
                    bot,
                    chat,
                    {"message_id": 8, "text": "hola"},
                    partner,
                    self.test_user,
                )
        self.assertEqual(answered, [8])
        self.assertFalse(send.called)
