from odoo.libs.json import dumps_bytes as json_dumps_bytes

from .common import TelegramBotTestCase
from odoo.addons.integration.tests.common import open_admission
from odoo.addons.telegram.tools import replay


class TestReplayGuard(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        replay.end_update()
        self.addCleanup(replay.end_update)

    def test_a_replayed_handler_does_not_send_twice(self):
        calls = []

        def _call():
            calls.append(1)
            return {"ok": True, "result": {"message_id": 1}}

        replay.begin_update((self.test_bot.id, 4242))
        first = replay.remember("sendMessage", {"text": "hola"}, _call)

        replay.begin_update((self.test_bot.id, 4242))
        second = replay.remember("sendMessage", {"text": "hola"}, _call)

        self.assertEqual(
            len(calls),
            1,
            "retrying() re-runs the endpoint after a rollback; the message was "
            "already delivered and must not be sent again",
        )
        self.assertEqual(first, second)

    def test_a_diverging_replay_is_really_sent(self):
        calls = []

        def _call(text):
            def _inner():
                calls.append(text)
                return {"ok": True, "result": {"message_id": len(calls)}}

            return _inner

        replay.begin_update((self.test_bot.id, 99))
        replay.remember("sendMessage", {"text": "first"}, _call("first"))

        replay.begin_update((self.test_bot.id, 99))
        replay.remember("sendMessage", {"text": "different"}, _call("different"))

        self.assertEqual(calls, ["first", "different"])

    def test_a_new_update_starts_from_a_clean_slate(self):
        calls = []

        def _call():
            calls.append(1)
            return {"ok": True}

        replay.begin_update((self.test_bot.id, 1))
        replay.remember("sendMessage", {"text": "x"}, _call)

        replay.begin_update((self.test_bot.id, 2))
        replay.remember("sendMessage", {"text": "x"}, _call)

        self.assertEqual(len(calls), 2)

    def test_outside_a_scope_nothing_is_cached(self):
        calls = []

        def _call():
            calls.append(1)
            return {"ok": True}

        replay.remember("sendMessage", {"text": "x"}, _call)
        replay.remember("sendMessage", {"text": "x"}, _call)

        self.assertEqual(len(calls), 2)

    def test_send_message_reuses_the_first_answer_on_a_replay(self):
        response = self.mock_telegram_response(success=True, result={"message_id": 7})

        with self.mock_api_gateway_post(response) as mock_post:
            replay.begin_update((self.test_bot.id, 7000))
            self.test_bot.send_message(self.test_chat.chat_id, "hola")

            replay.begin_update((self.test_bot.id, 7000))
            self.test_bot.send_message(self.test_chat.chat_id, "hola")

            self.assertEqual(
                mock_post.call_count,
                1,
                "the second attempt must not reach the Telegram API",
            )


class TestUpdateReceipt(TelegramBotTestCase):

    def _admission(self, data):
        receiver = self.test_bot._get_or_create_webhook_receiver()
        return open_admission(
            receiver, json_dumps_bytes(data), "update", path="/telegram/webhook/x"
        )

    def test_the_receiver_names_the_update_id(self):
        admission = self._admission({"update_id": 1001, "message": {}})
        self.assertEqual(admission.exchange.event_id_external, "1001")

    def test_an_update_without_an_id_claims_nothing(self):
        admission = self._admission({"message": {}})
        self.assertFalse(admission.exchange.event_id_external)
        self._admission({"message": {}})

    def test_a_redelivery_is_refused_at_admission(self):
        from odoo.addons.integration.tools.admission import Refused

        self._admission({"update_id": 1002, "message": {}})
        with self.assertRaises(Refused) as caught:
            self._admission({"update_id": 1002, "message": {}})
        self.assertEqual(caught.exception.error_code, "duplicate_event")
