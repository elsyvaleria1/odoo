from datetime import timedelta

import psycopg
from freezegun import freeze_time

from odoo import Command, fields
from odoo.db import db_connect
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import (
    JsonRpcException,
    TransactionCase,
    new_test_user,
    tagged,
)
from odoo.tools.misc import mute_logger

from odoo.addons.im_livechat.tests.common import TestImLivechatCommon
from odoo.addons.mail.tests.common import MailCommon
from odoo.addons.mail.tools.discuss import Store


class LivechatRouteCase(TestImLivechatCommon, MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chatbot = cls._create_chatbot("Scope Bot")
        cls.foreign_chatbot = cls._create_chatbot("Foreign Bot", active=False)
        cls.env["im_livechat.channel.rule"].create(
            {"channel_id": cls.livechat_channel.id, "chatbot_script_id": cls.chatbot.id}
        )

    @classmethod
    def _create_chatbot(cls, title, active=True):
        return cls.env["chatbot.script"].create(
            {
                "title": title,
                "active": active,
                "script_step_ids": [
                    Command.create(
                        {"step_type": "text", "message": f"{title} says hello"}
                    ),
                    Command.create(
                        {
                            "step_type": "free_input_single",
                            "message": f"{title} secret question",
                        }
                    ),
                    Command.create({"step_type": "text", "message": f"{title} bye"}),
                ],
            }
        )

    def _start_session(self, chatbot=None):
        params = {"channel_id": self.livechat_channel.id}
        if chatbot:
            params["chatbot_script_id"] = chatbot.id
        data = self.call_jsonrpc("/im_livechat/get_session", params)
        return self.env["discuss.channel"].browse(data["channel_id"])

    def _new_visitor(self):
        self.authenticate(None, None)
        self.opener.cookies.clear()

    def _bot_messages(self, channel, chatbot):
        channel.invalidate_recordset()
        return channel.message_ids.filtered(
            lambda m: m.author_id == chatbot.operator_partner_id
        )


@tagged("post_install", "-at_install")
class TestChatbotRouteScope(LivechatRouteCase):
    def test_restart_refuses_an_ended_human_session(self):
        self._new_visitor()
        channel = self._start_session()
        self.call_jsonrpc(
            "/mail/message/post",
            {
                "thread_model": "discuss.channel",
                "thread_id": channel.id,
                "post_data": {"body": "hi", "message_type": "comment"},
            },
        )
        self.call_jsonrpc(
            "/im_livechat/visitor_leave_session", {"channel_id": channel.id}
        )
        channel.invalidate_recordset()
        ended_at = channel.livechat_end_dt
        self.assertTrue(ended_at)
        result = self.call_jsonrpc(
            "/chatbot/restart",
            {"channel_id": channel.id, "chatbot_script_id": self.chatbot.id},
        )
        self.assertIsNone(result)
        channel.invalidate_recordset()
        self.assertEqual(channel.livechat_end_dt, ended_at)
        self.assertFalse(self._bot_messages(channel, self.chatbot))

    def test_restart_refuses_a_foreign_script(self):
        self._new_visitor()
        channel = self._start_session(self.chatbot)
        result = self.call_jsonrpc(
            "/chatbot/restart",
            {"channel_id": channel.id, "chatbot_script_id": self.foreign_chatbot.id},
        )
        self.assertIsNone(result)
        self.assertFalse(self._bot_messages(channel, self.foreign_chatbot))

    def test_restart_refuses_an_archived_own_script(self):
        self._new_visitor()
        channel = self._start_session(self.chatbot)
        self.chatbot.active = False
        result = self.call_jsonrpc(
            "/chatbot/restart",
            {"channel_id": channel.id, "chatbot_script_id": self.chatbot.id},
        )
        self.assertIsNone(result)

    def test_restart_refuses_once_an_agent_joined(self):
        self._new_visitor()
        channel = self._start_session(self.chatbot)
        channel._add_members(users=self.operators[0])
        channel.livechat_end_dt = fields.Datetime.now()
        ended_at = channel.livechat_end_dt
        before = self._bot_messages(channel, self.chatbot)
        result = self.call_jsonrpc(
            "/chatbot/restart",
            {"channel_id": channel.id, "chatbot_script_id": self.chatbot.id},
        )
        self.assertIsNone(result)
        channel.invalidate_recordset()
        self.assertEqual(channel.livechat_end_dt, ended_at)
        self.assertEqual(self._bot_messages(channel, self.chatbot), before)

    def test_restart_refuses_an_internal_channel(self):
        self.authenticate(self.user_employee.login, self.user_employee.login)
        channel = (
            self.env["discuss.channel"]
            .with_user(self.user_employee)
            ._create_channel(name="internal", group_id=None)
        )
        result = self.call_jsonrpc(
            "/chatbot/restart",
            {"channel_id": channel.id, "chatbot_script_id": self.chatbot.id},
        )
        self.assertIsNone(result)
        self.assertFalse(self._bot_messages(channel, self.chatbot))

    def test_trigger_refuses_a_foreign_script(self):
        self._new_visitor()
        channel = self._start_session()
        with self.mock_bus():
            self.call_jsonrpc(
                "/chatbot/step/trigger",
                {
                    "channel_id": channel.id,
                    "chatbot_script_id": self.foreign_chatbot.id,
                },
            )
        self.assertFalse(self._bot_messages(channel, self.foreign_chatbot))
        self.assertNotIn(
            "Foreign Bot",
            "".join(notif.message for notif in self._new_bus_notifs),
        )

    def test_trigger_refuses_an_internal_channel(self):
        self.authenticate(self.user_employee.login, self.user_employee.login)
        channel = (
            self.env["discuss.channel"]
            .with_user(self.user_employee)
            ._create_channel(name="internal", group_id=None)
        )
        self.call_jsonrpc(
            "/chatbot/step/trigger",
            {"channel_id": channel.id, "chatbot_script_id": self.chatbot.id},
        )
        self.assertFalse(self._bot_messages(channel, self.chatbot))

    def test_restart_accepts_the_script_of_the_bot_persona(self):
        self._new_visitor()
        channel = self._start_session(self.chatbot)
        channel.livechat_bot_history_ids.chatbot_script_id = False
        result = self.call_jsonrpc(
            "/chatbot/restart",
            {"channel_id": channel.id, "chatbot_script_id": self.chatbot.id},
        )
        self.assertTrue(result["message_id"])

    def test_restart_then_trigger_replays_the_own_script(self):
        self._new_visitor()
        channel = self._start_session(self.chatbot)
        result = self.call_jsonrpc(
            "/chatbot/restart",
            {"channel_id": channel.id, "chatbot_script_id": self.chatbot.id},
        )
        self.assertTrue(result["message_id"])
        channel.invalidate_recordset()
        self.assertFalse(channel.chatbot_current_step_id)
        self.call_jsonrpc(
            "/chatbot/step/trigger",
            {"channel_id": channel.id, "chatbot_script_id": self.chatbot.id},
        )
        channel.invalidate_recordset()
        self.assertEqual(
            channel.chatbot_current_step_id, self.chatbot.script_step_ids[0]
        )


@tagged("post_install", "-at_install")
class TestLivechatKpiIntegrity(LivechatRouteCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plain_employee = new_test_user(
            cls.env, "plain_employee", groups="base.group_user"
        )

    def _livechat_vals(self, **vals):
        return {
            "name": "fake session",
            "channel_type": "livechat",
            "livechat_operator_id": self.operators[0].partner_id.id,
            "livechat_channel_id": self.livechat_channel.id,
            **vals,
        }

    def test_internal_user_cannot_create_a_livechat_channel(self):
        with self.assertRaises(AccessError):
            self.env["discuss.channel"].with_user(self.plain_employee).create(
                self._livechat_vals()
            )

    def test_internal_user_cannot_create_a_livechat_member_type(self):
        with self.assertRaises((AccessError, ValidationError)):
            self.env["discuss.channel"].with_user(self.plain_employee).create(
                self._livechat_vals(
                    channel_member_ids=[
                        Command.create(
                            {
                                "partner_id": self.operators[1].partner_id.id,
                                "livechat_member_type": "agent",
                            }
                        )
                    ]
                )
            )

    def test_internal_user_cannot_write_session_outcome_fields(self):
        channel = self.env["discuss.channel"].create(self._livechat_vals())
        channel._add_members(users=self.plain_employee)
        channel_as_employee = channel.with_user(self.plain_employee)
        for vals in (
            {"livechat_end_dt": fields.Datetime.now()},
            {"livechat_failure": "no_agent"},
        ):
            with self.subTest(vals=vals), self.assertRaises(AccessError):
                channel_as_employee.write(vals)

    def test_operator_can_still_create_and_close(self):
        operator = self.operators[0]
        channel = (
            self.env["discuss.channel"]
            .with_user(operator)
            .create(self._livechat_vals())
        )
        channel.write({"livechat_end_dt": fields.Datetime.now()})
        self.assertTrue(channel.livechat_end_dt)

    def test_agent_post_outside_the_livechat_group_sets_no_failure(self):
        channel = self.env["discuss.channel"].create(
            self._livechat_vals(livechat_failure="no_answer")
        )
        channel._add_members(users=self.plain_employee)
        channel.with_user(self.plain_employee).message_post(
            body="I can help", message_type="comment"
        )
        self.assertEqual(channel.livechat_failure, "no_failure")

    def test_feedback_refuses_a_non_visitor(self):
        channel = self.env["discuss.channel"].create(self._livechat_vals())
        channel._add_members(users=self.plain_employee)
        self.authenticate(self.plain_employee.login, self.plain_employee.login)
        result = self.call_jsonrpc(
            "/im_livechat/feedback",
            {"channel_id": channel.id, "rate": 1, "reason": "fake"},
        )
        self.assertFalse(result)
        self.assertFalse(channel.sudo().rating_ids)

    def test_feedback_refuses_a_non_livechat_channel(self):
        self.authenticate(self.plain_employee.login, self.plain_employee.login)
        channel = (
            self.env["discuss.channel"]
            .with_user(self.plain_employee)
            ._create_channel(name="internal", group_id=None)
        )
        result = self.call_jsonrpc(
            "/im_livechat/feedback",
            {"channel_id": channel.id, "rate": 1, "reason": "fake"},
        )
        self.assertFalse(result)
        self.assertFalse(
            self.env["rating.rating"].search(
                [("res_model", "=", "discuss.channel"), ("res_id", "=", channel.id)]
            )
        )

    def test_feedback_rates_the_agent_after_a_bot_handover(self):
        self.authenticate(self.visitor_user.login, self.visitor_user.login)
        channel = self._start_session(self.chatbot)
        agent = (
            self.operators.filtered(
                lambda u: u.partner_id.name > self.visitor_user.partner_id.name
            )[:1]
            or self.operators[0]
        )
        channel._forward_human_operator(users=agent)
        channel.invalidate_recordset()
        self.assertEqual(channel.livechat_operator_id, agent.partner_id)
        rating_id = self.call_jsonrpc(
            "/im_livechat/feedback",
            {"channel_id": channel.id, "rate": 5, "reason": "great"},
        )
        rating = self.env["rating.rating"].browse(rating_id)
        self.assertEqual(rating.rated_partner_id, agent.partner_id)
        agent_history = channel.livechat_agent_history_ids.filtered(
            lambda h: h.partner_id == agent.partner_id
        )
        self.assertEqual(agent_history.rating_id, rating)


@tagged("post_install", "-at_install")
class TestLivechatHistoryAndPosting(LivechatRouteCase):
    def _capture_transient(self):
        sent = []

        def capture(partner, channel, content):
            sent.append((partner.id, channel.id, str(content)))

        self.patch(
            type(self.env["res.partner"]), "_bus_send_transient_message", capture
        )
        return sent

    def test_history_is_limited_to_site_paths(self):
        sent = self._capture_transient()
        self._new_visitor()
        channel = self._start_session()
        operator_partner = channel.livechat_operator_id
        self.call_jsonrpc(
            "/im_livechat/history",
            {
                "pid": operator_partner.id,
                "channel_id": channel.id,
                "page_history": [
                    "javascript:alert(1)",
                    "https://evil.example/phish",
                    "//evil.example/phish",
                    "/shop?x=1",
                ],
            },
        )
        self.assertEqual(len(sent), 1)
        body = sent[0][2]
        self.assertNotIn("javascript:", body)
        self.assertNotIn("evil.example", body)
        self.assertIn(f'href="{channel.get_base_url()}/shop?x=1"', body)

    def test_history_refuses_a_non_livechat_channel(self):
        sent = self._capture_transient()
        self.authenticate(self.user_employee.login, self.user_employee.login)
        channel = (
            self.env["discuss.channel"]
            .with_user(self.user_employee)
            ._create_channel(name="internal", group_id=None)
        )
        channel._add_members(users=self.operators[0])
        self.call_jsonrpc(
            "/im_livechat/history",
            {
                "pid": self.operators[0].partner_id.id,
                "channel_id": channel.id,
                "page_history": ["/phish"],
            },
        )
        self.assertFalse(sent)

    def test_history_refuses_a_non_agent_recipient(self):
        sent = self._capture_transient()
        self.authenticate(self.visitor_user.login, self.visitor_user.login)
        channel = self._start_session()
        self.call_jsonrpc(
            "/im_livechat/history",
            {
                "pid": self.visitor_user.partner_id.id,
                "channel_id": channel.id,
                "page_history": ["/shop"],
            },
        )
        self.assertFalse(sent)

    def test_visitor_cannot_post_after_the_session_ended(self):
        self._new_visitor()
        channel = self._start_session()
        self.call_jsonrpc(
            "/im_livechat/visitor_leave_session", {"channel_id": channel.id}
        )
        with (
            mute_logger("odoo.http"),
            self.assertRaises(JsonRpcException),
        ):
            self.call_jsonrpc(
                "/mail/message/post",
                {
                    "thread_model": "discuss.channel",
                    "thread_id": channel.id,
                    "post_data": {"body": "still here", "message_type": "comment"},
                },
            )
        channel.invalidate_recordset()
        self.assertNotIn("still here", "".join(channel.message_ids.mapped("body")))

    def test_operator_can_post_after_the_session_ended(self):
        channel = self.env["discuss.channel"].create(
            {
                "name": "ended",
                "channel_type": "livechat",
                "livechat_operator_id": self.operators[0].partner_id.id,
                "livechat_channel_id": self.livechat_channel.id,
                "livechat_end_dt": fields.Datetime.now(),
                "channel_member_ids": [
                    Command.create({"partner_id": self.operators[0].partner_id.id})
                ],
            }
        )
        self.authenticate(self.operators[0].login, self.password)
        data = self.call_jsonrpc(
            "/mail/message/post",
            {
                "thread_model": "discuss.channel",
                "thread_id": channel.id,
                "post_data": {"body": "follow-up", "message_type": "comment"},
            },
        )
        self.assertTrue(data["message_id"])


@tagged("post_install", "-at_install")
class TestLivechatModelGuards(LivechatRouteCase):
    def test_livechat_outcome_is_computed_per_record(self):
        escalated, answered = self.env["discuss.channel"].create(
            [
                {
                    "name": "escalated",
                    "channel_type": "livechat",
                    "livechat_operator_id": self.operators[0].partner_id.id,
                    "livechat_failure": "no_failure",
                    "channel_member_ids": [
                        Command.create(
                            {
                                "partner_id": user.partner_id.id,
                                "livechat_member_type": "agent",
                            }
                        )
                        for user in self.operators[:2]
                    ],
                },
                {
                    "name": "answered",
                    "channel_type": "livechat",
                    "livechat_operator_id": self.operators[0].partner_id.id,
                    "livechat_failure": "no_answer",
                },
            ]
        )
        channels = escalated | answered
        channels._compute_livechat_outcome()
        self.assertEqual(
            channels.mapped("livechat_outcome"), ["escalated", "no_answer"]
        )

    def test_redirect_link_accepts_only_web_targets(self):
        step = self.chatbot.script_step_ids[1]
        answers = self.env["chatbot.script.answer"]
        for link in (
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "//evil.example/",
            "https://",
            "ftp://files.example/",
        ):
            with self.subTest(link=link), self.assertRaises(ValidationError):
                answers.create(
                    {"name": "go", "script_step_id": step.id, "redirect_link": link}
                )
        for link in ("/shop", "#chatbot-redirect", "https://www.example.com/x"):
            with self.subTest(link=link):
                answers.create(
                    {"name": "go", "script_step_id": step.id, "redirect_link": link}
                )

    def test_rule_regex_must_compile(self):
        with self.assertRaises(ValidationError):
            self.env["im_livechat.channel.rule"].create(
                {"channel_id": self.livechat_channel.id, "regex_url": "shop(["}
            )

    def test_rule_with_a_script_without_steps_falls_back_to_an_operator(self):
        empty_bot = self.env["chatbot.script"].create({"title": "Empty Bot"})
        self.env["im_livechat.channel.rule"].create(
            {"channel_id": self.livechat_channel.id, "chatbot_script_id": empty_bot.id}
        )
        self._new_visitor()
        data = self.call_jsonrpc(
            "/im_livechat/get_session",
            {"channel_id": self.livechat_channel.id, "chatbot_script_id": empty_bot.id},
        )
        channel = self.env["discuss.channel"].browse(data["channel_id"])
        self.assertIn(channel.livechat_operator_id, self.operators.partner_id)

    def test_invite_panel_for_a_member_outside_the_livechat_group(self):
        john = new_test_user(self.env, "john_invite")
        bob = new_test_user(self.env, "bob_invite")
        channel = self.env["discuss.channel"].create(
            {
                "channel_type": "livechat",
                "livechat_operator_id": self.operators[0].partner_id.id,
                "name": "Support Channel",
                "livechat_channel_id": self.livechat_channel.id,
            }
        )
        channel.with_user(self.operators[0])._add_members(users=john)
        data = john.partner_id.with_user(john).search_for_channel_invite(
            "bob_invite", channel.id
        )["store_data"]
        self.assertIn(bob.partner_id.id, [p["id"] for p in data["res.partner"]])
        self.assertFalse(john.has_group("im_livechat.im_livechat_group_user"))

    def test_rating_action_on_a_deleted_session(self):
        channel = self.env["discuss.channel"].create(
            {
                "name": "rated",
                "channel_type": "livechat",
                "livechat_operator_id": self.operators[0].partner_id.id,
                "livechat_channel_id": self.livechat_channel.id,
            }
        )
        rating = self.env["rating.rating"].create(
            {
                "res_model_id": self.env["ir.model"]._get_id("discuss.channel"),
                "res_id": channel.id,
                "rating": 5,
            }
        )
        self.env.flush_all()
        self.env.cr.execute("DELETE FROM discuss_channel WHERE id = %s", [channel.id])
        self.env.invalidate_all()
        action = rating.action_view_rated_object()
        self.assertEqual(action["type"], "ir.actions.act_window")

    def test_report_binds_the_language(self):
        query = (
            self.env["im_livechat.report.channel"]
            .with_context(lang="en_US")
            ._table_query
        )
        self.assertEqual(query.params.count("en_US"), 2)


@tagged("post_install", "-at_install")
class TestGetSessionFlood(LivechatRouteCase):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(
            "im_livechat.get_session_limit", 2
        )

    def test_persisted_sessions_are_rate_limited_per_address(self):
        created = []
        for _attempt in range(3):
            self._new_visitor()
            data = self.call_jsonrpc(
                "/im_livechat/get_session", {"channel_id": self.livechat_channel.id}
            )
            created.append(bool(data))
        self.assertEqual(created, [True, True, False])

    def test_non_persisted_sessions_are_not_rate_limited(self):
        for _attempt in range(3):
            self._new_visitor()
            data = self.call_jsonrpc(
                "/im_livechat/get_session",
                {"channel_id": self.livechat_channel.id, "persisted": False},
            )
            self.assertTrue(data)


@tagged("post_install", "-at_install")
class TestSilentSessionCapacity(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = new_test_user(
            cls.env,
            "capacity_operator",
            groups="im_livechat.im_livechat_group_user",
        )
        cls.livechat_channel = cls.env["im_livechat.channel"].create(
            {
                "name": "capacity",
                "user_ids": [Command.set(cls.operator.ids)],
                "max_sessions_mode": "limited",
                "max_sessions": 3,
            }
        )

    def _open_session(self, visitor_message=False):
        guest = self.env["mail.guest"].create({"name": "Visitor"})
        channel = self.env["discuss.channel"].create(
            {
                "name": "session",
                "channel_type": "livechat",
                "livechat_channel_id": self.livechat_channel.id,
                "livechat_operator_id": self.operator.partner_id.id,
                "last_interest_dt": fields.Datetime.now(),
                "channel_member_ids": [
                    Command.create(
                        {
                            "partner_id": self.operator.partner_id.id,
                            "livechat_member_type": "agent",
                        }
                    ),
                    Command.create(
                        {"guest_id": guest.id, "livechat_member_type": "visitor"}
                    ),
                ],
            }
        )
        if visitor_message:
            channel.with_user(self.env.ref("base.public_user")).with_context(
                guest=guest
            ).sudo().message_post(
                body="hello",
                message_type="comment",
                author_guest_id=guest.id,
                author_id=False,
            )
        return channel

    def _is_available(self):
        return (
            self.operator
            in (
                self.livechat_channel._get_available_operators_by_livechat_channel()[
                    self.livechat_channel
                ]
            )
        )

    def test_silent_sessions_stop_holding_capacity(self):
        self.env["mail.presence"]._update_presence(self.operator)
        start = fields.Datetime.now()
        with freeze_time(start):
            for _index in range(4):
                self._open_session()
            self.assertFalse(self._is_available())
        with freeze_time(start + timedelta(minutes=3)):
            self.env["mail.presence"]._update_presence(self.operator)
            self.assertTrue(self._is_available())

    def test_answered_sessions_hold_capacity(self):
        self.env["mail.presence"]._update_presence(self.operator)
        start = fields.Datetime.now()
        with freeze_time(start):
            for _index in range(3):
                self._open_session(visitor_message=True)
        with freeze_time(start + timedelta(minutes=3)):
            self.env["mail.presence"]._update_presence(self.operator)
            self.assertFalse(self._is_available())


@tagged("post_install", "-at_install")
class TestChatbotMessageStorePerf(LivechatRouteCase):
    def _bot_session_with_messages(self, count):
        self._new_visitor()
        channel = self._start_session(self.chatbot).sudo()
        step = self.chatbot.script_step_ids[1]
        channel.chatbot_current_step_id = step
        for index in range(count):
            channel._chatbot_post_message(self.chatbot, f"bot line {index}")
        channel.invalidate_recordset()
        return channel.message_ids.filtered(
            lambda m: m.author_id == self.chatbot.operator_partner_id
        )

    def test_store_queries_do_not_grow_with_bot_messages(self):
        messages = self._bot_session_with_messages(10).sorted("id")
        self.assertQueriesConstant(
            lambda size: Store().add(messages[:size]).get_result(), small=2, large=10
        )


@tagged("post_install", "-at_install")
class TestOperatorCapacityConcurrency(TransactionCase):
    def setUp(self):
        super().setUp()
        with db_connect(self.env.cr.dbname).cursor() as cr:
            env = self.env(cr=cr)
            operator = new_test_user(
                env,
                "capacity_race_operator",
                groups="im_livechat.im_livechat_group_user",
            )
            livechat_channel = env["im_livechat.channel"].create(
                {
                    "name": "capacity race",
                    "user_ids": [Command.set(operator.ids)],
                    "max_sessions_mode": "limited",
                    "max_sessions": 1,
                }
            )
            env["mail.presence"]._update_presence(operator)
            cr.commit()
            self.operator_id = operator.id
            self.operator_partner_id = operator.partner_id.id
            self.livechat_channel_id = livechat_channel.id
        self.addCleanup(self._drop_committed_rows)

    def _drop_committed_rows(self):
        with db_connect(self.env.cr.dbname).cursor() as cr:
            env = self.env(cr=cr)
            channels = env["discuss.channel"].search(
                [("livechat_channel_id", "=", self.livechat_channel_id)]
            )
            guests = channels.channel_member_ids.guest_id
            channels.unlink()
            guests.unlink()
            env["im_livechat.channel"].browse(self.livechat_channel_id).unlink()
            env["mail.presence"].search([("user_id", "=", self.operator_id)]).unlink()
            env["res.users"].browse(self.operator_id).unlink()
            env["res.partner"].browse(self.operator_partner_id).unlink()
            cr.commit()

    def _assign(self, env):
        livechat_channel = (
            env["im_livechat.channel"].sudo().browse(self.livechat_channel_id)
        )
        operator = livechat_channel._get_operator()
        if not operator:
            return False
        guest = env["mail.guest"].sudo().create({"name": "race visitor"})
        env["discuss.channel"].sudo().create(
            livechat_channel._prepare_livechat_discuss_channel_vals(
                visitor_guest=guest,
                agent=operator,
                chatbot_script=env["chatbot.script"],
                operator_partner=operator.partner_id,
                operator_model="res.users",
            )
        )
        return True

    def _commit_retrying(self, cr):
        failures = 0
        while True:
            try:
                with mute_logger("odoo.db"):
                    assigned = self._assign(self.env(cr=cr))
                cr.commit()
                return failures, assigned
            except psycopg.errors.SerializationFailure:
                failures += 1
                cr.rollback()
                if failures > 3:
                    raise

    def _committed_session_count(self):
        with db_connect(self.env.cr.dbname).cursor() as cr:
            cr.execute(
                "SELECT count(*) FROM discuss_channel"
                " WHERE livechat_channel_id = %s AND livechat_operator_id = %s",
                [self.livechat_channel_id, self.operator_partner_id],
            )
            return cr.fetchone()[0]

    def test_concurrent_visitors_do_not_exceed_max_sessions(self):
        with (
            db_connect(self.env.cr.dbname).cursor() as cr_a,
            db_connect(self.env.cr.dbname).cursor() as cr_b,
        ):
            cr_a.execute("SELECT 1")
            cr_b.execute("SELECT 1")
            self.assertTrue(self._assign(self.env(cr=cr_a)))
            cr_a.commit()
            retries, assigned = self._commit_retrying(cr_b)
        self.assertEqual(self._committed_session_count(), 1)
        self.assertEqual(retries, 1, "the stale assignment retried")
        self.assertFalse(assigned, "the retried visitor found the operator full")
