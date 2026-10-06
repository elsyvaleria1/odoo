from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command
from odoo.fields import Datetime
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.im_livechat.tests.common import TestImLivechatCommon
from odoo.addons.im_livechat.tools.misc import prepare_livechat_history_action


@tagged("post_install", "-at_install")
class TestImLivechatReport(TestImLivechatCommon):
    def setUp(self):
        super().setUp()
        self.env["discuss.channel"].search(
            [("livechat_channel_id", "!=", False)]
        ).unlink()

        def _compute_available_operator_ids(channel_self):
            for record in channel_self:
                record.available_operator_ids = self.operators

        with (
            patch.object(
                type(self.env["im_livechat.channel"]),
                "_compute_available_operator_ids",
                _compute_available_operator_ids,
            ),
            freeze_time("2023-03-17 06:05:54"),
        ):
            channel_id = self.call_jsonrpc(
                "/im_livechat/get_session",
                {"channel_id": self.livechat_channel.id},
            )["channel_id"]

        channel = self.env["discuss.channel"].browse(channel_id)
        self.operator = channel.livechat_operator_id

        self._create_message(
            channel, self.visitor_user.partner_id, "2023-03-17 06:06:59"
        )
        self._create_message(channel, self.operator, "2023-03-17 08:15:54")
        self._create_message(channel, self.operator, "2023-03-17 08:45:54")

        partner_message = self._create_message(
            channel, self.operator, "2023-03-17 05:05:54"
        )
        partner_message |= self._create_message(
            channel, self.operator, "2023-03-17 09:15:54"
        )
        partner_message.model = "res.partner"

        with freeze_time("2023-03-17 09:20:54"):
            self.call_jsonrpc(
                "/im_livechat/visitor_leave_session", {"channel_id": channel_id}
            )
        self.env["mail.message"].flush_model()

    def test_im_livechat_report_channel(self):
        report = self.env["im_livechat.report.channel"].search(
            [("livechat_channel_id", "=", self.livechat_channel.id)]
        )
        self.assertEqual(
            len(report), 1, "Should have one channel report for this live channel"
        )
        self.assertEqual(report.time_to_answer, 7800 / 3600)
        self.assertEqual(int(report.duration), 195)

    def test_im_livechat_report_operator(self):
        result = self.env["im_livechat.report.channel"].formatted_read_group(
            [], aggregates=["time_to_answer:avg", "duration:avg"]
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["time_to_answer:avg"], 7800 / 3600)
        self.assertEqual(int(result[0]["duration:avg"]), 195)
        channel = self.env["discuss.channel"].search(
            [("livechat_channel_id", "=", self.livechat_channel.id)]
        )
        rated_channel = channel.copy()
        self.env["rating.rating"].create(
            {
                "res_model_id": self.env["ir.model"]._get_id("discuss.channel"),
                "res_id": rated_channel.id,
                "rating": 5,
                "consumed": True,
            }
        )
        self.assertEqual(rated_channel.rating_last_value, 5)
        self._create_message(rated_channel, self.operator, "2023-03-18 11:00:00")
        result = self.env["im_livechat.report.channel"].formatted_read_group(
            [], aggregates=["rating:avg"]
        )
        self.assertEqual(
            result[0]["rating:avg"],
            5,
            "Rating average should be 5, excluding unrated sessions",
        )

    @classmethod
    def _create_message(cls, channel, author, date):
        posted_on = Datetime.to_datetime(date)
        with patch.object(cls.env.cr, "now", lambda: posted_on):
            return channel.message_post(author_id=author.id, body=f"Message {date}")

    def test_redirect_to_form_from_pivot(self):
        operator_1 = new_test_user(
            self.env, login="operator_1", groups="im_livechat.im_livechat_group_manager"
        )
        operator_2 = new_test_user(self.env, login="operator_2")
        livechat_channel = self.env["im_livechat.channel"].create(
            {"name": "Support", "user_ids": [operator_1.id, operator_2.id]}
        )
        [partner_1, partner_2] = self.env["res.partner"].create(
            [{"name": "test 1"}, {"name": "test 2"}]
        )
        [channel_1, channel_2, channel_3] = self.env["discuss.channel"].create(
            [
                {
                    "name": "test 1",
                    "channel_type": "livechat",
                    "livechat_channel_id": livechat_channel.id,
                    "livechat_operator_id": operator_1.partner_id.id,
                    "channel_member_ids": [
                        Command.create({"partner_id": partner_1.id})
                    ],
                },
                {
                    "name": "test 2",
                    "channel_type": "livechat",
                    "livechat_channel_id": livechat_channel.id,
                    "livechat_operator_id": operator_2.partner_id.id,
                    "channel_member_ids": [
                        Command.create({"partner_id": partner_2.id})
                    ],
                },
                {
                    "name": "test 3",
                    "channel_type": "livechat",
                    "livechat_channel_id": livechat_channel.id,
                    "livechat_operator_id": operator_2.partner_id.id,
                    "channel_member_ids": [
                        Command.create({"partner_id": partner_2.id})
                    ],
                },
            ]
        )
        self._create_message(channel_1, operator_1.partner_id, "2025-06-26 10:05:00")
        self._create_message(channel_2, operator_2.partner_id, "2025-06-26 10:15:00")
        self._create_message(channel_3, operator_2.partner_id, "2025-06-26 10:25:00")
        agent_report_action = self.env.ref(
            "im_livechat.im_livechat_agent_history_action"
        )
        session_report_action = self.env.ref(
            "im_livechat.im_livechat_report_channel_action"
        )
        self.start_tour(
            f"/odoo/action-{agent_report_action.id}?view_type=pivot",
            "im_livechat_agents_report_pivot_redirect_tour",
            login="operator_1",
        )
        self.start_tour(
            f"/odoo/action-{session_report_action.id}?view_type=pivot",
            "im_livechat_sessions_report_pivot_redirect_tour",
            login="operator_1",
        )

    def test_day_of_week_ordered_by_lang_week_start(self):
        agent = new_test_user(
            self.env, login="test_agent", groups="im_livechat.im_livechat_group_manager"
        )
        livechat_channel = self.env["im_livechat.channel"].create(
            {"name": "Test Support", "user_ids": [agent.id]}
        )
        today_dt = datetime.now()
        for i in range(1, 8):
            date = today_dt + timedelta(days=i)
            with freeze_time(date):
                channel_id = self.call_jsonrpc(
                    "/im_livechat/get_session",
                    {
                        "anonymous_name": f"Visitor_{i}",
                        "channel_id": livechat_channel.id,
                    },
                )["channel_id"]
                channel = self.env["discuss.channel"].browse(channel_id)
                self._create_message(channel, channel.livechat_operator_id, date)
        en_lang = self.env["res.lang"]._activate_lang("en_US")
        report_model = self.env["im_livechat.report.channel"].with_user(agent)
        result = report_model.formatted_read_group(domain=[], groupby=["day_number"])
        expected_order = ["0", "1", "2", "3", "4", "5", "6"]
        actual_order = [group["day_number"] for group in result]
        self.assertEqual(actual_order, expected_order)
        en_lang.week_start = "6"
        result = report_model.formatted_read_group(domain=[], groupby=["day_number"])
        expected_order = ["6", "0", "1", "2", "3", "4", "5"]
        actual_order = [group["day_number"] for group in result]
        self.assertEqual(
            actual_order,
            expected_order,
            f"Days should be ordered starting from Saturday. Got {actual_order}, expected {expected_order}",
        )

    def test_time_to_answer_does_not_count_messages_after_close(self):
        with freeze_time("2025-05-20 06:00:00") as frozen_time:
            data = self.call_jsonrpc(
                "/im_livechat/get_session",
                {"channel_id": self.livechat_channel.id},
            )
            chat = self.env["discuss.channel"].browse(data["channel_id"])
            frozen_time.tick(delta=timedelta(minutes=1))
            chat.message_post(body="Question", message_type="comment")
            self._create_message(chat, self.env.user.partner_id, datetime.now())
            frozen_time.tick(delta=timedelta(minutes=5))
            self.call_jsonrpc(
                "/im_livechat/visitor_leave_session", {"channel_id": chat.id}
            )
            frozen_time.tick(delta=timedelta(minutes=5))
            self._create_message(chat, chat.livechat_operator_id, datetime.now())
            report = self.env["im_livechat.report.channel"].search(
                [("channel_id", "=", chat.id)]
            )
            self.assertEqual(report.time_to_answer, 0.0)


