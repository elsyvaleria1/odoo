from unittest.mock import PropertyMock, patch

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import Command, fields
from odoo.fields import Domain
from odoo.tests.common import HttpCase, tagged, users, warmup

from odoo.addons.mail.tests.common import MailCommon
from odoo.addons.mail.tools.discuss import Store


@tagged("post_install", "-at_install", "is_query_count")
class TestDiscussFullPerformance(HttpCase, MailCommon):
    _query_count_init_store = 24
    _query_count_init_messaging = 41
    _query_count_messaging_menu_channels = 75

    def setUp(self):
        super().setUp()
        self.maxDiff = None
        self.group_user = self.env.ref("base.group_user")
        self.livechat_user = self.env.ref("im_livechat.im_livechat_group_user")
        self.password = "Pl1bhD@2!kXZ"
        self.users = self.env["res.users"].create(
            [
                {
                    "email": "e.e@example.com",
                    "group_ids": [
                        Command.link(self.group_user.id),
                        Command.link(self.livechat_user.id),
                    ],
                    "login": "emp",
                    "name": "Ernest Employee",
                    "notification_type": "inbox",
                    "odoobot_state": "disabled",
                    "password": self.password,
                    "signature": "--\nErnest",
                },
                {
                    "name": "test1",
                    "login": "test1",
                    "password": self.password,
                    "email": "test1@example.com",
                    "country_id": self.env.ref("base.in").id,
                },
                {"name": "test2", "login": "test2", "email": "test2@example.com"},
                {"name": "test3", "login": "test3"},
                {"name": "test4", "login": "test4"},
                {"name": "test5", "login": "test5"},
                {"name": "test6", "login": "test6"},
                {"name": "test7", "login": "test7"},
                {"name": "test8", "login": "test8"},
                {"name": "test9", "login": "test9"},
                {"name": "test10", "login": "test10"},
                {"name": "test11", "login": "test11"},
                {"name": "test12", "login": "test12"},
                {"name": "test13", "login": "test13"},
                {"name": "test14", "login": "test14"},
                {"name": "test15", "login": "test15"},
            ]
        )
        self.employees = self.env["hr.employee"].create(
            [
                {
                    "user_id": user.id,
                }
                for user in self.users
            ]
        )
        self.leave_type = self.env["hr.leave.type"].create(
            {
                "requires_allocation": False,
                "name": "Legal Leaves",
            }
        )
        self.leaves = self.env["hr.leave"].create(
            [
                {
                    "request_date_from": fields.Datetime.today()
                    + relativedelta(days=-2),
                    "request_date_to": fields.Datetime.today() + relativedelta(days=2),
                    "employee_id": employee.id,
                    "holiday_status_id": self.leave_type.id,
                }
                for employee in self.employees
            ]
        )
        self.authenticate(self.users[0].login, self.password)
        Channel = self.env["discuss.channel"].with_user(self.users[0])
        self.channel_general = self.env.ref(
            "mail.channel_all_employees"
        )
        self.channel_general.message_ids.unlink()
        self.channel_general.last_interest_dt = False
        self.channel_general.channel_member_ids.sudo().last_interest_dt = (
            False
        )
        self.env["discuss.channel"].sudo().search(
            [("id", "!=", self.channel_general.id)]
        ).unlink()
        self.user_root = self.env.ref("base.user_root")
        self.channel_channel_public_1 = Channel._create_channel(
            name="public channel 1", group_id=None
        )
        self.channel_channel_public_1._add_members(
            users=self.users[0]
            | self.users[2]
            | self.users[3]
            | self.users[4]
            | self.users[8]
        )
        self.channel_channel_public_2 = Channel._create_channel(
            name="public channel 2", group_id=None
        )
        self.channel_channel_public_2._add_members(
            users=self.users[0]
            | self.users[2]
            | self.users[4]
            | self.users[7]
            | self.users[9]
        )
        self.channel_channel_group_1 = Channel._create_channel(
            name="group restricted channel 1",
            group_id=self.env.ref("base.group_user").id,
        )
        self.channel_channel_group_1._add_members(
            users=self.users[0]
            | self.users[2]
            | self.users[3]
            | self.users[6]
            | self.users[12]
        )
        self.channel_channel_group_2 = Channel._create_channel(
            name="group restricted channel 2",
            group_id=self.env.ref("base.group_user").id,
        )
        self.channel_channel_group_2._add_members(
            users=self.users[0]
            | self.users[2]
            | self.users[6]
            | self.users[7]
            | self.users[13]
        )
        self.channel_chat_1 = Channel._get_or_create_chat(
            (self.users[0] + self.users[14]).partner_id.ids
        )
        self.channel_chat_2 = Channel._get_or_create_chat(
            (self.users[0] + self.users[15]).partner_id.ids
        )
        self.channel_chat_3 = Channel._get_or_create_chat(
            (self.users[0] + self.users[2]).partner_id.ids
        )
        self.channel_chat_4 = Channel._get_or_create_chat(
            (self.users[0] + self.users[3]).partner_id.ids
        )
        self.channel_group_1 = Channel._create_group(
            (self.users[0] + self.users[12]).partner_id.ids
        )
        self.im_livechat_channel = (
            self.env["im_livechat.channel"]
            .sudo()
            .create({"name": "support", "user_ids": [Command.link(self.users[0].id)]})
        )
        self.env["mail.presence"]._update_presence(self.users[0])
        self.authenticate("test1", self.password)
        self.channel_livechat_1 = Channel.browse(
            self.call_jsonrpc(
                "/im_livechat/get_session",
                {
                    "channel_id": self.im_livechat_channel.id,
                    "previous_operator_id": self.users[0].partner_id.id,
                },
            )["channel_id"]
        )
        self.channel_livechat_1.with_user(self.users[1]).message_post(
            body="test", message_type="comment"
        )
        self.conversation_tag = self.env["im_livechat.conversation.tag"].create(
            {"name": "Support", "color": 1}
        )
        self.channel_livechat_1.livechat_conversation_tag_ids = [
            Command.link(self.conversation_tag.id)
        ]
        self.authenticate(None, None)
        with patch(
            "odoo.http.GeoIP.country_code",
            new_callable=PropertyMock(return_value=self.env.ref("base.be").code),
        ):
            self.channel_livechat_2 = Channel.browse(
                self.call_jsonrpc(
                    "/im_livechat/get_session",
                    {
                        "channel_id": self.im_livechat_channel.id,
                        "previous_operator_id": self.users[0].partner_id.id,
                    },
                )["channel_id"]
            )
        self.guest = self.channel_livechat_2.channel_member_ids.guest_id.sudo()
        self.call_jsonrpc(
            "/mail/message/post",
            {
                "post_data": {
                    "body": "test",
                    "message_type": "comment",
                },
                "thread_id": self.channel_livechat_2.id,
                "thread_model": "discuss.channel",
            },
            cookies={
                self.guest._cookie_name: self.guest._format_auth_cookie(),
            },
        )
        self.users[0].notification_type = "inbox"
        message_0 = self.channel_channel_public_1.message_post(
            body="test",
            message_type="comment",
            author_id=self.users[2].partner_id.id,
            partner_ids=self.users[0].partner_id.ids,
        )
        members = self.channel_channel_public_1.channel_member_ids
        member = members.filtered(
            lambda m: m.partner_id == self.users[0].partner_id
        ).with_user(self.users[0])
        member._mark_as_read(message_0.id)
        message_0.toggle_message_starred()
        self.env.company.sudo().name = "YourCompany"
        members = self.channel_chat_1.channel_member_ids
        member = members.with_user(self.users[0]).filtered(lambda m: m.is_self)
        members = self.channel_channel_group_1.channel_member_ids
        member_0 = members.with_user(self.users[0]).filtered(lambda m: m.is_self)
        member_2 = members.with_user(self.users[2]).filtered(lambda m: m.is_self)
        self.channel_channel_group_1_invited_member = member_0
        data = {
            "channel_id": self.channel_channel_group_1.id,
            "channel_member_id": member_2.id,
        }
        session = self.env["discuss.channel.rtc.session"].sudo().create(data)
        member_0.rtc_inviting_session_id = session
        message_1 = self.channel_general.message_post(
            body="test", message_type="comment", author_id=self.users[0].partner_id.id
        )
        self.authenticate(self.users[0].login, self.password)
        self._add_reactions(message_0, ["😊", "😏"])
        self._add_reactions(message_1, ["😊"])
        self.authenticate(self.users[1].login, self.password)
        self._add_reactions(message_0, ["😊", "😏"])
        self._add_reactions(message_1, ["😊", "😁"])
        self.authenticate(self.users[2].login, self.password)
        self._add_reactions(message_0, ["😊", "😁"])
        self._add_reactions(message_1, ["😊", "😁", "👍"])
        self.env.cr.precommit.run()

    def _add_reactions(self, message, reactions):
        for reaction in reactions:
            self.call_jsonrpc(
                "/mail/message/reaction",
                {
                    "action": "add",
                    "content": reaction,
                    "message_id": message.id,
                },
            )

    def _run_test(self, /, *, fn, count, results, preserve_order=True):
        self.authenticate(self.users[0].login, self.password)
        self.env["res.lang"]._get_data(code="en_US")
        with self.assertQueryCount(emp=count):
            if self.warm:
                with self.env.cr._enable_logging():
                    res = fn()
            else:
                res = fn()
        if not preserve_order:
            res, results = (
                self._sort_store_records(res),
                self._sort_store_records(results),
            )
        self.assertEqual(res, results)

    @staticmethod
    def _sort_store_records(data):
        return {
            model: sorted(records, key=lambda record: repr(record.get("id")))
            if isinstance(records, list)
            else records
            for model, records in data.items()
        }

    @freeze_time("2025-04-22 21:18:33")
    @users("emp")
    @warmup
    def test_10_init_store_data(self):

        def test_fn():
            store = Store()
            self.env["res.users"].with_user(self.users[0])._init_store_data(store)
            return store.get_result()

        self._run_test(
            fn=test_fn,
            count=self._query_count_init_store,
            results=self._get_init_store_data_result(),
        )

    @freeze_time("2025-04-22 21:18:33")
    @users("emp")
    @warmup
    def test_20_init_messaging(self):
        self._run_test(
            fn=lambda: self.call_jsonrpc(
                "/mail/data",
                {
                    "fetch_params": [
                        ["discuss.channel", {"ids": [self.channel_chat_1.id]}],
                        "init_messaging",
                    ]
                },
            ),
            count=self._query_count_init_messaging,
            results=self._get_init_messaging_result(),
        )

    @freeze_time("2025-04-22 21:18:33")
    @users("emp")
    @warmup
    def test_30_messaging_menu_channels(self):
        self._run_test(
            fn=lambda: self.call_jsonrpc(
                "/mail/data",
                {
                    "fetch_params": [
                        [
                            "/mail/messaging_menu/discuss.channel/load_more",
                            {"tab_id": tab_id, "limit": 20},
                        ]
                        for tab_id in ("chat", "channel", "livechat")
                    ]
                },
            ),
            count=self._query_count_messaging_menu_channels,
            results=self._get_messaging_menu_channels_result(),
            preserve_order=False,
        )

    def _get_init_store_data_result(self):
        xmlid_to_res_id = self.env["ir.model.data"]._xmlid_to_res_id
        partner_0 = self.users[0].partner_id
        return {
            "res.partner": self._filter_partners_fields(
                {
                    "active": False,
                    "avatar_128_access_token": self.user_root.partner_id._get_avatar_128_access_token(),
                    "email": "odoobot@example.com",
                    "id": self.user_root.partner_id.id,
                    "im_status": "bot",
                    "im_status_access_token": self.user_root.partner_id._get_im_status_access_token(),
                    "is_company": False,
                    "main_user_id": self.user_root.id,
                    "name": "OdooBot",
                    "write_date": fields.Datetime.to_string(
                        self.user_root.partner_id.write_date
                    ),
                },
                {
                    "active": True,
                    "avatar_128_access_token": partner_0._get_avatar_128_access_token(),
                    "id": self.users[0].partner_id.id,
                    "im_status": "online",
                    "im_status_access_token": self.users[
                        0
                    ].partner_id._get_im_status_access_token(),
                    "main_user_id": self.users[0].id,
                    "name": "Ernest Employee",
                    "write_date": fields.Datetime.to_string(
                        self.users[0].partner_id.write_date
                    ),
                },
            ),
            "res.users": self._filter_users_fields(
                {
                    "id": self.user_root.id,
                    "partner_id": self.user_root.partner_id.id,
                    "share": False,
                    "employee_ids": [],
                },
                {
                    "id": self.users[0].id,
                    "partner_id": self.users[0].partner_id.id,
                    "is_admin": False,
                    "is_livechat_manager": False,
                    "notification_type": "inbox",
                    "share": False,
                    "signature": ["markup", str(self.users[0].signature)],
                },
            ),
            "Store": {
                "channel_type_policies": self.env[
                    "discuss.channel"
                ]._channel_type_policies_for_client(),
                "action_discuss_id": xmlid_to_res_id("mail.action_discuss"),
                "hasCannedResponses": True,
                "hasGifPickerFeature": False,
                "hasLinkPreviewFeature": True,
                "has_access_livechat": True,
                "hasMessageTranslationFeature": False,
                "has_access_create_lead": False,
                "internalUserGroupId": self.env.ref("base.group_user").id,
                "mt_comment": self.env.ref("mail.mt_comment").id,
                "mt_note": self.env.ref("mail.mt_note").id,
                "odoobot": self.user_root.partner_id.id,
                "self_partner": self.users[0].partner_id.id,
                "settings": {
                    "channel_notifications": False,
                    "color_scheme": "system",
                    "density": "default",
                    "dismissed_banners": False,
                    "home_tiles": False,
                    "homemenu_config": False,
                    "homemenu_usage": False,
                    "id": self.env["res.users.settings"]
                    ._get_or_create_for_user(self.users[0])
                    .id,
                    "livechat_expertise_ids": [],
                    "livechat_lang_ids": [],
                    "livechat_username": False,
                    "push_to_talk_key": False,
                    "use_push_to_talk": False,
                    "user_id": {"id": self.users[0].id},
                    "voice_active_duration": 200,
                    "volumes": [("ADD", [])],
                    "embedded_actions_config_ids": {},
                },
            },
        }

    def _get_init_messaging_result(self):
        bus_last_id = self.env["bus.bus"].sudo()._bus_last_id()
        return {
            "discuss.channel": self._filter_channels_fields(
                self._expected_result_for_channel(self.channel_chat_1),
                self._expected_result_for_channel(self.channel_channel_group_1),
            ),
            "discuss.channel.member": [
                self._res_for_member(self.channel_chat_1, self.users[0].partner_id),
                self._res_for_member(self.channel_chat_1, self.users[14].partner_id),
                self._res_for_member(
                    self.channel_channel_group_1, self.users[0].partner_id
                ),
                self._res_for_member(
                    self.channel_channel_group_1, self.users[2].partner_id
                ),
            ],
            "discuss.channel.rtc.session": [
                self._expected_result_for_rtc_session(
                    self.channel_channel_group_1, self.users[2]
                ),
            ],
            "res.groups": [
                {"full_name": "Role / User", "id": self.env.ref("base.group_user").id}
            ],
            "res.partner": self._filter_partners_fields(
                self._expected_result_for_persona(self.users[0]),
                self._expected_result_for_persona(self.users[14]),
                self._expected_result_for_persona(self.users[2], only_inviting=True),
            ),
            "res.users": self._filter_users_fields(
                self._res_for_user(self.users[0]),
                self._res_for_user(self.users[14]),
            ),
            "hr.employee": [
                self._res_for_employee(self.users[0].employee_ids[0]),
                self._res_for_employee(self.users[14].employee_ids[0]),
            ],
            "Store": {
                "needaction_counter": 0,
                "needaction_counter_bus_id": bus_last_id,
                "starred_counter": 1,
                "starred_counter_bus_id": bus_last_id,
            },
        }

    def _get_messaging_menu_channels_result(self):
        return {
            "discuss.call.history": [
                {
                    "duration_hour": self.channel_channel_group_1.call_history_ids.duration_hour,
                    "end_dt": False,
                    "id": self.channel_channel_group_1.call_history_ids.id,
                },
            ],
            "discuss.channel": self._filter_channels_fields(
                {
                    **self._expected_result_for_channel(self.channel_general),
                    "last_message_fetched": True,
                },
                {
                    **self._expected_result_for_channel(self.channel_channel_public_1),
                    "last_message_fetched": True,
                },
                {
                    **self._expected_result_for_channel(self.channel_channel_public_2),
                    "last_message_fetched": True,
                },
                {
                    **self._expected_result_for_channel(self.channel_channel_group_1),
                    "last_message_fetched": True,
                },
                {
                    **self._expected_result_for_channel(self.channel_channel_group_2),
                    "last_message_fetched": True,
                },
                {
                    **self._expected_result_for_channel(self.channel_chat_1),
                    "last_message_fetched": True,
                },
                {
                    **self._expected_result_for_channel(self.channel_chat_2),
                    "last_message_fetched": True,
                },
                {
                    **self._expected_result_for_channel(self.channel_chat_3),
                    "last_message_fetched": True,
                },
                {
                    **self._expected_result_for_channel(self.channel_chat_4),
                    "last_message_fetched": True,
                },
                {
                    **self._expected_result_for_channel(self.channel_group_1),
                    "last_message_fetched": True,
                },
                {
                    **self._expected_result_for_channel(self.channel_livechat_1),
                    "last_message_fetched": True,
                },
                {
                    **self._expected_result_for_channel(self.channel_livechat_2),
                    "last_message_fetched": True,
                },
            ),
            "discuss.channel.member": [
                self._res_for_member(self.channel_general, self.users[0].partner_id),
                self._res_for_member(
                    self.channel_channel_public_1, self.users[0].partner_id
                ),
                self._res_for_member(
                    self.channel_channel_public_2, self.users[0].partner_id
                ),
                self._res_for_member(
                    self.channel_channel_group_1, self.users[0].partner_id
                ),
                self._res_for_member(
                    self.channel_channel_group_1, self.users[2].partner_id
                ),
                self._res_for_member(
                    self.channel_channel_group_2, self.users[0].partner_id
                ),
                self._res_for_member(self.channel_chat_1, self.users[0].partner_id),
                self._res_for_member(self.channel_chat_1, self.users[14].partner_id),
                self._res_for_member(self.channel_chat_2, self.users[0].partner_id),
                self._res_for_member(self.channel_chat_2, self.users[15].partner_id),
                self._res_for_member(self.channel_chat_3, self.users[0].partner_id),
                self._res_for_member(self.channel_chat_3, self.users[2].partner_id),
                self._res_for_member(self.channel_chat_4, self.users[0].partner_id),
                self._res_for_member(self.channel_chat_4, self.users[3].partner_id),
                self._res_for_member(self.channel_group_1, self.users[0].partner_id),
                self._res_for_member(self.channel_group_1, self.users[12].partner_id),
                self._res_for_member(self.channel_livechat_1, self.users[0].partner_id),
                self._res_for_member(self.channel_livechat_1, self.users[1].partner_id),
                self._res_for_member(self.channel_livechat_2, self.users[0].partner_id),
                self._res_for_member(self.channel_livechat_2, guest=True),
            ],
            "discuss.channel.rtc.session": [
                self._expected_result_for_rtc_session(
                    self.channel_channel_group_1, self.users[2]
                ),
            ],
            "im_livechat.channel": [
                self._expected_result_for_livechat_channel(),
            ],
            "im_livechat.conversation.tag": [
                {
                    "id": self.conversation_tag.id,
                    "name": "Support",
                    "color": self.conversation_tag.color,
                },
            ],
            "mail.guest": [
                self._expected_result_for_persona(guest=True),
            ],
            "mail.message": self._filter_messages_fields(
                self._expected_result_for_message(self.channel_general),
                self._expected_result_for_message(self.channel_channel_public_1),
                self._expected_result_for_message(self.channel_channel_public_2),
                self._expected_result_for_message(self.channel_channel_group_1),
                self._expected_result_for_message(self.channel_channel_group_2),
                self._expected_result_for_message(self.channel_livechat_1),
                self._expected_result_for_message(self.channel_livechat_2),
            ),
            "mail.notification": [
                self._expected_result_for_notification(self.channel_channel_public_1),
            ],
            "mail.message.subtype": [
                {"description": False, "id": self.env.ref("mail.mt_note").id},
                {"description": False, "id": self.env.ref("mail.mt_comment").id},
            ],
            "mixin.mail.thread": self._filter_threads_fields(
                self._expected_result_for_thread(self.channel_general),
                self._expected_result_for_thread(self.channel_channel_public_1),
                self._expected_result_for_thread(self.channel_channel_public_2),
                self._expected_result_for_thread(self.channel_channel_group_1),
                self._expected_result_for_thread(self.channel_channel_group_2),
                self._expected_result_for_thread(self.channel_livechat_1),
                self._expected_result_for_thread(self.channel_livechat_2),
            ),
            "MessageReactions": [
                *self._expected_result_for_message_reactions(self.channel_general),
                *self._expected_result_for_message_reactions(
                    self.channel_channel_public_1
                ),
            ],
            "res.country": [
                {"code": "IN", "id": self.env.ref("base.in").id, "name": "India"},
                {"code": "BE", "id": self.env.ref("base.be").id, "name": "Belgium"},
            ],
            "res.groups": [
                {"full_name": "Role / User", "id": self.env.ref("base.group_user").id}
            ],
            "res.partner": self._filter_partners_fields(
                self._expected_result_for_persona(
                    self.users[0],
                    also_livechat=True,
                    also_notification=True,
                ),
                self._expected_result_for_persona(self.users[2]),
                self._expected_result_for_persona(self.users[14]),
                self._expected_result_for_persona(self.users[15]),
                self._expected_result_for_persona(self.users[3]),
                self._expected_result_for_persona(self.users[12]),
                self._expected_result_for_persona(self.users[1], also_livechat=True),
                self._expected_result_for_persona(self.user_root),
            ),
            "res.users": self._filter_users_fields(
                self._res_for_user(self.users[0]),
                self._res_for_user(self.users[14]),
                self._res_for_user(self.users[15]),
                self._res_for_user(self.users[2]),
                self._res_for_user(self.users[3]),
                self._res_for_user(self.users[12]),
                self._res_for_user(self.user_root),
                self._res_for_user(self.users[1]),
            ),
            "hr.employee": [
                self._res_for_employee(self.users[0].employee_ids[0]),
                self._res_for_employee(self.users[14].employee_ids[0]),
                self._res_for_employee(self.users[15].employee_ids[0]),
                self._res_for_employee(self.users[2].employee_ids[0]),
                self._res_for_employee(self.users[3].employee_ids[0]),
                self._res_for_employee(self.users[12].employee_ids[0]),
            ],
        }

    def _expected_result_for_channel(self, channel):
        bus_last_id = self.env["bus.bus"].sudo()._bus_last_id()
        members = channel.channel_member_ids
        member_0 = members.filtered(lambda m: m.partner_id == self.users[0].partner_id)
        member_2 = members.filtered(lambda m: m.partner_id == self.users[2].partner_id)
        member_12 = members.filtered(
            lambda m: m.partner_id == self.users[12].partner_id
        )
        last_interest_dt = fields.Datetime.to_string(channel.last_interest_dt)
        if channel == self.channel_general:
            return {
                "avatar_cache_key": channel.avatar_cache_key,
                "channel_type": "channel",
                "create_uid": self.user_root.id,
                "default_display_mode": False,
                "description": "General announcements for all employees.",
                "fetchChannelInfoState": "fetched",
                "from_message_id": False,
                "group_ids": channel.group_ids.ids,
                "group_public_id": self.env.ref("base.group_user").id,
                "id": channel.id,
                "invited_member_ids": [["ADD", []]],
                "is_editable": True,
                "last_interest_dt": last_interest_dt,
                "member_count": len(self.group_user.all_user_ids),
                "message_needaction_counter_bus_id": bus_last_id,
                "message_needaction_counter": 0,
                "name": "general",
                "parent_channel_id": False,
                "rtc_session_ids": [["ADD", []]],
                "uuid": channel.uuid,
            }
        if channel == self.channel_channel_public_1:
            return {
                "avatar_cache_key": channel.avatar_cache_key,
                "channel_type": "channel",
                "create_uid": self.env.user.id,
                "default_display_mode": False,
                "description": False,
                "fetchChannelInfoState": "fetched",
                "from_message_id": False,
                "group_ids": [],
                "group_public_id": False,
                "id": channel.id,
                "invited_member_ids": [["ADD", []]],
                "is_editable": True,
                "last_interest_dt": last_interest_dt,
                "member_count": 5,
                "message_needaction_counter_bus_id": bus_last_id,
                "message_needaction_counter": 1,
                "name": "public channel 1",
                "parent_channel_id": False,
                "rtc_session_ids": [["ADD", []]],
                "uuid": channel.uuid,
            }
        if channel == self.channel_channel_public_2:
            return {
                "avatar_cache_key": channel.avatar_cache_key,
                "channel_type": "channel",
                "create_uid": self.env.user.id,
                "default_display_mode": False,
                "description": False,
                "fetchChannelInfoState": "fetched",
                "from_message_id": False,
                "group_ids": [],
                "group_public_id": False,
                "id": channel.id,
                "invited_member_ids": [["ADD", []]],
                "is_editable": True,
                "last_interest_dt": last_interest_dt,
                "member_count": 5,
                "message_needaction_counter_bus_id": bus_last_id,
                "message_needaction_counter": 0,
                "name": "public channel 2",
                "parent_channel_id": False,
                "rtc_session_ids": [["ADD", []]],
                "uuid": channel.uuid,
            }
        if channel == self.channel_channel_group_1:
            return {
                "avatar_cache_key": channel.avatar_cache_key,
                "channel_type": "channel",
                "create_uid": self.env.user.id,
                "default_display_mode": False,
                "description": False,
                "fetchChannelInfoState": "fetched",
                "from_message_id": False,
                "group_ids": [],
                "group_public_id": self.env.ref("base.group_user").id,
                "id": channel.id,
                "invited_member_ids": [["ADD", [member_0.id]]],
                "is_editable": True,
                "last_interest_dt": last_interest_dt,
                "member_count": 5,
                "message_needaction_counter_bus_id": bus_last_id,
                "message_needaction_counter": 0,
                "name": "group restricted channel 1",
                "parent_channel_id": False,
                "rtc_session_ids": [["ADD", [member_2.sudo().rtc_session_ids.id]]],
                "uuid": channel.uuid,
            }
        if channel == self.channel_channel_group_2:
            return {
                "avatar_cache_key": channel.avatar_cache_key,
                "channel_type": "channel",
                "create_uid": self.env.user.id,
                "default_display_mode": False,
                "description": False,
                "fetchChannelInfoState": "fetched",
                "from_message_id": False,
                "group_ids": [],
                "group_public_id": self.env.ref("base.group_user").id,
                "id": channel.id,
                "invited_member_ids": [["ADD", []]],
                "is_editable": True,
                "last_interest_dt": last_interest_dt,
                "member_count": 5,
                "message_needaction_counter_bus_id": bus_last_id,
                "message_needaction_counter": 0,
                "name": "group restricted channel 2",
                "parent_channel_id": False,
                "rtc_session_ids": [["ADD", []]],
                "uuid": channel.uuid,
            }
        if channel == self.channel_group_1:
            return {
                "avatar_cache_key": channel.avatar_cache_key,
                "channel_name_member_ids": [member_0.id, member_12.id],
                "channel_type": "group",
                "create_uid": self.env.user.id,
                "default_display_mode": False,
                "description": False,
                "fetchChannelInfoState": "fetched",
                "from_message_id": False,
                "id": channel.id,
                "invited_member_ids": [["ADD", []]],
                "is_editable": True,
                "last_interest_dt": last_interest_dt,
                "member_count": 2,
                "message_needaction_counter_bus_id": bus_last_id,
                "message_needaction_counter": 0,
                "name": "",
                "parent_channel_id": False,
                "rtc_session_ids": [["ADD", []]],
                "uuid": channel.uuid,
            }
        if channel == self.channel_chat_1:
            return {
                "channel_type": "chat",
                "create_uid": self.env.user.id,
                "default_display_mode": False,
                "fetchChannelInfoState": "fetched",
                "id": channel.id,
                "invited_member_ids": [["ADD", []]],
                "is_editable": True,
                "last_interest_dt": last_interest_dt,
                "member_count": 2,
                "message_needaction_counter_bus_id": bus_last_id,
                "message_needaction_counter": 0,
                "name": "Ernest Employee, test14",
                "rtc_session_ids": [["ADD", []]],
                "uuid": channel.uuid,
            }
        if channel == self.channel_chat_2:
            return {
                "channel_type": "chat",
                "create_uid": self.env.user.id,
                "default_display_mode": False,
                "fetchChannelInfoState": "fetched",
                "id": channel.id,
                "invited_member_ids": [["ADD", []]],
                "is_editable": True,
                "last_interest_dt": last_interest_dt,
                "member_count": 2,
                "message_needaction_counter_bus_id": bus_last_id,
                "message_needaction_counter": 0,
                "name": "Ernest Employee, test15",
                "rtc_session_ids": [["ADD", []]],
                "uuid": channel.uuid,
            }
        if channel == self.channel_chat_3:
            return {
                "channel_type": "chat",
                "create_uid": self.env.user.id,
                "default_display_mode": False,
                "fetchChannelInfoState": "fetched",
                "id": channel.id,
                "invited_member_ids": [["ADD", []]],
                "is_editable": True,
                "last_interest_dt": last_interest_dt,
                "member_count": 2,
                "message_needaction_counter_bus_id": bus_last_id,
                "message_needaction_counter": 0,
                "name": "Ernest Employee, test2",
                "rtc_session_ids": [["ADD", []]],
                "uuid": channel.uuid,
            }
        if channel == self.channel_chat_4:
            return {
                "channel_type": "chat",
                "create_uid": self.env.user.id,
                "default_display_mode": False,
                "fetchChannelInfoState": "fetched",
                "id": channel.id,
                "invited_member_ids": [["ADD", []]],
                "is_editable": True,
                "last_interest_dt": last_interest_dt,
                "member_count": 2,
                "message_needaction_counter_bus_id": bus_last_id,
                "message_needaction_counter": 0,
                "name": "Ernest Employee, test3",
                "rtc_session_ids": [["ADD", []]],
                "uuid": channel.uuid,
            }
        if channel == self.channel_livechat_1:
            return {
                "ai_agent_id": False,
                "channel_type": "livechat",
                "country_id": self.env.ref("base.in").id,
                "create_uid": self.users[1].id,
                "default_display_mode": False,
                "description": False,
                "fetchChannelInfoState": "fetched",
                "id": channel.id,
                "invited_member_ids": [["ADD", []]],
                "is_editable": True,
                "last_interest_dt": last_interest_dt,
                "livechat_end_dt": False,
                "livechat_channel_id": self.im_livechat_channel.id,
                "livechat_conversation_tag_ids": [self.conversation_tag.id],
                "livechat_note": False,
                "livechat_outcome": "no_answer",
                "livechat_status": "in_progress",
                "livechat_looking_for_help_since_dt": False,
                "livechat_lang_id": False,
                "livechat_visitor_id": False,
                "livechat_expertise_ids": [],
                "livechat_operator_id": self.users[0].partner_id.id,
                "member_count": 2,
                "message_needaction_counter_bus_id": bus_last_id,
                "message_needaction_counter": 0,
                "name": "test1 Ernest Employee",
                "requested_by_operator": False,
                "rtc_session_ids": [["ADD", []]],
                "uuid": channel.uuid,
            }
        if channel == self.channel_livechat_2:
            return {
                "ai_agent_id": False,
                "channel_type": "livechat",
                "country_id": self.env.ref("base.be").id,
                "create_uid": self.env.ref("base.public_user").id,
                "default_display_mode": False,
                "description": False,
                "fetchChannelInfoState": "fetched",
                "id": channel.id,
                "invited_member_ids": [["ADD", []]],
                "is_editable": True,
                "last_interest_dt": last_interest_dt,
                "livechat_end_dt": False,
                "livechat_channel_id": self.im_livechat_channel.id,
                "livechat_conversation_tag_ids": [],
                "livechat_note": False,
                "livechat_outcome": "no_answer",
                "livechat_status": "in_progress",
                "livechat_looking_for_help_since_dt": False,
                "livechat_lang_id": False,
                "livechat_visitor_id": False,
                "livechat_expertise_ids": [],
                "livechat_operator_id": self.users[0].partner_id.id,
                "member_count": 2,
                "message_needaction_counter_bus_id": bus_last_id,
                "message_needaction_counter": 0,
                "name": "Visitor Ernest Employee",
                "requested_by_operator": False,
                "rtc_session_ids": [["ADD", []]],
                "uuid": channel.uuid,
            }
        return {}

    def _res_for_member(self, channel, partner=None, guest=None):
        members = channel.channel_member_ids
        member_0 = members.filtered(lambda m: m.partner_id == self.users[0].partner_id)
        member_0_last_interest_dt = fields.Datetime.to_string(member_0.last_interest_dt)
        member_0_last_seen_dt = fields.Datetime.to_string(member_0.last_seen_dt)
        member_0_create_date = fields.Datetime.to_string(member_0.create_date)
        member_1 = members.filtered(lambda m: m.partner_id == self.users[1].partner_id)
        member_2 = members.filtered(lambda m: m.partner_id == self.users[2].partner_id)
        member_3 = members.filtered(lambda m: m.partner_id == self.users[3].partner_id)
        member_12 = members.filtered(
            lambda m: m.partner_id == self.users[12].partner_id
        )
        member_14 = members.filtered(
            lambda m: m.partner_id == self.users[14].partner_id
        )
        member_15 = members.filtered(
            lambda m: m.partner_id == self.users[15].partner_id
        )
        last_message = channel._get_last_messages()
        last_message_of_partner_0 = self.env["mail.message"].search(
            Domain("author_id", "=", member_0.partner_id.id)
            & Domain("model", "=", "discuss.channel")
            & Domain("res_id", "=", channel.id),
            order="id desc",
            limit=1,
        )
        member_g = members.filtered(lambda m: m.guest_id)
        guest = member_g.guest_id
        bus_last_id = self.env["bus.bus"].sudo()._bus_last_id()
        if channel == self.channel_general and partner == self.users[0].partner_id:
            return {
                "create_date": member_0_create_date,
                "custom_channel_name": False,
                "custom_notifications": False,
                "fetched_message_id": False,
                "id": member_0.id,
                "is_favorite": False,
                "last_interest_dt": member_0_last_interest_dt,
                "message_unread_counter": 1,
                "message_unread_counter_bus_id": bus_last_id,
                "mute_until_dt": False,
                "last_seen_dt": member_0_last_seen_dt,
                "new_message_separator": 0,
                "partner_id": self.users[0].partner_id.id,
                "rtc_inviting_session_id": False,
                "seen_message_id": False,
                "unpin_dt": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if (
            channel == self.channel_channel_public_1
            and partner == self.users[0].partner_id
        ):
            return {
                "create_date": member_0_create_date,
                "custom_channel_name": False,
                "custom_notifications": False,
                "fetched_message_id": last_message.id,
                "id": member_0.id,
                "is_favorite": False,
                "last_interest_dt": member_0_last_interest_dt,
                "message_unread_counter": 0,
                "message_unread_counter_bus_id": bus_last_id,
                "mute_until_dt": False,
                "last_seen_dt": member_0_last_seen_dt,
                "new_message_separator": last_message.id + 1,
                "partner_id": self.users[0].partner_id.id,
                "rtc_inviting_session_id": False,
                "seen_message_id": last_message.id,
                "unpin_dt": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if (
            channel == self.channel_channel_public_2
            and partner == self.users[0].partner_id
        ):
            return {
                "create_date": member_0_create_date,
                "custom_channel_name": False,
                "custom_notifications": False,
                "fetched_message_id": last_message.id,
                "id": member_0.id,
                "is_favorite": False,
                "last_interest_dt": member_0_last_interest_dt,
                "message_unread_counter": 0,
                "message_unread_counter_bus_id": bus_last_id,
                "mute_until_dt": False,
                "last_seen_dt": member_0_last_seen_dt,
                "new_message_separator": last_message.id + 1,
                "partner_id": self.users[0].partner_id.id,
                "rtc_inviting_session_id": False,
                "seen_message_id": last_message.id,
                "unpin_dt": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if (
            channel == self.channel_channel_group_1
            and partner == self.users[0].partner_id
        ):
            return {
                "create_date": member_0_create_date,
                "custom_channel_name": False,
                "custom_notifications": False,
                "fetched_message_id": last_message_of_partner_0.id,
                "id": member_0.id,
                "is_favorite": False,
                "last_interest_dt": member_0_last_interest_dt,
                "message_unread_counter": 0,
                "message_unread_counter_bus_id": bus_last_id,
                "mute_until_dt": False,
                "last_seen_dt": member_0_last_seen_dt,
                "new_message_separator": last_message_of_partner_0.id + 1,
                "partner_id": self.users[0].partner_id.id,
                "rtc_inviting_session_id": member_0.rtc_inviting_session_id.id,
                "seen_message_id": last_message_of_partner_0.id,
                "unpin_dt": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if (
            channel == self.channel_channel_group_1
            and partner == self.users[2].partner_id
        ):
            return {
                "id": member_2.id,
                "partner_id": self.users[2].partner_id.id,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if (
            channel == self.channel_channel_group_2
            and partner == self.users[0].partner_id
        ):
            return {
                "create_date": member_0_create_date,
                "custom_channel_name": False,
                "custom_notifications": False,
                "fetched_message_id": last_message.id,
                "id": member_0.id,
                "is_favorite": False,
                "last_interest_dt": member_0_last_interest_dt,
                "message_unread_counter": 0,
                "message_unread_counter_bus_id": bus_last_id,
                "mute_until_dt": False,
                "last_seen_dt": member_0_last_seen_dt,
                "new_message_separator": last_message.id + 1,
                "partner_id": self.users[0].partner_id.id,
                "rtc_inviting_session_id": False,
                "seen_message_id": last_message.id,
                "unpin_dt": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_group_1 and partner == self.users[0].partner_id:
            return {
                "create_date": member_0_create_date,
                "custom_channel_name": False,
                "custom_notifications": False,
                "fetched_message_id": False,
                "id": member_0.id,
                "is_favorite": False,
                "last_interest_dt": member_0_last_interest_dt,
                "message_unread_counter": 0,
                "message_unread_counter_bus_id": bus_last_id,
                "mute_until_dt": False,
                "last_seen_dt": member_0_last_seen_dt,
                "new_message_separator": 0,
                "partner_id": self.users[0].partner_id.id,
                "rtc_inviting_session_id": False,
                "seen_message_id": False,
                "unpin_dt": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_group_1 and partner == self.users[12].partner_id:
            return {
                "create_date": fields.Datetime.to_string(member_12.create_date),
                "last_seen_dt": False,
                "fetched_message_id": False,
                "id": member_12.id,
                "partner_id": self.users[12].partner_id.id,
                "seen_message_id": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_chat_1 and partner == self.users[0].partner_id:
            return {
                "create_date": member_0_create_date,
                "custom_channel_name": False,
                "custom_notifications": False,
                "fetched_message_id": False,
                "id": member_0.id,
                "is_favorite": False,
                "last_interest_dt": member_0_last_interest_dt,
                "message_unread_counter": 0,
                "message_unread_counter_bus_id": bus_last_id,
                "mute_until_dt": False,
                "last_seen_dt": member_0_last_seen_dt,
                "new_message_separator": 0,
                "partner_id": self.users[0].partner_id.id,
                "rtc_inviting_session_id": False,
                "seen_message_id": False,
                "unpin_dt": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_chat_1 and partner == self.users[14].partner_id:
            return {
                "create_date": fields.Datetime.to_string(member_14.create_date),
                "last_seen_dt": False,
                "fetched_message_id": False,
                "id": member_14.id,
                "partner_id": self.users[14].partner_id.id,
                "seen_message_id": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_chat_2 and partner == self.users[0].partner_id:
            return {
                "create_date": member_0_create_date,
                "custom_channel_name": False,
                "custom_notifications": False,
                "fetched_message_id": False,
                "id": member_0.id,
                "is_favorite": False,
                "last_interest_dt": member_0_last_interest_dt,
                "message_unread_counter": 0,
                "message_unread_counter_bus_id": bus_last_id,
                "mute_until_dt": False,
                "last_seen_dt": member_0_last_seen_dt,
                "new_message_separator": 0,
                "partner_id": self.users[0].partner_id.id,
                "rtc_inviting_session_id": False,
                "seen_message_id": False,
                "unpin_dt": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_chat_2 and partner == self.users[15].partner_id:
            return {
                "create_date": fields.Datetime.to_string(member_15.create_date),
                "last_seen_dt": False,
                "fetched_message_id": False,
                "id": member_15.id,
                "partner_id": self.users[15].partner_id.id,
                "seen_message_id": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_chat_3 and partner == self.users[0].partner_id:
            return {
                "create_date": member_0_create_date,
                "custom_channel_name": False,
                "custom_notifications": False,
                "fetched_message_id": False,
                "id": member_0.id,
                "is_favorite": False,
                "last_interest_dt": member_0_last_interest_dt,
                "message_unread_counter": 0,
                "message_unread_counter_bus_id": bus_last_id,
                "mute_until_dt": False,
                "last_seen_dt": member_0_last_seen_dt,
                "new_message_separator": 0,
                "partner_id": self.users[0].partner_id.id,
                "rtc_inviting_session_id": False,
                "seen_message_id": False,
                "unpin_dt": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_chat_3 and partner == self.users[2].partner_id:
            return {
                "create_date": fields.Datetime.to_string(member_2.create_date),
                "last_seen_dt": False,
                "fetched_message_id": False,
                "id": member_2.id,
                "partner_id": self.users[2].partner_id.id,
                "seen_message_id": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_chat_4 and partner == self.users[0].partner_id:
            return {
                "create_date": member_0_create_date,
                "custom_channel_name": False,
                "custom_notifications": False,
                "fetched_message_id": False,
                "id": member_0.id,
                "is_favorite": False,
                "last_interest_dt": member_0_last_interest_dt,
                "message_unread_counter": 0,
                "message_unread_counter_bus_id": bus_last_id,
                "mute_until_dt": False,
                "last_seen_dt": member_0_last_seen_dt,
                "new_message_separator": 0,
                "partner_id": self.users[0].partner_id.id,
                "rtc_inviting_session_id": False,
                "seen_message_id": False,
                "unpin_dt": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_chat_4 and partner == self.users[3].partner_id:
            return {
                "create_date": fields.Datetime.to_string(member_3.create_date),
                "last_seen_dt": False,
                "fetched_message_id": False,
                "id": member_3.id,
                "partner_id": self.users[3].partner_id.id,
                "seen_message_id": False,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_livechat_1 and partner == self.users[0].partner_id:
            return {
                "create_date": member_0_create_date,
                "custom_channel_name": False,
                "custom_notifications": False,
                "fetched_message_id": False,
                "id": member_0.id,
                "is_favorite": False,
                "livechat_member_type": "agent",
                "last_interest_dt": member_0_last_interest_dt,
                "message_unread_counter": 1,
                "message_unread_counter_bus_id": bus_last_id,
                "mute_until_dt": False,
                "last_seen_dt": member_0_last_seen_dt,
                "new_message_separator": 0,
                "partner_id": self.users[0].partner_id.id,
                "rtc_inviting_session_id": False,
                "seen_message_id": False,
                "unpin_dt": fields.Datetime.to_string(member_0.unpin_dt),
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_livechat_1 and partner == self.users[1].partner_id:
            return {
                "create_date": fields.Datetime.to_string(member_1.create_date),
                "last_seen_dt": fields.Datetime.to_string(member_1.last_seen_dt),
                "fetched_message_id": last_message.id,
                "id": member_1.id,
                "livechat_member_type": "visitor",
                "partner_id": self.users[1].partner_id.id,
                "seen_message_id": last_message.id,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_livechat_2 and partner == self.users[0].partner_id:
            return {
                "create_date": member_0_create_date,
                "custom_channel_name": False,
                "custom_notifications": False,
                "fetched_message_id": False,
                "id": member_0.id,
                "is_favorite": False,
                "livechat_member_type": "agent",
                "last_interest_dt": member_0_last_interest_dt,
                "message_unread_counter": 1,
                "message_unread_counter_bus_id": bus_last_id,
                "mute_until_dt": False,
                "last_seen_dt": member_0_last_seen_dt,
                "new_message_separator": 0,
                "partner_id": self.users[0].partner_id.id,
                "rtc_inviting_session_id": False,
                "seen_message_id": False,
                "unpin_dt": fields.Datetime.to_string(member_0.unpin_dt),
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        if channel == self.channel_livechat_2 and guest:
            return {
                "create_date": fields.Datetime.to_string(member_g.create_date),
                "last_seen_dt": fields.Datetime.to_string(member_g.last_seen_dt),
                "fetched_message_id": last_message.id,
                "id": member_g.id,
                "livechat_member_type": "visitor",
                "guest_id": guest.id,
                "seen_message_id": last_message.id,
                "channel_id": {"id": channel.id, "model": "discuss.channel"},
            }
        return {}

    def _expected_result_for_livechat_channel(self):
        return {"id": self.im_livechat_channel.id, "name": "support"}

    def _expected_result_for_message(self, channel):
        last_message = channel._get_last_messages()
        create_date = fields.Datetime.to_string(last_message.create_date)
        date = fields.Datetime.to_string(last_message.date)
        write_date = fields.Datetime.to_string(last_message.write_date)
        user_0 = self.users[0]
        user_1 = self.users[1]
        user_2 = self.users[2]
        members = channel.channel_member_ids
        member_g = members.filtered(lambda m: m.guest_id)
        guest = member_g.guest_id
        if channel == self.channel_general:
            return {
                "attachment_ids": [],
                "author_guest_id": False,
                "author_id": user_0.partner_id.id,
                "body": ["markup", "<p>test</p>"],
                "create_date": create_date,
                "date": date,
                "default_subject": "general",
                "email_from": '"Ernest Employee" <e.e@example.com>',
                "id": last_message.id,
                "incoming_email_cc": False,
                "incoming_email_to": False,
                "message_link_preview_ids": [],
                "message_type": "comment",
                "model": "discuss.channel",
                "needaction": False,
                "needaction_done": False,
                "notification_ids": [],
                "parent_id": False,
                "partner_ids": [],
                "pinned_at": False,
                "rating_id": False,
                "reactions": [
                    {"content": "👍", "message": last_message.id},
                    {"content": "😁", "message": last_message.id},
                    {"content": "😊", "message": last_message.id},
                ],
                "record_name": "general",
                "res_id": 1,
                "scheduledDatetime": False,
                "starred": False,
                "subject": False,
                "subtype_id": self.env.ref("mail.mt_note").id,
                "thread": {"id": channel.id, "model": "discuss.channel"},
                "trackingValues": [],
                "write_date": write_date,
            }
        if channel == self.channel_channel_public_1:
            return {
                "attachment_ids": [],
                "author_guest_id": False,
                "author_id": user_2.partner_id.id,
                "body": ["markup", "<p>test</p>"],
                "create_date": create_date,
                "date": date,
                "default_subject": "public channel 1",
                "email_from": '"test2" <test2@example.com>',
                "id": last_message.id,
                "incoming_email_cc": False,
                "incoming_email_to": False,
                "message_link_preview_ids": [],
                "message_type": "comment",
                "model": "discuss.channel",
                "needaction": True,
                "needaction_done": False,
                "notification_ids": [last_message.notification_ids.id],
                "thread": {"id": channel.id, "model": "discuss.channel"},
                "parent_id": False,
                "partner_ids": [self.users[0].partner_id.id],
                "pinned_at": False,
                "rating_id": False,
                "reactions": [
                    {"content": "😁", "message": last_message.id},
                    {"content": "😊", "message": last_message.id},
                    {"content": "😏", "message": last_message.id},
                ],
                "record_name": "public channel 1",
                "res_id": channel.id,
                "scheduledDatetime": False,
                "starred": True,
                "subject": False,
                "subtype_id": self.env.ref("mail.mt_note").id,
                "trackingValues": [],
                "write_date": write_date,
            }
        if channel == self.channel_channel_public_2:
            return {
                "attachment_ids": [],
                "author_guest_id": False,
                "author_id": user_0.partner_id.id,
                "body": [
                    "markup",
                    '<div class="o_mail_notification">created this channel.</div>',
                ],
                "create_date": create_date,
                "date": date,
                "default_subject": "public channel 2",
                "email_from": '"Ernest Employee" <e.e@example.com>',
                "id": last_message.id,
                "incoming_email_cc": False,
                "incoming_email_to": False,
                "message_link_preview_ids": [],
                "message_type": "notification",
                "model": "discuss.channel",
                "needaction": False,
                "needaction_done": False,
                "notification_ids": [],
                "thread": {"id": channel.id, "model": "discuss.channel"},
                "parent_id": False,
                "partner_ids": [],
                "pinned_at": False,
                "rating_id": False,
                "reactions": [],
                "record_name": "public channel 2",
                "res_id": channel.id,
                "scheduledDatetime": False,
                "starred": False,
                "subject": False,
                "subtype_id": self.env.ref("mail.mt_comment").id,
                "trackingValues": [],
                "write_date": write_date,
            }
        if channel == self.channel_channel_group_1:
            return {
                "attachment_ids": [],
                "author_guest_id": False,
                "author_id": self.user_root.partner_id.id,
                "body": [
                    "markup",
                    '<div data-oe-type="call" class="o_mail_notification"></div>',
                ],
                "call_history_ids": [channel.call_history_ids[0].id],
                "create_date": create_date,
                "date": date,
                "default_subject": "group restricted channel 1",
                "email_from": '"OdooBot" <odoobot@example.com>',
                "id": last_message.id,
                "incoming_email_cc": False,
                "incoming_email_to": False,
                "message_link_preview_ids": [],
                "message_type": "notification",
                "model": "discuss.channel",
                "needaction": False,
                "needaction_done": False,
                "notification_ids": [],
                "thread": {"id": channel.id, "model": "discuss.channel"},
                "parent_id": False,
                "partner_ids": [],
                "pinned_at": False,
                "rating_id": False,
                "reactions": [],
                "record_name": "group restricted channel 1",
                "res_id": channel.id,
                "scheduledDatetime": False,
                "starred": False,
                "subject": False,
                "subtype_id": self.env.ref("mail.mt_note").id,
                "trackingValues": [],
                "write_date": write_date,
            }
        if channel == self.channel_channel_group_2:
            return {
                "attachment_ids": [],
                "author_guest_id": False,
                "author_id": user_0.partner_id.id,
                "body": [
                    "markup",
                    '<div class="o_mail_notification">created this channel.</div>',
                ],
                "create_date": create_date,
                "date": date,
                "default_subject": "group restricted channel 2",
                "email_from": '"Ernest Employee" <e.e@example.com>',
                "id": last_message.id,
                "incoming_email_cc": False,
                "incoming_email_to": False,
                "message_link_preview_ids": [],
                "message_type": "notification",
                "model": "discuss.channel",
                "needaction": False,
                "needaction_done": False,
                "notification_ids": [],
                "thread": {"id": channel.id, "model": "discuss.channel"},
                "parent_id": False,
                "partner_ids": [],
                "pinned_at": False,
                "rating_id": False,
                "reactions": [],
                "record_name": "group restricted channel 2",
                "res_id": channel.id,
                "scheduledDatetime": False,
                "starred": False,
                "subject": False,
                "subtype_id": self.env.ref("mail.mt_comment").id,
                "trackingValues": [],
                "write_date": write_date,
            }
        if channel == self.channel_livechat_1:
            return {
                "attachment_ids": [],
                "author_guest_id": False,
                "author_id": user_1.partner_id.id,
                "body": ["markup", "<p>test</p>"],
                "create_date": create_date,
                "date": date,
                "default_subject": "test1 Ernest Employee",
                "email_from": '"test1" <test1@example.com>',
                "id": last_message.id,
                "incoming_email_cc": False,
                "incoming_email_to": False,
                "message_link_preview_ids": [],
                "message_type": "comment",
                "model": "discuss.channel",
                "needaction": False,
                "needaction_done": False,
                "notification_ids": [],
                "thread": {"id": channel.id, "model": "discuss.channel"},
                "parent_id": False,
                "partner_ids": [],
                "pinned_at": False,
                "rating_id": False,
                "reactions": [],
                "record_name": "test1 Ernest Employee",
                "res_id": channel.id,
                "scheduledDatetime": False,
                "starred": False,
                "subject": False,
                "subtype_id": self.env.ref("mail.mt_note").id,
                "trackingValues": [],
                "write_date": write_date,
            }
        if channel == self.channel_livechat_2:
            return {
                "attachment_ids": [],
                "author_guest_id": guest.id,
                "author_id": False,
                "body": ["markup", "<p>test</p>"],
                "create_date": create_date,
                "date": date,
                "default_subject": "Visitor Ernest Employee",
                "email_from": False,
                "id": last_message.id,
                "incoming_email_cc": False,
                "incoming_email_to": False,
                "message_link_preview_ids": [],
                "message_type": "comment",
                "model": "discuss.channel",
                "needaction": False,
                "needaction_done": False,
                "notification_ids": [],
                "thread": {"id": channel.id, "model": "discuss.channel"},
                "parent_id": False,
                "partner_ids": [],
                "pinned_at": False,
                "rating_id": False,
                "reactions": [],
                "record_name": "Visitor Ernest Employee",
                "res_id": channel.id,
                "scheduledDatetime": False,
                "starred": False,
                "subject": False,
                "subtype_id": self.env.ref("mail.mt_comment").id,
                "trackingValues": [],
                "write_date": write_date,
            }
        return {}

    def _expected_result_for_message_reactions(self, channel):
        last_message = channel._get_last_messages()
        partner_0 = self.users[0].partner_id.id
        partner_1 = self.users[1].partner_id.id
        partner_2 = self.users[2].partner_id.id
        reactions_0 = last_message.sudo().reaction_ids.filtered(
            lambda r: r.content == "👍"
        )
        reactions_1 = last_message.sudo().reaction_ids.filtered(
            lambda r: r.content == "😁"
        )
        reactions_2 = last_message.sudo().reaction_ids.filtered(
            lambda r: r.content == "😊"
        )
        reactions_3 = last_message.sudo().reaction_ids.filtered(
            lambda r: r.content == "😏"
        )
        if channel == self.channel_general:
            return [
                {
                    "content": "👍",
                    "count": 1,
                    "guests": [],
                    "message": last_message.id,
                    "partners": [partner_2],
                    "sequence": min(reactions_0.ids),
                },
                {
                    "content": "😁",
                    "count": 2,
                    "guests": [],
                    "message": last_message.id,
                    "partners": [partner_2, partner_1],
                    "sequence": min(reactions_1.ids),
                },
                {
                    "content": "😊",
                    "count": 3,
                    "guests": [],
                    "message": last_message.id,
                    "partners": [partner_2, partner_1, partner_0],
                    "sequence": min(reactions_2.ids),
                },
            ]
        if channel == self.channel_channel_public_1:
            return [
                {
                    "content": "😁",
                    "count": 1,
                    "guests": [],
                    "message": last_message.id,
                    "partners": [partner_2],
                    "sequence": min(reactions_1.ids),
                },
                {
                    "content": "😊",
                    "count": 3,
                    "guests": [],
                    "message": last_message.id,
                    "partners": [partner_2, partner_1, partner_0],
                    "sequence": min(reactions_2.ids),
                },
                {
                    "content": "😏",
                    "count": 2,
                    "guests": [],
                    "message": last_message.id,
                    "partners": [partner_1, partner_0],
                    "sequence": min(reactions_3.ids),
                },
            ]
        return []

    def _expected_result_for_notification(self, channel):
        last_message = channel._get_last_messages()
        if channel == self.channel_channel_public_1:
            return {
                "mail_email_address": False,
                "failure_type": False,
                "id": last_message.notification_ids.id,
                "mail_message_id": last_message.id,
                "notification_status": "sent",
                "notification_type": "inbox",
                "res_partner_id": self.users[0].partner_id.id,
            }
        return {}

    def _expected_result_for_persona(
        self,
        user=None,
        guest=None,
        only_inviting=False,
        also_livechat=False,
        also_notification=False,
    ):
        if user == self.users[0]:
            res = {
                "active": True,
                "avatar_128_access_token": user.partner_id._get_avatar_128_access_token(),
                "email": "e.e@example.com",
                "id": user.partner_id.id,
                "im_status": "online",
                "im_status_access_token": user.partner_id._get_im_status_access_token(),
                "is_company": False,
                "main_user_id": user.id,
                "mention_token": user.partner_id._get_mention_token(),
                "name": "Ernest Employee",
                "write_date": fields.Datetime.to_string(user.partner_id.write_date),
            }
            if also_livechat:
                res.update(
                    {
                        "country_id": False,
                        "is_public": False,
                        "user_livechat_username": False,
                    }
                )
            if also_notification:
                res["name"] = "Ernest Employee"
            return res
        if user == self.users[1]:
            res = {
                "active": True,
                "avatar_128_access_token": user.partner_id._get_avatar_128_access_token(),
                "country_id": self.env.ref("base.in").id,
                "id": user.partner_id.id,
                "im_status": "offline",
                "im_status_access_token": user.partner_id._get_im_status_access_token(),
                "is_company": False,
                "is_public": False,
                "main_user_id": user.id,
                "name": "test1",
                "mention_token": user.partner_id._get_mention_token(),
                "write_date": fields.Datetime.to_string(user.partner_id.write_date),
            }
            if also_livechat:
                res["offline_since"] = False
                res["user_livechat_username"] = False
                res["email"] = user.email
            return res
        if user == self.users[2]:
            if only_inviting:
                return {
                    "avatar_128_access_token": user.partner_id._get_avatar_128_access_token(),
                    "id": user.partner_id.id,
                    "im_status": "offline",
                    "im_status_access_token": user.partner_id._get_im_status_access_token(),
                    "name": "test2",
                    "mention_token": user.partner_id._get_mention_token(),
                    "write_date": fields.Datetime.to_string(user.partner_id.write_date),
                }
            return {
                "active": True,
                "avatar_128_access_token": user.partner_id._get_avatar_128_access_token(),
                "email": "test2@example.com",
                "id": user.partner_id.id,
                "im_status": "offline",
                "im_status_access_token": user.partner_id._get_im_status_access_token(),
                "is_company": False,
                "main_user_id": user.id,
                "mention_token": user.partner_id._get_mention_token(),
                "name": "test2",
                "write_date": fields.Datetime.to_string(user.partner_id.write_date),
            }
        if user == self.users[3]:
            return {
                "active": True,
                "avatar_128_access_token": user.partner_id._get_avatar_128_access_token(),
                "email": False,
                "id": user.partner_id.id,
                "im_status": "offline",
                "im_status_access_token": user.partner_id._get_im_status_access_token(),
                "is_company": False,
                "main_user_id": user.id,
                "mention_token": user.partner_id._get_mention_token(),
                "name": "test3",
                "write_date": fields.Datetime.to_string(
                    self.users[3].partner_id.write_date
                ),
            }
        if user == self.users[12]:
            return {
                "active": True,
                "avatar_128_access_token": user.partner_id._get_avatar_128_access_token(),
                "email": False,
                "id": user.partner_id.id,
                "im_status": "offline",
                "im_status_access_token": user.partner_id._get_im_status_access_token(),
                "is_company": False,
                "main_user_id": user.id,
                "mention_token": user.partner_id._get_mention_token(),
                "name": "test12",
                "write_date": fields.Datetime.to_string(user.partner_id.write_date),
            }
        if user == self.users[14]:
            return {
                "active": True,
                "avatar_128_access_token": user.partner_id._get_avatar_128_access_token(),
                "email": False,
                "id": user.partner_id.id,
                "im_status": "offline",
                "im_status_access_token": user.partner_id._get_im_status_access_token(),
                "is_company": False,
                "main_user_id": user.id,
                "mention_token": user.partner_id._get_mention_token(),
                "name": "test14",
                "write_date": fields.Datetime.to_string(user.partner_id.write_date),
            }
        if user == self.users[15]:
            return {
                "active": True,
                "avatar_128_access_token": user.partner_id._get_avatar_128_access_token(),
                "email": False,
                "id": user.partner_id.id,
                "im_status": "offline",
                "im_status_access_token": user.partner_id._get_im_status_access_token(),
                "is_company": False,
                "main_user_id": user.id,
                "mention_token": user.partner_id._get_mention_token(),
                "name": "test15",
                "write_date": fields.Datetime.to_string(user.partner_id.write_date),
            }
        if user == self.user_root:
            return {
                "avatar_128_access_token": user.partner_id._get_avatar_128_access_token(),
                "id": user.partner_id.id,
                "is_company": False,
                "main_user_id": user.id,
                "name": "OdooBot",
                "write_date": fields.Datetime.to_string(user.partner_id.write_date),
            }
        if guest:
            return {
                "avatar_128_access_token": self.guest._get_avatar_128_access_token(),
                "country_id": self.guest.country_id.id,
                "id": self.guest.id,
                "im_status": "offline",
                "im_status_access_token": self.guest._get_im_status_access_token(),
                "name": "Visitor",
                "offline_since": False,
                "write_date": fields.Datetime.to_string(self.guest.write_date),
            }
        return {}

    def _expected_result_for_rtc_session(self, channel, user):
        members = channel.channel_member_ids
        member_2 = members.filtered(lambda m: m.partner_id == self.users[2].partner_id)
        if channel == self.channel_channel_group_1 and user == self.users[2]:
            return {
                "channel_member_id": member_2.id,
                "id": member_2.sudo().rtc_session_ids.id,
                "is_camera_on": False,
                "is_deaf": False,
                "is_screen_sharing_on": False,
                "is_muted": False,
            }
        return {}

    def _expected_result_for_thread(self, channel):
        common_data = {
            "has_mail_thread": True,
            "id": channel.id,
            "model": "discuss.channel",
            "module_icon": "/mail/static/description/icon.png",
            "rating_avg": 0.0,
            "rating_count": 0,
        }
        if channel == self.channel_general:
            return {**common_data, "display_name": "general"}
        if channel == self.channel_channel_public_1:
            return {**common_data, "display_name": "public channel 1"}
        if channel == self.channel_channel_public_2:
            return {**common_data, "display_name": "public channel 2"}
        if channel == self.channel_channel_group_1:
            return {**common_data, "display_name": "group restricted channel 1"}
        if channel == self.channel_channel_group_2:
            return {**common_data, "display_name": "group restricted channel 2"}
        if channel == self.channel_livechat_1:
            return {**common_data, "display_name": "test1 Ernest Employee"}
        if channel == self.channel_livechat_2:
            return {**common_data, "display_name": "Visitor Ernest Employee"}
        return {}

    def _res_for_user(self, user):
        if user == self.users[0]:
            return {
                "id": user.id,
                "partner_id": user.partner_id.id,
                "employee_ids": user.employee_ids.ids,
                "share": False,
            }
        if user == self.users[1]:
            return {"id": user.id, "partner_id": user.partner_id.id, "share": False}
        if user == self.users[2]:
            return {
                "id": user.id,
                "partner_id": user.partner_id.id,
                "employee_ids": user.employee_ids.ids,
                "share": False,
            }
        if user == self.users[3]:
            return {
                "id": user.id,
                "partner_id": user.partner_id.id,
                "employee_ids": user.employee_ids.ids,
                "share": False,
            }
        if user == self.users[12]:
            return {
                "id": user.id,
                "partner_id": user.partner_id.id,
                "employee_ids": user.employee_ids.ids,
                "share": False,
            }
        if user == self.users[14]:
            return {
                "id": user.id,
                "partner_id": user.partner_id.id,
                "employee_ids": user.employee_ids.ids,
                "share": False,
            }
        if user == self.users[15]:
            return {
                "id": user.id,
                "partner_id": user.partner_id.id,
                "employee_ids": user.employee_ids.ids,
                "share": False,
            }
        if user == self.user_root:
            return {"id": user.id, "partner_id": user.partner_id.id, "share": False}
        return {}

    def _res_for_employee(self, employee):
        return {
            "id": employee.id,
            "leave_date_to": False,
        }
