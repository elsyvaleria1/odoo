from odoo.tests import counting_statements
from odoo.tests.common import HttpCase, new_test_user, tagged

from odoo.addons.mail.tests.common import MailCommon


@tagged("post_install", "-at_install")
class TestDiscussReadScaling(HttpCase, MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.colleagues = cls.env["res.users"].union(
            *(
                new_test_user(
                    cls.env,
                    login=f"scaling_colleague_{index}",
                    name=f"Scaling Colleague {index}",
                    groups="base.group_user",
                )
                for index in range(6)
            )
        )
        cls.readers = {
            units: new_test_user(
                cls.env,
                login=f"scaling_reader_{units}",
                password=f"scaling_reader_{units}",
                name=f"Scaling Reader {units}",
                groups="base.group_user",
            )
            for units in (2, 6)
        }
        for units, reader in cls.readers.items():
            cls._create_channels(reader, units)

    @classmethod
    def _create_channels(cls, reader, units):
        Channel = cls.env["discuss.channel"].with_user(reader)
        for index in range(units):
            colleague = cls.colleagues[index]
            Channel._get_or_create_chat([colleague.partner_id.id])
            Channel._create_group(
                [colleague.partner_id.id, cls.colleagues[index - 1].partner_id.id],
                name=f"Group {units}-{index}",
            )
            channel = Channel._create_channel(f"Channel {units}-{index}", None)
            question = channel.message_post(
                body=f"<p>Question {index}</p>", message_type="comment"
            )
            channel._create_sub_channel(from_message_id=question.id)
            channel.message_post(
                body=f"<p>Answer {index}</p>",
                message_type="comment",
                parent_id=question.id,
            )

    def _statements(self, route, params):
        self.call_jsonrpc(route, params)
        self.env.flush_all()
        self.env.invalidate_all()
        with counting_statements(self.cr) as statements:
            self.call_jsonrpc(route, params)
            return statements.count

    def _statements_by_units(self, params):
        counts = {}
        for units, reader in self.readers.items():
            self.authenticate(reader.login, reader.login)
            counts[units] = self._statements("/mail/data", params)
        return counts

    def test_channel_tabs_are_flat_in_channels(self):
        counts = self._statements_by_units(
            {
                "fetch_params": [
                    [
                        "/mail/messaging_menu/discuss.channel/load_more",
                        {"tab_id": tab_id, "limit": 20},
                    ]
                    for tab_id in ("chat", "channel")
                ]
            }
        )
        self.assertEqual(
            counts[6],
            counts[2],
            "loading a channel tab must not issue statements per channel",
        )

    def test_counters_are_flat_in_channels(self):
        counts = self._statements_by_units(
            {
                "fetch_params": [
                    [
                        "/mail/messaging_menu/initialize_counters",
                        {
                            "filter_id_by_tab_id_by_record_type": {
                                "discuss.channel": {
                                    "chat": None,
                                    "channel": None,
                                    "livechat": None,
                                }
                            },
                            "presence_tab_ids": ["livechat"],
                        },
                    ]
                ]
            }
        )
        self.assertEqual(
            counts[6],
            counts[2],
            "counting the unread channels must not issue statements per channel",
        )

    def test_channel_messages_are_flat_in_messages(self):
        reader = self.readers[2]
        channel = (
            self.env["discuss.channel"]
            .with_user(reader)
            ._create_channel("Replies", None)
        )
        questions = [
            channel.message_post(
                body=f"<p>Question {index}</p>", message_type="comment"
            )
            for index in range(25)
        ]
        for question in questions:
            channel.message_post(
                body="<p>Answer</p>", message_type="comment", parent_id=question.id
            )
        self.authenticate(reader.login, reader.login)
        counts = {
            limit: self._statements(
                "/discuss/channel/messages",
                {"channel_id": channel.id, "fetch_params": {"limit": limit}},
            )
            for limit in (5, 25)
        }
        self.assertEqual(
            counts[25],
            counts[5],
            "fetching more messages must not issue statements per message",
        )
