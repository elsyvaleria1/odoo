from datetime import timedelta

from odoo import fields
from odoo.tests import JsonRpcException, tagged
from odoo.tools import mute_logger

from odoo.addons.mail.tests.common_controllers import MailControllerCommon
from odoo.addons.mail.tools.discuss import Store

COUNTERS = "/mail/messaging_menu/initialize_counters"
MESSAGE_LOAD_MORE = "/mail/messaging_menu/mail.message/load_more"
CHANNEL_LOAD_MORE = "/mail/messaging_menu/discuss.channel/load_more"
MOST_POPULAR = "/mail/messaging_menu/get_most_popular_channels"


@tagged("-at_install", "post_install", "mail_controller", "messaging_menu")
class TestMessagingMenu(MailControllerCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["discuss.channel.member"].search(
            [("partner_id", "=", cls.partner_employee.id)]
        ).unlink()
        cls.record = cls.env["res.partner"].create({"name": "Menu Record"})
        cls.notified = cls.env["mail.message"]
        for index in range(3):
            cls.notified |= cls.record.message_post(
                body=f"<p>notified {index}</p>",
                message_type="comment",
                partner_ids=cls.partner_employee.ids,
                subtype_xmlid="mail.mt_comment",
            )
        cls.read_message = cls.notified[0]
        cls.read_message.notification_ids.filtered(
            lambda n: n.res_partner_id == cls.partner_employee
        ).is_read = True
        cls.starred = cls.record.message_post(
            body="<p>starred</p>", message_type="comment"
        )
        cls.starred.starred_partner_ids = cls.partner_employee

        employee_channels = cls.env["discuss.channel"].with_user(cls.user_employee)
        cls.chat = employee_channels._get_or_create_chat(cls.partner_admin.ids)
        cls.group = employee_channels._create_group(
            [cls.partner_admin.id, cls.partner_portal.id]
        )
        cls.channel = employee_channels._create_channel("General Menu", None)
        cls.channel._add_members(users=cls.user_admin, post_joined_message=False)
        cls.thread = cls.channel._create_sub_channel(name="Menu Thread")
        cls.muted_channel = employee_channels._create_channel("Muted Menu", None)
        cls.muted_channel._add_members(users=cls.user_admin, post_joined_message=False)
        cls.muted_channel.self_member_id.sudo().mute_until_dt = (
            fields.Datetime.now() + timedelta(days=1)
        )
        cls.foreign_channel = cls.env["discuss.channel"]._create_channel(
            "Foreign Menu", None
        )
        cls.foreign_channel._add_members(
            users=cls.user_employee_nopartner, post_joined_message=False
        )
        cls.public_channel = cls.env["discuss.channel"]._create_channel(
            "Public Menu", None
        )
        cls.public_channel.group_public_id = False
        cls.public_channel._add_members(guests=cls.guest, post_joined_message=False)

        cls.chat_message = cls.chat.with_env(cls.env).message_post(
            body="<p>chat unread</p>",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        cls.group.with_env(cls.env).message_post(
            body="<p>group unread</p>",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        cls.channel_mention = cls.channel.with_env(cls.env).message_post(
            body="<p>mention</p>",
            message_type="comment",
            partner_ids=cls.partner_employee.ids,
            subtype_xmlid="mail.mt_comment",
        )
        cls.channel_last = cls.channel.with_env(cls.env).message_post(
            body="<p>channel last</p>",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        cls.muted_channel.with_env(cls.env).message_post(
            body="<p>muted unread</p>",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        now = fields.Datetime.now()
        for offset, channel in enumerate(
            [cls.chat, cls.group, cls.channel, cls.thread, cls.muted_channel]
        ):
            channel.sudo().last_interest_dt = now - timedelta(minutes=offset)

    def _mail_data(self, *fetch_params):
        return self.call_jsonrpc("/mail/data", {"fetch_params": list(fetch_params)})

    def _counters(self, filters_by_type, as_user=None):
        if as_user is not None:
            self._authenticate_pseudo_user(as_user)
        data = self._mail_data(
            [COUNTERS, {"filter_id_by_tab_id_by_record_type": filters_by_type}]
        )
        return {
            tab["id"]: sorted(tab["init_counter_ids"])
            for tab in data.get("MessagingMenuTab", [])
        }

    def _resolved(self, data, data_id):
        (response,) = [r for r in data["DataResponse"] if r["id"] == data_id]
        return response

    def test_initialize_counters_discuss_channel(self):
        self.authenticate("employee", "employee")
        counters = self._counters(
            {
                "discuss.channel": {
                    "chat": None,
                    "channel": "channel_unread",
                }
            }
        )
        self.assertEqual(
            counters,
            {
                "chat": sorted((self.chat | self.group).ids),
                "channel": self.channel.ids,
            },
            "only important channels count: the muted one and the thread with "
            "nothing unread are left out",
        )
        counters = self._counters(
            {"discuss.channel": {"chat": "chat_group", "channel": "channel_thread"}}
        )
        self.assertEqual(counters, {"chat": self.group.ids, "channel": []})

    def test_initialize_counters_as_guest(self):
        self.public_channel.message_post(
            body="<p>for the guest</p>",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        counters = self._counters(
            {"discuss.channel": {"chat": None, "channel": None}},
            as_user=self.guest,
        )
        self.assertEqual(counters, {"chat": [], "channel": self.public_channel.ids})

    def test_initialize_counters_as_public(self):
        counters = self._counters(
            {"discuss.channel": {"chat": None, "channel": None}},
            as_user=self.user_public,
        )
        self.assertEqual(counters, {"chat": [], "channel": []})

    def test_initialize_counters_answers_presence(self):
        self.authenticate("employee", "employee")
        self.chat.self_member_id.sudo().message_unread_counter = 0
        data = self._mail_data(
            [
                COUNTERS,
                {
                    "filter_id_by_tab_id_by_record_type": {
                        "discuss.channel": {"chat": None, "channel": None}
                    },
                    "presence_tab_ids": ["chat"],
                },
            ]
        )
        self.assertEqual(
            {tab["id"]: tab.get("has_records") for tab in data["MessagingMenuTab"]},
            {"chat": True, "channel": None},
            "only the tabs asking for their presence are answered",
        )
        self._authenticate_pseudo_user(self.user_public)
        data = self._mail_data(
            [
                COUNTERS,
                {
                    "filter_id_by_tab_id_by_record_type": {
                        "discuss.channel": {"chat": None}
                    },
                    "presence_tab_ids": ["chat"],
                },
            ]
        )
        self.assertEqual(
            [tab.get("has_records") for tab in data["MessagingMenuTab"]], [False]
        )

    @mute_logger("odoo.http")
    def test_invalid_presence_request_fails_the_batch(self):
        self.authenticate("employee", "employee")
        for presence in ("chat", [["chat"]], [{"id": "chat"}]):
            with (
                self.subTest(presence=presence),
                self.assertRaises(JsonRpcException) as capture,
            ):
                self._mail_data(
                    [
                        COUNTERS,
                        {
                            "filter_id_by_tab_id_by_record_type": {
                                "discuss.channel": {"chat": None}
                            },
                            "presence_tab_ids": presence,
                        },
                    ]
                )
            self.assertEqual(str(capture.exception), "werkzeug.exceptions.BadRequest")

    @mute_logger("odoo.http")
    def test_unknown_tab_or_filter_fails_the_batch(self):
        self.authenticate("employee", "employee")
        for filters_by_type in (
            {"discuss.channel": {"nope": None}},
            {"discuss.channel": {"chat": "nope"}},
            {"discuss.channel": {"chat": "channel_thread"}},
            {"discuss.channel": ["chat"]},
            {"discuss.channel": {"notification": None}},
        ):
            with (
                self.subTest(filters=filters_by_type),
                self.assertRaises(JsonRpcException) as capture,
            ):
                self._mail_data(
                    "init_messaging",
                    [COUNTERS, {"filter_id_by_tab_id_by_record_type": filters_by_type}],
                )
            self.assertEqual(str(capture.exception), "werkzeug.exceptions.BadRequest")
        for fetch_param in (
            [CHANNEL_LOAD_MORE, {"tab_id": "nope", "limit": 5}, "data-1"],
            [MESSAGE_LOAD_MORE, {"tab_id": "chat", "limit": 5}, "data-2"],
            [
                MESSAGE_LOAD_MORE,
                {"tab_id": "notification", "limit": 5, "filter_ids": ["chat_unread"]},
                "data-3",
            ],
        ):
            with (
                self.subTest(fetch_param=fetch_param),
                self.assertRaises(JsonRpcException) as capture,
            ):
                self._mail_data(fetch_param)
            self.assertEqual(str(capture.exception), "werkzeug.exceptions.BadRequest")

    def test_mail_message_load_more(self):
        self.authenticate("employee", "employee")
        data = self._mail_data(
            [MESSAGE_LOAD_MORE, {"tab_id": "notification", "limit": 2}, "page-1"]
        )
        first_page = [m["id"] for m in data["mail.message"] if "body" in m]
        self.assertEqual(first_page, sorted(self.notified.ids, reverse=True)[:2])
        self.assertFalse(self._resolved(data, "page-1")["is_fully_loaded"])
        by_id = {m["id"]: m for m in data["mail.message"]}
        self.assertTrue(by_id[self.notified[-1].id]["needaction"])
        self.assertFalse(by_id[self.notified[-1].id]["needaction_done"])
        thread = next(t for t in data["mixin.mail.thread"] if t["id"] == self.record.id)
        self.assertEqual(thread["message_needaction_counter"], 2)
        self.assertIn("selfFollower", thread)

        data = self._mail_data(
            [
                MESSAGE_LOAD_MORE,
                {"tab_id": "notification", "limit": 2, "exclude_ids": first_page},
                "page-2",
            ]
        )
        by_id = {m["id"]: m for m in data["mail.message"] if "body" in m}
        self.assertEqual(list(by_id), self.read_message.ids)
        self.assertTrue(self._resolved(data, "page-2")["is_fully_loaded"])
        self.assertFalse(by_id[self.read_message.id]["needaction"])
        self.assertTrue(
            by_id[self.read_message.id]["needaction_done"],
            "a read notification of the current user is a done needaction",
        )

        data = self._mail_data(
            [
                MESSAGE_LOAD_MORE,
                {
                    "tab_id": "notification",
                    "limit": 5,
                    "filter_ids": ["notification_unread"],
                    "search_term": "notified 2",
                },
                "search",
            ]
        )
        self.assertEqual(
            [m["id"] for m in data["mail.message"] if "body" in m],
            self.notified[2].ids,
        )
        self.assertTrue(self._resolved(data, "search")["is_fully_loaded"])

        data = self._mail_data(
            [MESSAGE_LOAD_MORE, {"tab_id": "bookmark", "limit": 5}, "bookmark"]
        )
        self.assertEqual(
            [m["id"] for m in data["mail.message"] if "body" in m], self.starred.ids
        )
        self.assertTrue(data["mail.message"][0]["starred"])

    def test_mail_message_load_more_is_for_logged_in_users(self):
        self._authenticate_pseudo_user(self.guest)
        data = self._mail_data(
            [MESSAGE_LOAD_MORE, {"tab_id": "notification", "limit": 5}, "guest"]
        )
        self.assertNotIn("mail.message", data)
        self.assertNotIn("DataResponse", data)

    def test_discuss_channel_load_more(self):
        self.authenticate("employee", "employee")
        data = self._mail_data(
            [CHANNEL_LOAD_MORE, {"tab_id": "channel", "limit": 2}, "page-1"]
        )
        channel_ids = [c["id"] for c in data["discuss.channel"]]
        self.assertEqual(channel_ids, [self.channel.id, self.thread.id])
        self.assertFalse(self._resolved(data, "page-1")["is_fully_loaded"])
        message_ids = {m["id"] for m in data["mail.message"]}
        self.assertIn(self.channel_last.id, message_ids, "last message")
        self.assertIn(self.channel_mention.id, message_ids, "last needaction")
        by_channel = {c["id"]: c for c in data["discuss.channel"]}
        self.assertTrue(by_channel[self.channel.id]["last_message_fetched"])

        data = self._mail_data(
            [
                CHANNEL_LOAD_MORE,
                {"tab_id": "channel", "limit": 2, "exclude_ids": channel_ids},
                "page-2",
            ]
        )
        self.assertEqual(
            [c["id"] for c in data["discuss.channel"]], self.muted_channel.ids
        )
        self.assertTrue(self._resolved(data, "page-2")["is_fully_loaded"])

        data = self._mail_data(
            [
                CHANNEL_LOAD_MORE,
                {"tab_id": "chat", "limit": 5, "search_term": "nothing matches"},
                "search",
            ]
        )
        self.assertNotIn("discuss.channel", data)
        self.assertTrue(self._resolved(data, "search")["is_fully_loaded"])

        data = self._mail_data(
            [
                CHANNEL_LOAD_MORE,
                {"tab_id": "channel", "limit": 5, "search_term": "muted"},
                "muted",
            ]
        )
        self.assertEqual(
            [c["id"] for c in data["discuss.channel"]], self.muted_channel.ids
        )

        data = self._mail_data(
            [
                CHANNEL_LOAD_MORE,
                {"tab_id": "chat", "limit": 5, "filter_ids": ["chat_unread"]},
                "unread",
            ]
        )
        self.assertEqual(
            [c["id"] for c in data["discuss.channel"]], [self.chat.id, self.group.id]
        )

    def test_meetings_have_their_own_tab(self):
        employee_channels = self.env["discuss.channel"].with_user(self.user_employee)
        meeting = employee_channels._create_group(
            [self.partner_admin.id],
            default_display_mode="video_full_screen",
            name="Stand-up",
        )
        notes = meeting._create_sub_channel(name="Stand-up notes")
        self.authenticate("employee", "employee")

        def listed(tab_id, *filter_ids):
            data = self._mail_data(
                [
                    CHANNEL_LOAD_MORE,
                    {"tab_id": tab_id, "filter_ids": list(filter_ids), "limit": 20},
                    "page",
                ]
            )
            return {channel["id"] for channel in data.get("discuss.channel", [])}

        self.assertEqual(listed("meeting"), {meeting.id, notes.id})
        self.assertFalse(listed("chat") & {meeting.id, notes.id})
        self.assertIn(self.group.id, listed("chat"), "a plain group stays a chat")
        threads = listed("meeting", "meeting_thread")
        self.assertIn(notes.id, threads)
        self.assertLessEqual(
            threads, {notes.id, meeting.id}, "a thread brings its parent"
        )
        self.assertEqual(
            listed("meeting", "meeting_today"),
            {meeting.id},
            "a meeting started now takes place today, its thread follows it",
        )

    def test_favorites_come_first(self):
        self.muted_channel.with_user(
            self.user_admin
        ).self_member_id.sudo().is_favorite = True
        self.authenticate("employee", "employee")
        data = self._mail_data(
            [CHANNEL_LOAD_MORE, {"tab_id": "channel", "limit": 1}, "page-1"]
        )
        self.assertEqual(
            [c["id"] for c in data["discuss.channel"]],
            [self.channel.id],
            "another member's favorite orders nothing for this user",
        )
        self.muted_channel.self_member_id.sudo().is_favorite = True
        data = self._mail_data(
            [CHANNEL_LOAD_MORE, {"tab_id": "channel", "limit": 2}, "page-1"]
        )
        self.assertEqual(
            [c["id"] for c in data["discuss.channel"]],
            [self.muted_channel.id, self.channel.id],
            "the favorite leads the first page though it is the least recent",
        )
        found = self.call_jsonrpc("/discuss/search", {"term": "Menu"})["channel_ids"]
        self.assertEqual(found[0], self.muted_channel.id)

    @mute_logger("odoo.http")
    def test_favorite_route(self):
        self.authenticate("employee", "employee")
        self.call_jsonrpc(
            "/discuss/channel/favorite",
            {"channel_id": self.channel.id, "is_favorite": True},
        )
        self.assertTrue(self.channel.self_member_id.is_favorite)
        self.call_jsonrpc(
            "/discuss/channel/favorite",
            {"channel_id": self.channel.id, "is_favorite": False},
        )
        self.assertFalse(self.channel.self_member_id.is_favorite)
        for params in (
            {"channel_id": self.foreign_channel.id, "is_favorite": True},
            {"channel_id": self.channel.id, "is_favorite": "yes"},
        ):
            with (
                self.subTest(params=params),
                self.assertRaises(JsonRpcException) as capture,
            ):
                self.call_jsonrpc("/discuss/channel/favorite", params)
            self.assertEqual(str(capture.exception), "werkzeug.exceptions.NotFound")

    def test_discuss_channel_load_more_as_guest(self):
        self._authenticate_pseudo_user(self.guest)
        data = self._mail_data(
            [CHANNEL_LOAD_MORE, {"tab_id": "channel", "limit": 5}, "guest"]
        )
        self.assertEqual(
            [c["id"] for c in data["discuss.channel"]], self.public_channel.ids
        )
        self.assertTrue(self._resolved(data, "guest")["is_fully_loaded"])

    def test_get_most_popular_channels(self):
        self.foreign_channel._add_members(
            partners=self.partner_portal | self.partner_admin | self.partner_employee,
            post_joined_message=False,
        )
        self.env.flush_all()
        self.env.cr.execute(
            """
              SELECT member.channel_id
                FROM discuss_channel_member member
                JOIN discuss_channel channel ON channel.id = member.channel_id
               WHERE channel.channel_type = 'channel'
            GROUP BY member.channel_id
            ORDER BY count(*) DESC, member.channel_id DESC
               LIMIT 3
            """
        )
        popular = [channel_id for (channel_id,) in self.env.cr.fetchall()]
        self.assertEqual(len(popular), 3)
        self.authenticate("employee", "employee")
        data = self._mail_data(MOST_POPULAR)
        self.assertEqual(
            data["Store"]["most_popular_channels"],
            [{"id": channel_id, "model": "discuss.channel"} for channel_id in popular],
            "references, most members first, then newest",
        )
        self.assertLessEqual(
            set(popular),
            {c["id"] for c in data["discuss.channel"]},
            "the popular channels are added to the store",
        )

    def test_self_member_id_and_is_unread_search(self):
        channels = self.env["discuss.channel"].with_user(self.user_employee)
        members = self.env["discuss.channel.member"].with_user(self.user_employee)
        self.assertEqual(
            channels.search([("self_member_id.is_unread", "=", True)]),
            self.chat | self.group | self.channel | self.muted_channel,
        )
        self.assertEqual(
            channels.search(
                [
                    ("self_member_id.is_unread", "=", True),
                    ("self_member_id.mute_until_dt", "!=", False),
                ]
            ),
            self.muted_channel,
        )
        self.assertEqual(
            channels.search([("self_member_id", "=", self.chat.self_member_id.id)]),
            self.chat,
        )
        self.assertIn(
            self.public_channel,
            channels.search([("self_member_id", "=", False)]),
        )
        unread = members.search([("is_self", "=", True), ("is_unread", "=", True)])
        self.assertEqual(
            unread,
            (self.chat | self.group | self.channel | self.muted_channel)
            .with_user(self.user_employee)
            .self_member_id,
        )
        self.assertTrue(all(member.is_unread for member in unread))
        self.chat.self_member_id._mark_as_read(self.chat_message.id)
        self.assertNotIn(
            self.chat,
            channels.search([("self_member_id.is_unread", "=", True)]),
        )
        self.assertEqual(
            members.search(
                [
                    ("channel_id", "=", self.chat.id),
                    ("is_self", "=", True),
                    ("is_unread", "=", False),
                ]
            ).channel_id,
            self.chat,
        )

    def test_last_needaction_messages(self):
        channels = (self.chat | self.channel).with_user(self.user_employee)
        self.assertEqual(channels._get_last_needaction_messages(), self.channel_mention)
        later = self.channel.with_env(self.env).message_post(
            body="<p>second mention</p>",
            message_type="comment",
            partner_ids=self.partner_employee.ids,
            subtype_xmlid="mail.mt_comment",
        )
        channels.invalidate_recordset()
        self.assertEqual(channels._get_last_needaction_messages(), later)
        self.assertEqual(
            self.env["discuss.channel"]._get_last_needaction_messages(),
            self.env["mail.message"],
        )

    def test_messaging_menu_tab_values(self):
        self.authenticate("employee", "employee")
        data = self._mail_data(
            [
                COUNTERS,
                {
                    "filter_id_by_tab_id_by_record_type": {
                        "mail.message": {"bookmark": None},
                        "discuss.channel": {"chat": "chat_unread", "channel": None},
                    }
                },
            ]
        )
        self.assertEqual(
            sorted(data["MessagingMenuTab"], key=lambda tab: tab["id"]),
            [
                {"id": "channel", "init_counter_ids": self.channel.ids},
                {
                    "id": "chat",
                    "init_counter_ids": sorted((self.chat | self.group).ids),
                },
            ],
            "counters are ids only, and mail.message tabs are not counted here",
        )
        self.assertNotIn("discuss.channel", data)

    def test_needaction_done_is_one_query_per_batch(self):
        messages = self.notified.with_user(self.user_employee)

        def statements(batch):
            batch.invalidate_model()
            self.env.flush_all()
            count0 = self.cr.sql_statement_count
            result = Store().add(batch).get_result()
            return self.cr.sql_statement_count - count0, result

        statements(messages)
        one, _result = statements(messages[:1])
        three, result = statements(messages)
        self.assertEqual(one, three, "no statement per message")
        self.assertEqual(
            {m["id"]: m["needaction_done"] for m in result["mail.message"]},
            {message.id: message == self.read_message for message in self.notified},
        )
