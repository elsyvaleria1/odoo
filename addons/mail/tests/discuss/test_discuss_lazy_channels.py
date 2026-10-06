from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.mail.tests.common_controllers import MailControllerCommon


@tagged("-at_install", "post_install", "mail_controller")
class TestDiscussLazyChannels(MailControllerCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["discuss.channel.member"].search(
            [("partner_id", "=", cls.partner_employee.id)]
        ).unlink()
        channels = cls.env["discuss.channel"].with_user(cls.user_employee)
        cls.chat = channels._get_or_create_chat(cls.partner_admin.ids)
        cls.group = channels._create_group(
            [cls.partner_admin.id, cls.partner_portal.id]
        )
        cls.channel = channels._create_channel("Lazy General", None)
        cls.channel._add_members(users=cls.user_admin, post_joined_message=False)
        cls.other_channel = cls.env["discuss.channel"]._create_channel(
            "Lazy Other", None
        )
        cls.chat.with_env(cls.env).message_post(
            body="<p>unread</p>",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        now = fields.Datetime.now()
        for offset, channel in enumerate([cls.channel, cls.group, cls.chat]):
            channel.sudo().last_interest_dt = now - timedelta(minutes=offset)

    def _search(self, term):
        return self.call_jsonrpc("/discuss/search", {"term": term})

    def test_search_finds_unnamed_group_by_member_name(self):
        self.authenticate("employee", "employee")
        result = self._search(self.partner_portal.name)
        self.assertIn(self.group.id, result["channel_ids"])
        self.assertNotIn("recent_channel_ids", result)

    def test_search_without_term_lists_mentioned_and_recent(self):
        self.authenticate("employee", "employee")
        result = self._search("")
        self.assertEqual(result["mentioned_channel_ids"], self.chat.ids)
        self.assertEqual(
            result["recent_channel_ids"],
            (self.channel | self.group | self.chat).ids,
        )
        listed = {channel["id"] for channel in result["store_data"]["discuss.channel"]}
        self.assertLessEqual(
            {self.chat.id, self.group.id, self.channel.id},
            listed,
            "the listed conversations come with their data, loaded or not",
        )

    def test_search_brings_the_self_chats_of_listed_partners(self):
        self.authenticate("employee", "employee")
        result = self._search(self.partner_admin.name)
        listed = {channel["id"] for channel in result["store_data"]["discuss.channel"]}
        self.assertIn(self.chat.id, listed)

    def test_search_as_public_lists_no_personal_conversations(self):
        self.other_channel.group_public_id = False
        result = self._search("")
        self.assertNotIn("recent_channel_ids", result)
        self.assertNotIn("mentioned_channel_ids", result)

    def test_search_by_member_name_stays_in_own_conversations(self):
        guest_group = (
            self.env["discuss.channel"]
            .with_user(self.user_employee)
            ._create_group([self.partner_portal.id])
        )
        guest_group._add_members(guests=self.guest, post_joined_message=False)
        self.authenticate("employee", "employee")
        self.assertIn(guest_group.id, self._search(self.guest.name)["channel_ids"])
        self.authenticate("portal_test", "portal_test")
        self.assertIn(guest_group.id, self._search(self.guest.name)["channel_ids"])
        self.assertIn(
            guest_group.id, self._search(self.partner_employee.name)["channel_ids"]
        )
        other_group = (
            self.env["discuss.channel"]
            .with_user(self.user_employee)
            ._create_group([self.partner_admin.id])
        )
        self.assertNotIn(
            other_group.id,
            self._search(self.partner_admin.name)["channel_ids"],
            "the persona match never reaches a conversation the user is not in",
        )
        self.authenticate(None, None)
        self.assertEqual(self._search(self.guest.name)["channel_ids"], [])

    def test_odoobot_chat_is_fetched_on_demand(self):
        odoobot = self.env.ref("base.partner_root")
        odoobot_chat = (
            self.env["discuss.channel"]
            .with_user(self.user_employee)
            ._get_or_create_chat(odoobot.ids)
        )
        self.authenticate("employee", "employee")
        data = self.call_jsonrpc("/mail/data", {"fetch_params": ["odoobot_chat"]})
        self.assertEqual([c["id"] for c in data["discuss.channel"]], odoobot_chat.ids)
        self.authenticate("portal_test", "portal_test")
        data = self.call_jsonrpc("/mail/data", {"fetch_params": ["odoobot_chat"]})
        self.assertNotIn("discuss.channel", data)

    def test_hashtag_suggestions_rank_member_channels_first(self):
        foreign = self.env["discuss.channel"]
        for index in range(8):
            foreign |= self.env["discuss.channel"]._create_channel(
                f"Lazy Foreign {index}", None
            )
        suggestions = (
            self.env["discuss.channel"]
            .with_user(self.user_employee)
            .get_mention_suggestions("Lazy")
        )
        channels = suggestions["discuss.channel"]
        self.assertEqual(channels[0]["id"], self.channel.id)
        self.assertTrue(channels[0]["self_member_id"])
        self.assertEqual(len(channels), 8)
        members = {
            member["id"]: member for member in suggestions["discuss.channel.member"]
        }
        self.assertEqual(
            members[channels[0]["self_member_id"]]["channel_id"]["id"],
            self.channel.id,
        )

    def test_mention_suggestions_bring_the_self_chats(self):
        suggestions = (
            self.env["res.partner"]
            .with_user(self.user_employee)
            .get_mention_suggestions(self.partner_admin.name)
        )
        self.assertIn(
            self.chat.id, [channel["id"] for channel in suggestions["discuss.channel"]]
        )
