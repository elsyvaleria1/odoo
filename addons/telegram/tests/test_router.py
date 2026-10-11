from unittest.mock import patch

from .common import TelegramBotTestCase


class FakeHandler:
    """What the router asks a handler, and a record of what it was told."""

    def __init__(
        self, name, *, flow=(), intakes=(), claims=False, prefixes=(), priority=100
    ):
        self._name = name
        self._description = name
        self._telegram_intake_priority = priority
        self.flow, self.intakes, self.claims, self.prefixes = (
            set(flow),
            set(intakes),
            claims,
            prefixes,
        )
        self.seen = []

    def __bool__(self):
        return False

    def _telegram_commands(self):
        return {}

    def _telegram_callback_prefixes(self):
        return self.prefixes

    def _feature_enabled(self, bot):
        return True

    def _owns_flow(self, chat):
        return chat._flow_is_open() and chat.flow_step in self.flow

    def _claims_message(self, bot, chat, message, partner, internal_user):
        return self.claims

    def _accepts_idle(self, bot, chat, kind, message, partner, internal_user):
        return kind in self.intakes

    def _telegram_intake_command(self, bot, chat, kind):
        return None

    def _telegram_intake_label(self, bot, chat, kind):
        return self._name

    def _on_unhandled_message(self, bot, chat, message, partner, internal_user):
        return False

    def _on_message(self, bot, chat, message, partner, internal_user):
        self.seen.append(message.get("text") or "media")
        return True

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        self.seen.append(callback_query["data"])
        return True

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        return []


class TestRouterPrecedence(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.router = self.env["telegram.router"]

    def _route(self, handlers, text="hola", **message):
        update = {"text": text, **message}
        with (
            patch.object(
                type(self.router), "_handlers", lambda this, bot=None: handlers
            ),
            patch.object(
                type(self.router),
                "_flow_owner",
                lambda this, chat: next(
                    (h for h in handlers if h._owns_flow(chat)), None
                ),
            ),
            self.mock_api_gateway_post() as post,
        ):
            self.router._dispatch_free_message(
                self.test_bot, self.test_chat, update, self.test_partner, self.test_user
            )
        return post

    def test_the_flow_owner_takes_the_chats_free_text(self):
        self.test_chat._flow_start("telegram.handler.base", "owned_step")
        owner = FakeHandler("telegram.handler.owner", flow={"owned_step"})
        idle = FakeHandler("telegram.handler.idle", intakes={"text"}, priority=1)
        claimer = FakeHandler("telegram.handler.claimer", claims=True)

        self._route([idle, claimer, owner])

        self.assertEqual(owner.seen, ["hola"])
        self.assertEqual(idle.seen + claimer.seen, [])

    def test_a_claim_comes_before_the_idle_intake(self):
        idle = FakeHandler("telegram.handler.idle", intakes={"text"}, priority=1)
        claimer = FakeHandler("telegram.handler.claimer", claims=True)

        self._route([idle, claimer])

        self.assertEqual(claimer.seen, ["hola"])
        self.assertEqual(idle.seen, [])

    def test_two_idle_intakes_ask_the_person_which(self):
        late = FakeHandler("telegram.handler.late", intakes={"text"}, priority=50)
        early = FakeHandler("telegram.handler.early", intakes={"text"}, priority=10)

        post = self._route([late, early])

        self.assertEqual(late.seen + early.seen, [])
        markup = post.call_args.kwargs["json"]["reply_markup"]
        self.assertLess(
            markup.index("tg_in:telegram.handler.early"),
            markup.index("tg_in:telegram.handler.late"),
        )

    def test_the_bot_names_its_idle_intake(self):
        late = FakeHandler("telegram.handler.late", intakes={"text"}, priority=50)
        early = FakeHandler("telegram.handler.early", intakes={"text"}, priority=10)

        with patch.object(
            type(self.test_bot),
            "_idle_handler_name",
            lambda this, kind: "telegram.handler.late",
        ):
            self._route([late, early])

        self.assertEqual(late.seen, ["hola"])

    def test_the_intake_is_per_kind(self):
        text = FakeHandler("telegram.handler.text", intakes={"text"})
        voice = FakeHandler("telegram.handler.voice", intakes={"voice"})

        self._route([text, voice], text="", voice={"file_id": "x"})

        self.assertEqual(voice.seen, ["media"])
        self.assertEqual(text.seen, [])

    def test_nobody_taking_it_answers_with_help(self):
        post = self._route([])
        self.assertIn("/ayuda", post.call_args.kwargs["json"]["text"])

    def test_a_button_goes_to_its_longest_prefix(self):
        short = FakeHandler("telegram.handler.short", prefixes=("fin",))
        long = FakeHandler("telegram.handler.long", prefixes=("fin_period_",))
        query = self.mock_telegram_callback_query(
            chat_id=self.test_chat.chat_id, callback_data="fin_period_3"
        )
        with (
            patch.object(
                type(self.router), "_handlers", lambda this, bot=None: [short, long]
            ),
            self.mock_api_gateway_post() as post,
            self.mock_rate_limiter(),
        ):
            self.router._dispatch_callback_query(self.test_bot, query)

        self.assertEqual(long.seen, ["fin_period_3"])
        self.assertEqual(short.seen, [])
        self.assertTrue(
            any("answerCallbackQuery" in call.args[0] for call in post.call_args_list)
        )


class TestServiceUpdates(TelegramBotTestCase):
    def test_blocking_the_bot_stops_sends_and_unblocking_resumes(self):
        router = self.env["telegram.router"]
        update = {
            "chat": {"id": int(self.test_chat.chat_id), "type": "private"},
            "new_chat_member": {"status": "kicked"},
        }
        router._dispatch_my_chat_member(self.test_bot, update)
        self.assertTrue(self.test_chat.bot_blocked)

        update["new_chat_member"]["status"] = "member"
        router._dispatch_my_chat_member(self.test_bot, update)
        self.assertFalse(self.test_chat.bot_blocked)

    def test_an_edit_updates_the_ledger(self):
        router = self.env["telegram.router"]
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id, text="hola", message_id=77
        )
        with self.mock_api_gateway_post(), self.mock_rate_limiter():
            router._dispatch_message(self.test_bot, message)
        router._dispatch_edited_message(
            self.test_bot, {**message, "text": "hola, corregido"}
        )
        ledger = self.env["telegram.message"].search(
            [("msg_uid", "=", "77"), ("message_type", "=", "inbound")]
        )
        self.assertEqual(ledger.text, "hola, corregido")
