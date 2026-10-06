from odoo import Command
from odoo.tests import tagged, users

from odoo.addons.mail.tests.common import MailCommon
from odoo.addons.mail.tools.discuss import Store


@tagged("mail_performance", "post_install", "-at_install")
class TestMailReadScaling(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.authors = cls.env["res.partner"].create(
            [
                {"name": f"Author {index}", "email": f"author.{index}@example.com"}
                for index in range(25)
            ]
        )

    def _statements(self, function):
        function()
        self.env.flush_all()
        self.env.invalidate_all()
        before = self.env.cr.sql_statement_count
        function()
        return self.env.cr.sql_statement_count - before

    def _assert_flat(self, serialize, small, large):
        self.assertEqual(
            self._statements(lambda: serialize(large)),
            self._statements(lambda: serialize(small)),
            "serializing more records must not issue more statements",
        )

    @users("employee")
    def test_chatter_messages_store_is_flat(self):
        record = self.env["mail.test.track"].sudo().create({"name": "Scaling record"})
        user_field = self.env["ir.model.fields"]._get("mail.test.track", "user_id")
        preview = (
            self.env["mail.link.preview"]
            .sudo()
            .create({"source_url": "https://www.example.com", "og_title": "Example"})
        )
        messages = (
            self.env["mail.message"]
            .sudo()
            .create(
                [
                    {
                        "attachment_ids": [
                            Command.create(
                                {
                                    "name": f"file {index}.txt",
                                    "raw": b"data",
                                    "res_id": record.id,
                                    "res_model": record._name,
                                }
                            )
                        ],
                        "author_id": author.id,
                        "body": f"<p>Message {index}</p>",
                        "message_link_preview_ids": [
                            Command.create({"link_preview_id": preview.id})
                        ],
                        "message_type": "comment",
                        "model": record._name,
                        "notification_ids": [
                            Command.create(
                                {
                                    "is_read": False,
                                    "notification_type": "inbox",
                                    "res_partner_id": self.partner_employee.id,
                                }
                            )
                        ],
                        "partner_ids": [
                            Command.link(author.id),
                            Command.link(self.partner_employee.id),
                        ],
                        "reaction_ids": [
                            Command.create(
                                {"content": "\U0001f44d", "partner_id": author.id}
                            ),
                            Command.create(
                                {
                                    "content": "\U0001f389",
                                    "partner_id": self.partner_employee.id,
                                }
                            ),
                        ],
                        "res_id": record.id,
                        "starred_partner_ids": [Command.link(self.partner_employee.id)],
                        "subtype_id": self.env.ref("mail.mt_comment").id,
                        "tracking_value_ids": [
                            Command.create(
                                {
                                    "field_id": user_field.id,
                                    "new_value_char": self.user_employee.name,
                                    "new_value_integer": self.user_employee.id,
                                    "old_value_char": self.user_admin.name,
                                    "old_value_integer": self.user_admin.id,
                                }
                            )
                        ],
                    }
                    for index, author in enumerate(self.authors)
                ]
            )
            .with_env(self.env)
        )
        self._assert_flat(
            lambda batch: Store().add(batch).get_result(), messages[:5], messages
        )

    @users("employee")
    def test_channel_replies_store_is_flat(self):
        channel = self.env["discuss.channel"]._create_channel("Replies", None)
        parents = (
            self.env["mail.message"]
            .sudo()
            .create(
                [
                    {
                        "author_id": author.id,
                        "body": f"<p>Question {index}</p>",
                        "message_type": "comment",
                        "model": "discuss.channel",
                        "res_id": channel.id,
                    }
                    for index, author in enumerate(self.authors)
                ]
            )
        )
        replies = (
            self.env["mail.message"]
            .sudo()
            .create(
                [
                    {
                        "author_id": self.partner_employee.id,
                        "body": f"<p>Answer to {parent.id}</p>",
                        "message_type": "comment",
                        "model": "discuss.channel",
                        "parent_id": parent.id,
                        "res_id": channel.id,
                    }
                    for parent in parents
                ]
            )
            .with_env(self.env)
        )
        self._assert_flat(
            lambda batch: Store().add(batch).get_result(), replies[:5], replies
        )

    @users("employee")
    def test_sub_channels_store_is_flat(self):
        Channel = self.env["discuss.channel"]
        parents = Channel.browse()
        sub_channels = Channel.browse()
        for index in range(25):
            parent = Channel._create_channel(f"Parent {index}", None)
            origin = parent.message_post(
                body=f"<p>Origin {index}</p>", message_type="comment"
            )
            parents |= parent
            sub_channels |= parent._create_sub_channel(from_message_id=origin.id)
        self._assert_flat(
            lambda batch: Store().add(batch).get_result(),
            parents[:5] | sub_channels[:5],
            parents | sub_channels,
        )
