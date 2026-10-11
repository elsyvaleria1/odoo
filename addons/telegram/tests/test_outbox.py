from unittest.mock import patch

import psycopg

from odoo.exceptions import AccessError, RetryableJobError

from ..tools import errors
from ..tools import format as tools_format
from .common import TelegramBotTestCase
from odoo.addons.telegram.tools.telegram_client import TelegramClient

_CALL = "odoo.addons.telegram.tools.telegram_client.TelegramClient.call"


class TestFormat(TelegramBotTestCase):
    def test_escape_is_total(self):
        self.assertEqual(
            tools_format.escape("<b>&co</b>"), "&lt;b&gt;&amp;co&lt;/b&gt;"
        )

    def test_odoo_html_becomes_telegram_html(self):
        converted = tools_format.from_odoo_html(
            "<p>Hola <strong>Ana</strong>, <em>mira</em> "
            '<a href="/odoo/project.task/7">esto</a></p>'
            "<ul><li>uno</li><li>dos &amp; tres</li></ul>"
            '<span style="color:red">sin estilo</span><script>x()</script>',
            base_url="https://erp.example.com",
        )
        self.assertIn("<b>Ana</b>", converted)
        self.assertIn("<i>mira</i>", converted)
        self.assertIn(
            '<a href="https://erp.example.com/odoo/project.task/7">esto</a>', converted
        )
        self.assertIn("• uno", converted)
        self.assertIn("dos &amp; tres", converted)
        self.assertIn("sin estilo", converted)
        self.assertNotIn("<span", converted)
        self.assertNotIn("<p>", converted)

    def test_a_relative_link_without_a_base_is_dropped_not_broken(self):
        converted = tools_format.from_odoo_html('<a href="/odoo/x">x</a>')
        self.assertEqual(converted, "x")

    def test_truncate_closes_what_it_leaves_open(self):
        text = "<b>" + "a" * 50 + "</b>"
        cut = tools_format.truncate(text, limit=10)
        self.assertEqual(cut, "<b>" + "a" * 9 + "…</b>")
        self.assertEqual(len(tools_format.plain(cut)), 10)

    def test_truncate_keeps_entities_whole(self):
        cut = tools_format.truncate("&amp;" * 20, limit=5)
        self.assertEqual(cut, "&amp;" * 4 + "…")

    def test_plain_unescapes(self):
        self.assertEqual(tools_format.plain("<b>a &amp; b</b>"), "a & b")


class TestErrorTaxonomy(TelegramBotTestCase):
    def test_classify(self):
        cases = [
            (
                {"error_code": 429, "description": "Too Many Requests: retry after 7"},
                errors.TelegramRetryAfter,
            ),
            (
                {
                    "error_code": 403,
                    "description": "Forbidden: bot was blocked by the user",
                },
                errors.TelegramForbidden,
            ),
            (
                {"error_code": 400, "description": "Bad Request: can't parse entities"},
                errors.TelegramParseError,
            ),
            (
                {"error_code": 400, "description": "Bad Request: chat not found"},
                errors.TelegramNotFound,
            ),
            (
                {
                    "error_code": 400,
                    "description": "Bad Request: group chat was upgraded",
                    "parameters": {"migrate_to_chat_id": -1001},
                },
                errors.TelegramChatMigrated,
            ),
            (
                {"error_code": 502, "description": "Bad Gateway"},
                errors.TelegramUnavailable,
            ),
            (
                {"error_code": 400, "description": "Bad Request: message is too long"},
                errors.TelegramBadRequest,
            ),
        ]
        for body, cls in cases:
            with self.subTest(body=body["description"]):
                self.assertIs(type(errors.classify({"ok": False, **body})), cls)

    def test_retry_after_reads_the_parameter_then_the_text(self):
        self.assertEqual(
            errors.classify(
                {"error_code": 429, "parameters": {"retry_after": 12}}
            ).seconds,
            12,
        )
        self.assertEqual(
            errors.classify(
                {"error_code": 429, "description": "retry after 9"}
            ).seconds,
            9,
        )