class TestLivechatHistoryAction(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channels = cls.env["discuss.channel"].create(
            [
                {"name": "History action one", "channel_type": "channel"},
                {"name": "History action two", "channel_type": "channel"},
            ]
        )

    def test_single_channel_opens_form_and_preserves_context(self):
        action_model = self.env["ir.actions.act_window"]
        original = action_model._get_action_dict_by_xml_id(
            "im_livechat.discuss_channel_action"
        )
        action = prepare_livechat_history_action(self.env, self.channels[:1])
        self.assertEqual(action["res_id"], self.channels[0].id)
        self.assertEqual(action["view_mode"], "form")
        self.assertEqual(
            action["views"], [view for view in original["views"] if view[1] == "form"]
        )
        self.assertEqual(action.get("context"), original.get("context"))
        self.assertEqual(action.get("domain"), original.get("domain"))
        self.assertEqual(
            action_model._get_action_dict_by_xml_id(
                "im_livechat.discuss_channel_action"
            ),
            original,
        )

    def test_zero_or_multiple_channels_open_filtered_list(self):
        for channels in (self.channels[:0], self.channels):
            with self.subTest(count=len(channels)):
                action = prepare_livechat_history_action(self.env, channels)
                self.assertEqual(action["domain"], [("id", "in", channels.ids)])
                self.assertEqual(action["context"], {})
                self.assertEqual(action["view_mode"], "list")
                self.assertEqual(action["mobile_view_mode"], "list")
                self.assertTrue(
                    all(view[1] in ("list", "form") for view in action["views"])
                )

    def test_both_entry_points_forward_the_search_domain(self):
        for model in (
            "im_livechat.channel.member.history",
            "im_livechat.report.channel",
        ):
            source = self.env[model]
            for channels in (self.channels[:0], self.channels[:1], self.channels):
                with self.subTest(model=model, count=len(channels)):
                    domain = [("channel_id", "in", channels.ids)]
                    with patch.object(
                        type(source),
                        "search_fetch",
                        return_value=SimpleNamespace(channel_id=channels),
                    ) as search:
                        action = source.action_view_discuss_channels(domain=domain)
                    search.assert_called_once_with(domain, ["channel_id"])
                    self.assertEqual(
                        action, prepare_livechat_history_action(self.env, channels)
                    )
