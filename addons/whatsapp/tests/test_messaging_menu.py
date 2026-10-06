from datetime import timedelta

from odoo import fields
from odoo.tests import JsonRpcException, tagged
from odoo.tools import mute_logger

from odoo.addons.whatsapp.tests.common import MockIncomingWhatsApp, WhatsAppCommon

COUNTERS = "/mail/messaging_menu/initialize_counters"
CHANNEL_LOAD_MORE = "/mail/messaging_menu/discuss.channel/load_more"


@tagged("-at_install", "post_install", "wa_message", "messaging_menu")
class TestWhatsappMessagingMenu(WhatsAppCommon, MockIncomingWhatsApp):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        channel_values = {
            "channel_partner_ids": [(4, cls.user_wa_admin.partner_id.id)],
            "channel_type": "whatsapp",
            "wa_account_id": cls.whatsapp_account.id,
            "whatsapp_number": "911234567891",
            "whatsapp_partner_id": cls.whatsapp_customer.id,
        }
        cls.unread_channel, cls.read_channel, cls.unpinned_channel = cls.env[
            "discuss.channel"
        ].create(
            [
                {**channel_values, "name": "WA Unread"},
                {**channel_values, "name": "WA Read"},
                {**channel_values, "name": "WA Unpinned"},
            ]
        )
        cls.std_channel = cls.env["discuss.channel"].create(
            {
                "channel_partner_ids": [(4, cls.user_wa_admin.partner_id.id)],
                "channel_type": "channel",
                "name": "Standard Channel",
            }
        )
        for channel in cls.unread_channel | cls.read_channel | cls.unpinned_channel:
            channel.message_post(
                author_id=cls.whatsapp_customer.id,
                body="Hello",
                message_type="whatsapp_message",
                subtype_xmlid="mail.mt_comment",
            )
        cls._admin_member(cls.read_channel)._mark_as_read(
            cls.read_channel.message_ids[:1].id
        )
        past = fields.Datetime.now() - timedelta(hours=1)
        cls.unpinned_channel.last_interest_dt = past
        unpinned_member = cls._admin_member(cls.unpinned_channel)
        unpinned_member.last_interest_dt = past
        unpinned_member.unpin_dt = fields.Datetime.now()

    @classmethod
    def _admin_member(cls, channel):
        return cls.env["discuss.channel.member"].search(
            [
                ("channel_id", "=", channel.id),
                ("partner_id", "=", cls.user_wa_admin.partner_id.id),
            ]
        )

    def _mail_data(self, *fetch_params):
        return self.call_jsonrpc("/mail/data", {"fetch_params": list(fetch_params)})

    def _load_more_ids(self, filter_ids=()):
        data = self._mail_data(
            [
                CHANNEL_LOAD_MORE,
                {"tab_id": "whatsapp", "limit": 10, "filter_ids": list(filter_ids)},
                "whatsapp",
            ]
        )
        return sorted(channel["id"] for channel in data.get("discuss.channel", []))

    def test_load_more(self):
        self.authenticate("user_wa_admin", "user_wa_admin")
        self.assertEqual(
            self._load_more_ids(),
            sorted((self.unread_channel | self.read_channel).ids),
            "pinned WhatsApp conversations only",
        )
        self.assertEqual(
            self._load_more_ids(["whatsapp_unread"]), self.unread_channel.ids
        )

    def test_initialize_counters(self):
        self.authenticate("user_wa_admin", "user_wa_admin")
        data = self._mail_data(
            [
                COUNTERS,
                {
                    "filter_id_by_tab_id_by_record_type": {
                        "discuss.channel": {"whatsapp": None}
                    }
                },
            ]
        )
        self.assertEqual(
            data["MessagingMenuTab"],
            [{"id": "whatsapp", "init_counter_ids": self.unread_channel.ids}],
        )

    @mute_logger("odoo.http")
    def test_unknown_whatsapp_filter_fails(self):
        self.authenticate("user_wa_admin", "user_wa_admin")
        for tab_id, filter_id in (
            ("whatsapp", "chat_unread"),
            ("chat", "whatsapp_unread"),
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
