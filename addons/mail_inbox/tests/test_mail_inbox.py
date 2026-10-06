from psycopg.errors import IntegrityError

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger
from odoo.tools.mail import email_normalize

from odoo.addons.mail.tests.common import MailCommon, mail_new_test_user
from odoo.addons.mail_inbox.controllers.messaging_menu import (
    InboxMessagingMenuController,
)

CORRESPONDENT = "Carla Customer <carla@customer.example>"


@tagged("post_install", "-at_install")
class TestMailInbox(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.inbox_domain = cls.env["mail.alias.domain"].create(
            {
                "name": "inbox.example.com",
                "bounce_alias": "bounce-inbox",
                "catchall_alias": "catchall-inbox",
            }
        )
        cls.user_billing = mail_new_test_user(
            cls.env,
            login="inbox_billing",
            groups="base.group_user",
            name="Bea Billing",
            email="bea@inbox.example.com",
        )
        cls.inbox = cls.env["mail.inbox"].create(
            {
                "name": "Billing",
                "kind": "shared",
                "alias_name": "billing",
                "alias_domain_id": cls.inbox_domain.id,
                "user_ids": [Command.set((cls.user_employee | cls.user_billing).ids)],
            }
        )

    def _receive(
        self, message_id, subject="Invoice 7", email_from=CORRESPONDENT, extra=""
    ):
        raw = (
            f"From: {email_from}\r\n"
            "To: billing@inbox.example.com\r\n"
            f"Subject: {subject}\r\n"
            f"Message-Id: <{message_id}>\r\n"
            f"{extra}"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Hello\r\n"
        ).encode()
        self.env["mixin.mail.thread"].message_process(False, raw)
        return self.inbox.channel_ids

    def test_a_new_correspondent_opens_a_conversation(self):
        channel = self._receive("first@customer")
        self.assertEqual(len(channel), 1)
        self.assertEqual(channel.channel_type, "email")
        self.assertEqual(
            channel.correspondent_partner_id.email, "carla@customer.example"
        )
        self.assertEqual(
            channel.channel_member_ids.partner_id,
            self.user_employee.partner_id
            | self.user_billing.partner_id
            | channel.correspondent_partner_id,
        )
        self.assertEqual(channel.message_ids.message_id, "<first@customer>")

    def test_the_same_correspondent_returns_to_the_same_conversation(self):
        self._receive("one@customer", subject="Invoice 7")
        channel = self._receive("two@customer", subject="Another question")
        self.assertEqual(len(channel), 1, "one conversation per correspondent")
        self.assertEqual(len(channel.message_ids), 2)
        other = self._receive("three@other", email_from="Otto <otto@other.example>")
        self.assertEqual(len(other), 2, "another correspondent, another conversation")

    def test_an_inbound_message_is_not_mailed_back(self):
        with self.mock_mail_gateway():
            channel = self._receive("quiet@customer")
        self.assertFalse(
            self._new_mails.filtered(
                lambda m: channel.correspondent_partner_id in m.recipient_ids
            )
        )

    def test_a_reply_from_discuss_is_mailed_from_the_inbox(self):
        channel = self._receive("ask@customer")
        with self.mock_mail_gateway():
            channel.with_user(self.user_employee).message_post(
                body="It is paid.",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        mail = self._new_mails.filtered(
            lambda m: channel.correspondent_partner_id in m.recipient_ids
        )
        self.assertEqual(len(mail), 1)
        self.assertIn("billing@inbox.example.com", mail.email_from)
        self.assertIn(self.user_employee.name, mail.email_from)
        self.assertEqual(email_normalize(mail.reply_to), "billing@inbox.example.com")
        self.assertEqual(mail.subject, "Re: Invoice 7")
        self.assertIn("<ask@customer>", mail.references)
        self.assertEqual((mail.headers or {}).get("In-Reply-To"), "<ask@customer>")
        self.assertIn("It is paid.", mail.body_html)
        self.assertNotIn(
            "Powered by", mail.body_html, "a person's email, not a notification"
        )

    def test_the_correspondent_s_reply_lands_in_the_conversation(self):
        channel = self._receive("start@customer")
        with self.mock_mail_gateway():
            answer = channel.with_user(self.user_employee).message_post(
                body="Which invoice?",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        self._receive(
            "reply@customer",
            subject="Re: Invoice 7",
            extra=f"In-Reply-To: {answer.message_id}\r\nReferences: {answer.message_id}\r\n",
        )
        self.assertEqual(len(self.inbox.channel_ids), 1)
        self.assertIn("<reply@customer>", channel.message_ids.mapped("message_id"))

    def test_a_personal_inbox_belongs_to_one_user(self):
        with self.assertRaises(ValidationError):
            self.env["mail.inbox"].create(
                {
                    "name": "Nobody's",
                    "kind": "personal",
                    "alias_name": "nobody",
                    "alias_domain_id": self.inbox_domain.id,
                }
            )

    def test_the_inbox_s_users_follow_its_conversations(self):
        channel = self._receive("members@customer")
        self.inbox.user_ids = [Command.unlink(self.user_billing.id)]
        self.assertNotIn(
            self.user_billing.partner_id, channel.channel_member_ids.partner_id
        )
        self.assertIn(
            channel.correspondent_partner_id, channel.channel_member_ids.partner_id
        )
        self.inbox.user_ids = [Command.link(self.user_billing.id)]
        self.assertIn(
            self.user_billing.partner_id, channel.channel_member_ids.partner_id
        )

    def test_a_user_reads_only_the_inboxes_they_answer(self):
        outsider = mail_new_test_user(
            self.env, login="inbox_outsider", groups="base.group_user", name="Olga"
        )
        Inbox = self.env["mail.inbox"]
        self.assertEqual(Inbox.with_user(self.user_billing).search([]), self.inbox)
        self.assertFalse(Inbox.with_user(outsider).search([]))
        channel = self._receive("private@customer")
        self.assertFalse(
            self.env["discuss.channel"]
            .with_user(outsider)
            .search([("id", "=", channel.id)]),
            "an email conversation is its members' only",
        )

    def test_the_recipient_view_lists_the_inbox_address(self):
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT kind FROM mail_gateway_recipient WHERE address = %s",
            ["billing@inbox.example.com"],
        )
        self.assertEqual(self.env.cr.fetchall(), [("alias",)])

    def test_mail_from_one_of_our_addresses_still_opens_a_conversation(self):
        channel = self._receive(
            "from-alias@inbox",
            email_from="Catchall <catchall-inbox@inbox.example.com>",
        )
        self.assertEqual(len(channel), 1)
        self.assertEqual(
            channel.correspondent_partner_id.email_normalized,
            "catchall-inbox@inbox.example.com",
        )

    def test_an_inbox_with_conversations_is_archived_not_deleted(self):
        self._receive("kept@customer")
        with self.assertRaises(IntegrityError), mute_logger("odoo.db.cursor"):
            with self.env.cr.savepoint():
                self.inbox.unlink()
                self.env.flush_all()

    def test_the_email_tab_lists_the_member_s_conversations(self):
        channel = self._receive("tab@customer")
        domain = InboxMessagingMenuController._get_menu_tab_domain("email")
        Channel = self.env["discuss.channel"]
        self.assertEqual(Channel.with_user(self.user_billing).search(domain), channel)
        outsider = mail_new_test_user(
            self.env, login="inbox_tab_outsider", groups="base.group_user", name="Tess"
        )
        self.assertFalse(Channel.with_user(outsider).search(domain))

    def test_the_email_names_the_message_s_author(self):
        channel = self._receive("author@customer")
        with self.mock_mail_gateway():
            channel.with_user(self.user_employee).message_post(
                body="Signed by Bea.",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                author_id=self.user_billing.partner_id.id,
            )
        mail = self._new_mails.filtered(
            lambda m: channel.correspondent_partner_id in m.recipient_ids
        )
        self.assertIn(self.user_billing.name, mail.email_from)
        self.assertIn("billing@inbox.example.com", mail.email_from)

    def test_an_archived_inbox_answers_no_mail_until_restored(self):
        def answered():
            self.env.flush_all()
            self.env.cr.execute(
                "SELECT 1 FROM mail_gateway_recipient WHERE address = %s",
                ["billing@inbox.example.com"],
            )
            return bool(self.env.cr.fetchall())

        self.assertTrue(answered())
        self.inbox.action_archive()
        self.assertFalse(
            answered(), "the edge refuses the address of an archived inbox"
        )
        self.assertFalse(self.inbox.alias_name)
        self.inbox.action_unarchive()
        self.assertEqual(self.inbox.alias_name, "billing")
        self.assertTrue(answered())
