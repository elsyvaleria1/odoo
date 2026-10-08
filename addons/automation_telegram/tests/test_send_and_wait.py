import base64
from contextlib import suppress
from datetime import timedelta
from unittest.mock import patch

import psycopg

from odoo import fields
from odoo.exceptions import UserError

from odoo.addons.automation.tests.test_workflow_dag import link
from odoo.addons.automation_telegram.models.automation_telegram_wait import (
    MAX_ATTEMPTS,
    _lost_to_concurrency,
)
from odoo.addons.telegram.models.telegram_bot import TelegramBot
from odoo.addons.telegram.tests.common import TelegramBotTestCase

ASK_PHOTO = (
    "chat = env['telegram.chat'].browse(%d)\n"
    "runtime_line._telegram_send_and_wait(chat, 'Send me a selfie', 'selfie', "
    "accept=('photo', 'document'))"
)
SAVE_ANSWER = (
    "answer = steps.ask.output['answer']\n"
    "record.write({'ref': '%s:%s' % (answer['kind'], len(answer['attachment_ids']))})"
)
JPEG = b"\xff\xd8\xff\xe0 a selfie"


class TestSendAndWait(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model_partner = cls.env["ir.model"]._get("res.partner")
        cls.automation = cls.env["automation.rule"].create(
            {
                "name": "Selfie",
                "model_id": cls.model_partner.id,
                "trigger": "on_hand",
                "create_runtime_instance": True,
            }
        )
        cls.ask = cls._action("ask", ASK_PHOTO % cls.test_chat.id, step_key="ask")
        cls.save = cls._action("save", SAVE_ANSWER, step_key="save")
        cls.remind = cls._action("remind", step_key="remind")
        link(cls.env, cls.ask, cls.save, condition="event", event_code="selfie")
        link(
            cls.env,
            cls.ask,
            cls.remind,
            condition="no_event",
            event_code="selfie",
            delay=1,
            delay_unit="day",
        )

    @classmethod
    def _action(cls, name, code="pass", **kw):
        return cls.env["ir.actions.server"].create(
            {
                "name": name,
                "model_id": cls.model_partner.id,
                "state": "code",
                "code": code,
                "automation_rule_id": cls.automation.id,
                "usage": "automation",
                **kw,
            }
        )

    def _run(self):
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "res_model": "res.partner",
                "res_id": self.test_partner.id,
            }
        )
        runtime.action_start()
        runtime.action_run_all()
        return runtime

    def _line(self, runtime, action):
        return runtime.line_ids.filtered(lambda step: step.action_id == action)

    def _wait(self, runtime):
        return self.env["automation.telegram.wait"].search(
            [("runtime_id", "=", runtime.id)]
        )

    def _send(self, message_id=50, **content):
        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id, message_id=message_id
        )
        message.pop("text")
        message.update(content or {"text": "hello"})
        with self.mock_api_gateway_post() as post, self.mock_rate_limiter():
            self.env["telegram.router"]._dispatch_message(self.test_bot, message)
        return post

    def _photo(self, **extra):
        return {
            "photo": [
                {"file_id": "small", "width": 90, "height": 90},
                {"file_id": "large", "width": 1280, "height": 1280},
            ],
            **extra,
        }

    def _deliver(self, content=JPEG):
        with patch.object(
            TelegramBot,
            "get_file",
            return_value={"content": content, "file_path": "photos/file_7.jpg"},
        ) as got:
            self.env["automation.telegram.wait"]._cron_deliver_answers()
        return got

    def _queued_texts(self):
        return self.env["telegram.message"].search(
            [
                ("chat_id", "=", self.test_chat.id),
                ("message_type", "=", "outbound"),
                ("api_method", "=", "sendMessage"),
            ]
        )

    def test_asking_queues_the_question_and_the_run_waits_for_the_answer(self):
        runtime = self._run()

        wait = self._wait(runtime)
        self.assertEqual(wait.state, "waiting")
        self.assertEqual(wait.accepted_kinds, "photo,document")
        self.assertEqual(wait.prompt_message_id.text, "Send me a selfie")
        self.assertEqual(self._line(runtime, self.ask).state, "done")
        self.assertEqual(self._line(runtime, self.save).state, "waiting")
        self.assertEqual(self._line(runtime, self.remind).state, "scheduled")
        self.assertEqual(runtime.state, "waiting_resume")
        self.assertEqual(
            self._line(runtime, self.ask).output["telegram_wait_id"], wait.id
        )

    def test_a_photo_answers_and_the_dispatcher_resumes_the_run(self):
        runtime = self._run()
        wait = self._wait(runtime)

        self._send(**self._photo())

        self.assertEqual(wait.state, "received")
        self.assertEqual(wait.reply_kind, "photo")
        self.assertEqual(wait.reply_payload["files"], [["large", "photo.jpg"]])
        reaction = self.env["telegram.message"].search(
            [
                ("chat_id", "=", self.test_chat.id),
                ("api_method", "=", "setMessageReaction"),
            ]
        )
        self.assertEqual(len(reaction), 1)
        # recording the answer runs nothing: the sender is not who resumes
        self.assertEqual(self._line(runtime, self.save).state, "waiting")

        got = self._deliver()

        got.assert_called_once_with("large")
        self.assertEqual(wait.state, "delivered")
        self.assertEqual(wait.attachment_ids.name, "file_7.jpg")
        self.assertEqual(wait.attachment_ids.res_model, "automation.runtime")
        self.assertEqual(wait.attachment_ids.res_id, runtime.id)
        self.assertEqual(base64.b64decode(wait.attachment_ids.datas), JPEG)
        answer = self._line(runtime, self.ask).output["answer"]
        self.assertEqual(answer["attachment_ids"], wait.attachment_ids.ids)
        self.assertEqual(answer["chat_id"], self.test_chat.id)
        self.assertEqual(self._line(runtime, self.save).state, "done")
        self.assertEqual(self._line(runtime, self.remind).state, "skipped")
        self.assertEqual(runtime.state, "done")
        self.assertEqual(self.test_partner.ref, "photo:1")

    def test_a_message_of_another_kind_is_left_to_the_bot(self):
        runtime = self._run()

        post = self._send(text="hola")

        self.assertEqual(self._wait(runtime).state, "waiting")
        self.assertTrue(
            any("sendMessage" in call.args[0] for call in post.call_args_list),
            "the bot answers a text as if no question were open",
        )

    def test_a_reply_of_the_wrong_kind_says_what_answers(self):
        runtime = self._run()
        wait = self._wait(runtime)
        wait.prompt_message_id.msg_uid = "40"
        before = self._queued_texts()

        self._send(text="no selfie today", reply_to_message={"message_id": 40})

        self.assertEqual(wait.state, "waiting")
        notice = self._queued_texts() - before
        self.assertEqual(len(notice), 1)
        self.assertIn("a photo", notice.text)

    def test_a_reply_answers_its_own_question_among_several(self):
        first = self._run()
        second = self._run()
        self._wait(first).prompt_message_id.msg_uid = "40"
        self._wait(second).prompt_message_id.msg_uid = "41"

        self._send(**self._photo(reply_to_message={"message_id": 40}))

        self.assertEqual(self._wait(first).state, "received")
        self.assertEqual(self._wait(second).state, "waiting")

    def test_without_a_reply_the_latest_question_is_answered(self):
        first = self._run()
        second = self._run()

        self._send(**self._photo())

        self.assertEqual(self._wait(first).state, "waiting")
        self.assertEqual(self._wait(second).state, "received")

    def test_a_question_out_of_the_senders_reach_leaves_the_message_to_the_bot(self):
        runtime = self._run()
        runtime.company_ids = self.env["res.company"].create({"name": "Elsewhere"})

        post = self._send(**self._photo())

        self.assertEqual(self._wait(runtime).state, "waiting")
        self.assertTrue(
            any("sendMessage" in call.args[0] for call in post.call_args_list)
        )

    def test_a_cancelled_run_no_longer_takes_answers(self):
        runtime = self._run()
        runtime.action_cancel()

        self._send(**self._photo())
        self._deliver()

        self.assertEqual(self._wait(runtime).state, "cancelled")

    def test_an_answer_after_the_reminder_still_resumes_the_run(self):
        runtime = self._run()
        remind = self._line(runtime, self.remind)
        self._line(runtime, self.ask).date_settled -= timedelta(days=2)
        remind.date_resume = self.env.cr.now()
        self.env["automation.runtime"]._resume_waiting_executions()
        self.assertEqual(remind.state, "done")

        self._send(**self._photo())
        self._deliver()

        self.assertEqual(self._line(runtime, self.save).state, "done")
        self.assertEqual(runtime.state, "done")

    def _retry_delays(self, before):
        """The minutes from `before` of the delivery job's triggers since."""
        cron = self.env.ref("automation_telegram.ir_cron_deliver_answers")
        triggers = self.env["ir.cron.trigger"].search(
            [("cron_id", "=", cron.id), ("call_at", ">", before)], order="call_at"
        )
        return [round((t.call_at - before).total_seconds() / 60) for t in triggers]

    def test_a_file_telegram_withholds_is_retried_then_reported(self):
        runtime = self._run()
        self._send(**self._photo())
        wait = self._wait(runtime)

        with patch.object(TelegramBot, "get_file", return_value=False):
            for _attempt in range(MAX_ATTEMPTS):
                self.env["automation.telegram.wait"]._cron_deliver_answers()

        self.assertEqual(wait.state, "error")
        self.assertEqual(wait.attempts, MAX_ATTEMPTS)
        self.assertFalse(wait.attachment_ids)
        self.assertEqual(self._line(runtime, self.save).state, "waiting")
        self.assertIn("could not be delivered", runtime.message_ids[:1].body or "")

    def test_a_failed_delivery_backs_off(self):
        runtime = self._run()
        self._send(**self._photo())
        before = fields.Datetime.now()

        with patch.object(TelegramBot, "get_file", return_value=False):
            for _attempt in range(3):
                self.env["automation.telegram.wait"]._cron_deliver_answers()

        self.assertEqual(self._wait(runtime).attempts, 3)
        self.assertEqual(self._retry_delays(before), [1, 2, 4])

    def test_a_transaction_left_aborted_is_retried_in_a_minute(self):
        first, second = self._run(), self._run()
        self._send(message_id=50, **self._photo())
        self._wait(first).prompt_message_id.msg_uid = "60"
        self._send(message_id=61, **self._photo(reply_to_message={"message_id": 60}))
        self.assertEqual(
            (self._wait(first) | self._wait(second)).mapped("state"),
            ["received", "received"],
        )
        cr = self.env.cr

        def poisoned(bot, file_id):
            # what a step does when it catches a serialization failure and
            # carries on: the transaction is left aborted
            with suppress(psycopg.errors.DivisionByZero):
                cr.execute("SELECT 1 / 0")
            return {"content": JPEG, "file_path": "photos/file_7.jpg"}

        before = fields.Datetime.now()
        with patch.object(TelegramBot, "get_file", poisoned):
            delivered = self.env["automation.telegram.wait"]._cron_deliver_answers()

        self.assertEqual(delivered, 0)
        waits = (self._wait(first) | self._wait(second)).sorted("id")
        self.assertEqual(waits.mapped("state"), ["received", "received"])
        self.assertEqual(
            waits.mapped("attempts"), [1, 0], "the job stops at the lost one"
        )
        self.assertIn("aborted", waits[0].error_message)
        self.assertEqual(self._retry_delays(before), [1])

        self._deliver()

        self.assertEqual(waits.mapped("state"), ["delivered", "delivered"])
        self.assertEqual((first | second).mapped("state"), ["done", "done"])

    def test_a_lost_transaction_is_seen_through_the_error_that_follows(self):
        try:
            try:
                raise psycopg.errors.SerializationFailure("concurrent update")
            except psycopg.errors.SerializationFailure:
                raise ValueError("what the step said instead") from None
        except ValueError as masked:
            # `from None` hides the cause from tracebacks, not from __context__
            self.assertTrue(_lost_to_concurrency(masked))
        self.assertTrue(
            _lost_to_concurrency(psycopg.errors.InFailedSqlTransaction("aborted"))
        )
        self.assertFalse(_lost_to_concurrency(ValueError("no file")))

    def test_asking_needs_an_edge_for_the_event(self):
        self.ask.code = (
            "chat = env['telegram.chat'].browse(%d)\n"
            "runtime_line._telegram_send_and_wait(chat, 'Hi', 'nobody_listens')"
        ) % self.test_chat.id

        runtime = self._run()

        line = self._line(runtime, self.ask)
        self.assertEqual(line.state, "error")
        self.assertIn("nobody_listens", line.error_message)
        self.assertFalse(self._wait(runtime))

    def test_asking_refuses_a_group_chat(self):
        group = self.env["telegram.chat"].create(
            {"chat_id": "-100", "chat_type": "group", "bot_id": self.test_bot.id}
        )
        line = self._run().line_ids[:1]
        line.state = "in_progress"

        with self.assertRaises(UserError):
            line._telegram_send_and_wait(group, "Hi", "selfie", accept="photo")

    def test_asking_refuses_an_unknown_kind(self):
        line = self._line(self._run(), self.ask)
        line.state = "in_progress"

        with self.assertRaises(UserError):
            line._telegram_send_and_wait(
                self.test_chat, "Hi", "selfie", accept=("sticker",)
            )
