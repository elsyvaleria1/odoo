from datetime import timedelta

from odoo import Command, fields
from odoo.tests import JsonRpcException, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.mail.tests.common_controllers import MailControllerCommon

COUNTERS = "/mail/messaging_menu/initialize_counters"
CHANNEL_LOAD_MORE = "/mail/messaging_menu/discuss.channel/load_more"


@tagged("-at_install", "post_install", "mail_controller", "messaging_menu")
class TestLivechatMessagingMenu(MailControllerCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = new_test_user(
            cls.env,
            login="menu_operator",
            password="menu_operator",
            groups="base.group_user,im_livechat.im_livechat_group_user",
        )
        cls.other_operator = new_test_user(
            cls.env,
            login="menu_other_operator",
            groups="base.group_user,im_livechat.im_livechat_group_user",
        )
        cls.administrator = new_test_user(
            cls.env,
            login="menu_administrator",
            password="menu_administrator",
            groups="base.group_user,base.group_system",
        )
        cls.unread_session = cls._create_session(cls.operator, "Visitor Unread")
        cls.read_session = cls._create_session(cls.operator, "Visitor Read")
        cls.help_session = cls._create_session(cls.other_operator, "Visitor Help")
        cls.foreign_session = cls._create_session(cls.other_operator, "Visitor Foreign")
        cls.employee_session = cls._create_session(
            cls.user_employee, "Visitor Employee"
        )
        for session in cls.read_session | cls.employee_session:
            cls.env["discuss.channel.member"].search(
                [
                    ("channel_id", "=", session.id),
                    ("partner_id", "=", session.livechat_operator_id.id),
                ]
            )._mark_as_read(max(session.message_ids.ids))
        cls.help_session.livechat_status = "need_help"
        cls.hr_livechat_channel = cls.env["im_livechat.channel"].create(
            {"name": "Menu HR"}
        )
        (
            cls.unread_session | cls.help_session
        ).livechat_channel_id = cls.hr_livechat_channel
        cls.env["discuss.channel"].with_user(cls.operator)._get_or_create_chat(
            cls.partner_employee.ids
        )

    @classmethod
    def _create_session(cls, operator, visitor_name):
        guest = cls.env["mail.guest"].create({"name": visitor_name})
        session = cls.env["discuss.channel"].create(
            {
                "name": visitor_name,
                "channel_type": "livechat",
                "livechat_operator_id": operator.partner_id.id,
                "channel_member_ids": [
                    Command.create(
                        {
                            "partner_id": operator.partner_id.id,
                            "livechat_member_type": "agent",
                        }
                    ),
                    Command.create(
                        {"guest_id": guest.id, "livechat_member_type": "visitor"}
                    ),
                ],
            }
        )
        session.with_context(guest=guest).message_post(
            body=f"<p>hello from {visitor_name}</p>",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        return session

    def _mail_data(self, *fetch_params):
        return self.call_jsonrpc("/mail/data", {"fetch_params": list(fetch_params)})

    def _load_more_ids(self, filter_ids=()):
        data = self._mail_data(
            [
                CHANNEL_LOAD_MORE,
                {"tab_id": "livechat", "limit": 10, "filter_ids": list(filter_ids)},
                "livechat",
            ]
        )
        return sorted(channel["id"] for channel in data.get("discuss.channel", []))

    def _counter_ids(self, filter_id):
        data = self._mail_data(
            [
                COUNTERS,
                {
                    "filter_id_by_tab_id_by_record_type": {
                        "discuss.channel": {"livechat": filter_id, "chat": None}
                    }
                },
            ]
        )
        return {
            tab["id"]: sorted(tab["init_counter_ids"])
            for tab in data["MessagingMenuTab"]
        }

    def test_load_more_as_operator(self):
        self.authenticate("menu_operator", "menu_operator")
        self.assertEqual(
            self._load_more_ids(),
            sorted((self.unread_session | self.read_session | self.help_session).ids),
            "own pinned sessions and every session needing help, not another "
            "operator's session nor the operator's chats",
        )
        self.assertEqual(
            self._load_more_ids(["livechat_unread"]), self.unread_session.ids
        )
        self.assertEqual(
            self._load_more_ids(["livechat_need_help"]), self.help_session.ids
        )

    def test_load_more_by_livechat_channel(self):
        self.authenticate("menu_operator", "menu_operator")
        hr_filter = f"livechat_channel_{self.hr_livechat_channel.id}"
        self.assertEqual(
            self._load_more_ids([hr_filter]),
            sorted((self.unread_session | self.help_session).ids),
            "the sessions of the livechat channel the operator sees in the tab",
        )
        self.assertEqual(
            self._load_more_ids([hr_filter, "livechat_need_help"]),
            self.help_session.ids,
        )

    def test_load_more_without_livechat_access(self):
        self.authenticate("employee", "employee")
        self.assertEqual(
            self._load_more_ids(),
            self.employee_session.ids,
            "a user outside the livechat group sees only the sessions they are "
            "pinned in",
        )
        self.assertEqual(self._load_more_ids(["livechat_need_help"]), [])
        self.authenticate("menu_administrator", "menu_administrator")
        self.assertEqual(
            self._load_more_ids(),
            [],
            "reading every session does not make one needing help a livechat "
            "user's business",
        )

    def test_initialize_counters(self):
        self.authenticate("menu_operator", "menu_operator")
        self.assertEqual(
            self._counter_ids(None),
            {"livechat": self.unread_session.ids, "chat": []},
            "only unread own sessions count; a session needing help is not "
            "important to an operator outside it",
        )
        self.assertEqual(
            self._counter_ids("livechat_unread"),
            {"livechat": self.unread_session.ids, "chat": []},
        )

    @mute_logger("odoo.http")
    def test_unknown_livechat_filter_fails(self):
        self.authenticate("menu_operator", "menu_operator")
        for tab_id, filter_id in (
            ("livechat", "chat_unread"),
            ("livechat", "nope"),
            ("livechat", "livechat_channel_"),
            ("livechat", "livechat_channel_0"),
            ("livechat", "livechat_channel_1x"),
            ("livechat", "livechat_channel_-1"),
            ("chat", "livechat_channel_1"),
            ("chat", "livechat_need_help"),
        ):
            with (
                self.subTest(tab_id=tab_id, filter_id=filter_id),
                self.assertRaises(JsonRpcException) as capture,
            ):
                self._mail_data(
                    [
                        COUNTERS,
                        {
                            "filter_id_by_tab_id_by_record_type": {
                                "discuss.channel": {tab_id: filter_id}
                            }
                        },
                    ]
                )
            self.assertEqual(str(capture.exception), "werkzeug.exceptions.BadRequest")

    def _oldest_unread(self, exclude_ids=()):
        data = self._mail_data(
            [
                "/im_livechat/oldest_unread_livechat",
                {"exclude_ids": list(exclude_ids)},
                "oldest",
            ]
        )
        (response,) = [r for r in data["DataResponse"] if r["id"] == "oldest"]
        return response["channel_id"]

    def test_oldest_unread_livechat(self):
        second = self._create_session(self.operator, "Visitor Second")
        ended = self._create_session(self.operator, "Visitor Ended")
        ended.livechat_end_dt = "2020-01-01 00:00:00"
        now = fields.Datetime.now()
        for session, days in ((ended, 3), (second, 2), (self.unread_session, 1)):
            interest = now - timedelta(days=days)
            session.last_interest_dt = interest
            session.channel_member_ids.filtered(
                lambda member: member.partner_id == self.operator.partner_id
            ).last_interest_dt = interest
        self.authenticate("menu_operator", "menu_operator")
        self.assertEqual(
            self._oldest_unread(),
            second.id,
            "the oldest ongoing session comes before any ended one",
        )
        self.assertEqual(self._oldest_unread([second.id]), self.unread_session.id)
        self.assertEqual(
            self._oldest_unread([second.id, self.unread_session.id]), ended.id
        )
        self.assertFalse(
            self._oldest_unread([second.id, self.unread_session.id, ended.id]),
            "read sessions and other operators' sessions are never offered",
        )

    def test_livechat_tab_presence(self):
        data = {}
        for login in ("employee", "menu_administrator"):
            self.authenticate(login, login)
            data[login] = self._mail_data(
                [
                    COUNTERS,
                    {
                        "filter_id_by_tab_id_by_record_type": {
                            "discuss.channel": {"livechat": None}
                        },
                        "presence_tab_ids": ["livechat"],
                    },
                ]
            )["MessagingMenuTab"]
        self.assertEqual(
            [tab["has_records"] for tab in data["employee"]],
            [True],
            "a read session pinned for a user outside the livechat group shows the tab",
        )
        self.assertEqual(
            [tab["has_records"] for tab in data["menu_administrator"]], [False]
        )