class TestOutbox(TelegramBotTestCase):
    def setUp(self):
        super().setUp()
        self.defers = []
        patcher = patch.object(
            type(self.env["ir.job"]),
            "_defer",
            lambda _self, seconds, reason="": self.defers.append((seconds, reason)),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _queued(self, text="<b>Hola</b>"):
        return self.test_bot._queue_text(self.test_chat, text)

    def test_queueing_writes_the_ledger_and_enqueues_one_job(self):
        message = self._queued()

        self.assertEqual(message.state, "outgoing")
        self.assertEqual(message.api_method, "sendMessage")
        self.assertEqual(message.payload["parse_mode"], "HTML")
        jobs = (
            self.env["ir.job"]
            .sudo()
            .search([("identity_key", "=", f"telegram.message:{message.id}")])
        )
        self.assertEqual(len(jobs), 1)

    def test_a_delivered_message_records_its_telegram_id(self):
        message = self._queued()
        with patch(_CALL, return_value={"message_id": 77}) as call:
            message._deliver()

        self.assertEqual(message.state, "sent")
        self.assertEqual(message.msg_uid, "77")
        method, payload = call.call_args.args[:2]
        self.assertEqual(method, "sendMessage")
        self.assertEqual(payload["chat_id"], self.test_chat.chat_id)

    def test_a_conflict_reading_the_token_leaves_the_message_queued(self):
        message = self._queued()
        conflict = psycopg.errors.SerializationFailure("concurrent update")
        with (
            patch.object(
                type(self.test_bot), "_get_telegram_client", side_effect=conflict
            ),
            patch(_CALL) as call,
            self.assertRaises(psycopg.errors.SerializationFailure),
        ):
            message._deliver()

        self.assertFalse(call.called)
        self.assertEqual(message.state, "outgoing")

    def test_a_message_left_sending_is_uncertain_never_resent(self):
        message = self._queued()
        message.sudo().write({"state": "sending"})
        with patch(_CALL) as call:
            message._deliver()

        self.assertFalse(call.called)
        self.assertEqual(message.state, "uncertain")

    def test_flood_control_defers_without_spending_a_retry(self):
        message = self._queued()
        with patch(
            _CALL, side_effect=errors.TelegramRetryAfter(429, "", {"retry_after": 13})
        ):
            message._deliver()

        self.assertEqual(message.state, "outgoing")
        self.assertEqual(self.defers, [(13, "flood control")])

    def test_a_blocked_bot_stops_writing_to_the_chat(self):
        message = self._queued()
        with patch(
            _CALL,
            side_effect=errors.TelegramForbidden(
                403, "Forbidden: bot was blocked by the user"
            ),
        ):
            message._deliver()

        self.assertEqual(message.state, "error")
        self.assertTrue(self.test_chat.bot_blocked)
        second = self._queued()
        with patch(_CALL) as call:
            second._deliver()
        self.assertFalse(call.called)
        self.assertEqual(second.state, "error")

    def test_the_person_writing_again_unblocks_the_chat(self):
        self.test_chat._side_block()
        self.env["telegram.chat"]._acquire_chat(
            self.test_chat.chat_id,
            self.test_bot.id,
            chat_type="private",
            account=self.test_account,
        )
        self.assertFalse(self.test_chat.bot_blocked)

    def test_text_that_does_not_parse_is_resent_plain(self):
        message = self._queued("<b>a &amp; b")
        with patch(
            _CALL,
            side_effect=errors.TelegramParseError(
                400, "Bad Request: can't parse entities"
            ),
        ):
            message._deliver()

        self.assertEqual(message.state, "outgoing")
        self.assertEqual(message.payload["text"], "a & b")
        self.assertNotIn("parse_mode", message.payload)

    def test_a_migrated_group_is_followed(self):
        group = self.env["telegram.chat"].create(
            {"chat_id": "-500", "chat_type": "group", "bot_id": self.test_bot.id}
        )
        message = self.test_bot._queue_text(group, "hola")
        with patch(
            _CALL,
            side_effect=errors.TelegramChatMigrated(
                400, "upgraded", {"migrate_to_chat_id": -100500}
            ),
        ):
            message._deliver()

        supergroup = group.migrated_to_id
        self.assertEqual(supergroup.chat_id, "-100500")
        self.assertEqual(supergroup.chat_type, "supergroup")
        self.assertEqual(group.chat_id, "-500")
        self.assertEqual(message.state, "cancelled")
        follower = self.env["telegram.message"].search(
            [("chat_id", "=", supergroup.id)]
        )
        self.assertEqual(follower.state, "outgoing")
        self.assertEqual(follower.payload["text"], "hola")

    def _open_budget(self):
        return patch.object(
            type(self.env["telegram.message"]),
            "_consume_send_budget",
            return_value=True,
        )

    def test_an_edit_waits_for_its_message_and_names_it(self):
        self.enterContext(self._open_budget())
        original = self._queued()
        edit = self.env["telegram.message"]._queue(
            self.test_bot,
            self.test_chat,
            "editMessageText",
            {"text": "otro", "parse_mode": "HTML"},
            target_id=original.id,
        )
        with patch(_CALL) as call:
            edit._deliver()
        self.assertFalse(call.called)
        self.assertEqual(edit.state, "outgoing")

        with patch(_CALL, return_value={"message_id": 31}):
            original._deliver()
        with patch(_CALL, return_value={"message_id": 31}) as call:
            edit._deliver()
        self.assertEqual(call.call_args.args[1]["message_id"], 31)
        self.assertEqual(edit.state, "sent")
        self.assertFalse(edit.msg_uid)

    def test_a_deletion_answered_true_is_sent(self):
        self.enterContext(self._open_budget())
        original = self._queued()
        with patch(_CALL, return_value={"message_id": 32}):
            original._deliver()
        deletion = self.env["telegram.message"]._queue(
            self.test_bot, self.test_chat, "deleteMessage", {}, target_id=original.id
        )
        with patch(_CALL, return_value=True):
            deletion._deliver()
        self.assertEqual(deletion.state, "sent")

    def test_a_topic_message_names_its_topic(self):
        message = self.test_bot._queue_text(self.test_chat, "hola", thread_uid="7")
        with patch(_CALL, return_value={"message_id": 33}) as call:
            message._deliver()
        self.assertEqual(call.call_args.args[1]["message_thread_id"], 7)

    def test_an_unreachable_telegram_is_retried(self):
        message = self._queued()
        raised = None
        with patch(_CALL, side_effect=errors.TelegramUnavailable(0, "timeout")):
            try:
                message._deliver()
            except RetryableJobError as error:
                raised = error

        self.assertIsNotNone(raised)
        self.assertEqual(message.state, "outgoing")
        self.assertEqual(message.attempts, 1)

    def test_an_exhausted_budget_defers_without_calling(self):
        message = self._queued()
        with (
            patch.object(type(message), "_consume_send_budget", return_value=False),
            patch(_CALL) as call,
        ):
            message._deliver()

        self.assertFalse(call.called)
        self.assertEqual(self.defers, [(1, "rate limit")])

    def test_the_chat_budget_is_one_per_second(self):
        first, second = self._queued(), self._queued()
        self.assertTrue(first._consume_send_budget())
        self.assertFalse(second._consume_send_budget())

    def test_only_a_writer_resends(self):
        message = self._queued()
        message.sudo().write({"state": "uncertain"})
        with self.assertRaises(AccessError):
            message.with_user(self.test_user).action_resend()
        message.action_resend()
        self.assertEqual(message.state, "outgoing")

    def test_a_file_is_sent_as_its_kind(self):
        image = self.env["ir.attachment"].create(
            {"name": "a.png", "raw": b"\x89PNG\r\n\x1a\n", "mimetype": "image/png"}
        )
        message = self.test_bot._queue_file(
            self.test_chat, image, caption="<b>foto</b>"
        )
        self.assertEqual(message.api_method, "sendPhoto")
        with patch(_CALL, return_value={"message_id": 5}) as call:
            message._deliver()
        self.assertEqual(call.call_args.kwargs["files"]["photo"][0], "a.png")
        self.assertEqual(message.state, "sent")

    def test_the_client_types_a_refusal(self):
        client = self.test_bot._get_telegram_client()
        with (
            patch.object(
                client._client,
                "post",
                return_value={
                    "body": {"ok": False, "error_code": 403, "description": "Forbidden"}
                },
            ),
            self.assertRaises(errors.TelegramForbidden),
        ):
            client.call("sendMessage", {"chat_id": "1", "text": "x"})
        self.assertIsInstance(client, TelegramClient)


class TestStillWanted(TelegramBotTestCase):
    def test_a_message_no_longer_wanted_is_cancelled_unsent(self):
        message = self.test_bot._queue_text(self.test_chat, "x")
        with (
            patch.object(type(message), "_still_wanted", return_value=False),
            patch(_CALL) as call,
        ):
            message._deliver()
        self.assertFalse(call.called)
        self.assertEqual(message.state, "cancelled")
