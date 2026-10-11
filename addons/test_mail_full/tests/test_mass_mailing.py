from urllib.parse import parse_qsl, urlsplit

from odoo.tests import tagged
from odoo.tests.common import users
from odoo.tools import mute_logger

from odoo.addons.test_mail_full.tests.common import TestMailFullCommon


@tagged("mass_mailing")
class TestMassMailing(TestMailFullCommon):
    @users("user_marketing")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mailing_w_blacklist_opt_out(self):
        mailing = self.env["mailing.mailing"].browse(self.mailing_bl.ids)
        mailing.write({"subject": "Subject {{ object.name }}"})

        mailing.write(
            {"mailing_model_id": self.env["ir.model"]._get("mailing.test.optout").id}
        )
        recipients = self._create_mailing_test_records(
            model="mailing.test.optout", count=10
        )

        (recipients[1] | recipients[2]).write({"opt_out": True})
        recipients[1].email_from = f'"Format Me" <{recipients[1].email_normalized}>'
        self.env["mail.blacklist"].create({"email": recipients[3].email_normalized})
        self.env["mail.blacklist"].create({"email": recipients[4].email_normalized})
        recipients[3].email_from = f'"Format Me" <{recipients[3].email_normalized}>'
        recipients[9].email_from = f'"Format Me" <{recipients[9].email_normalized}>'
        recipient_dup_1 = recipients[9].copy()
        recipient_dup_1.email_from = f'"Format Me" <{recipient_dup_1.email_normalized}>'
        recipient_dup_2 = recipients[9].copy()
        recipient_dup_2.email_from += f'; "TestDupe" <{recipients[8].email_normalized}>'
        recipient_dup_3 = recipients[
            9
        ].copy()
        recipient_dup_3.email_from += '; "TestMulti" <test.multi@test.example.com>'
        recipient_dup_4 = recipient_dup_2.copy()

        recipient_void_1 = self.env["mailing.test.optout"].create(
            {"name": "TestRecord_void_1"}
        )
        recipient_falsy_1 = self.env["mailing.test.optout"].create(
            {"name": "TestRecord_falsy_1", "email_from": "falsymail"}
        )
        recipients_all = (
            recipients
            + recipient_dup_1
            + recipient_dup_2
            + recipient_dup_3
            + recipient_dup_4
            + recipient_void_1
            + recipient_falsy_1
        )

        mailing.write({"mailing_domain": [("id", "in", recipients_all.ids)]})
        mailing.action_put_in_queue()
        with self.mock_mail_gateway(mail_unlink_sent=False):
            mailing.action_send_mail()

        for recipient in recipients_all:
            with self.subTest(recipient_from=recipient.email_from):
                recipient_info = {
                    "content": f"Hello {recipient.name}",
                    "email": recipient.email_normalized or "",
                    "email_to_mail": recipient.email_from or "",
                    "email_to_recipients": [[recipient.email_from]],
                    "mail_values": {
                        "subject": f"Subject {recipient.name}",
                    },
                }
                if recipient == recipient_dup_2:
                    recipient_info["email_to_mail"] = (
                        '"Format Me" <test.record.09@test.example.com>,"TestDupe" <test.record.08@test.example.com>'
                    )
                if recipient == recipient_dup_3:
                    recipient_info["email_to_mail"] = (
                        '"Format Me" <test.record.09@test.example.com>,"TestMulti" <test.multi@test.example.com>'
                    )
                    recipient_info["email_to_recipients"] = [
                        [
                            '"Format Me" <test.record.09@test.example.com>',
                            '"TestMulti" <test.multi@test.example.com>',
                        ]
                    ]
                if recipient == recipient_dup_4:
                    recipient_info["email_to_mail"] = (
                        '"Format Me" <test.record.09@test.example.com>,"TestDupe" <test.record.08@test.example.com>'
                    )

                if recipient in recipients[1] | recipients[2]:
                    recipient_info["trace_status"] = "cancel"
                    recipient_info["failure_type"] = "mail_optout"
                elif recipient in recipients[3] | recipients[4]:
                    recipient_info["trace_status"] = "cancel"
                    recipient_info["failure_type"] = "mail_bl"
                elif recipient in (recipient_dup_1, recipient_dup_2, recipient_dup_4):
                    recipient_info["trace_status"] = "cancel"
                    recipient_info["failure_type"] = "mail_dup"
                elif recipient == recipient_void_1:
                    recipient_info["trace_status"] = "cancel"
                    recipient_info["failure_type"] = "mail_email_missing"
                elif recipient == recipient_falsy_1:
                    recipient_info["trace_status"] = "cancel"
                    recipient_info["failure_type"] = "mail_email_invalid"
                    recipient_info["email"] = (
                        recipient.email_from
                    )
                else:
                    email = self._find_sent_email(
                        self.user_marketing.email_formatted,
                        recipient_info["email_to_recipients"][0],
                    )
                    self.assertIn("Hi %s :)" % recipient.name, email["body"])
                    self.assertIn(
                        "%s/mailing/%s/confirm_unsubscribe"
                        % (mailing.get_base_url(), mailing.id),
                        email["body"],
                    )
                    unsubscribe_href = self._get_href_from_anchor_id(
                        email["body"], "url6"
                    )
                    unsubscribe_url = urlsplit(unsubscribe_href)
                    unsubscribe_params = dict(parse_qsl(unsubscribe_url.query))
                    self.assertEqual(
                        int(unsubscribe_params["document_id"]), recipient.id
                    )
                    self.assertEqual(
                        unsubscribe_params["email"], recipient.email_normalized
                    )
                    self.assertEqual(
                        mailing._generate_mailing_recipient_token(
                            unsubscribe_params["document_id"],
                            (unsubscribe_params["email"]),
                        ),
                        unsubscribe_params["hash_token"],
                    )
                    self.assertIn(
                        "%s/mailing/%s/view" % (mailing.get_base_url(), mailing.id),
                        email["body"],
                    )
                    view_href = self._get_href_from_anchor_id(email["body"], "url6")
                    view_url = urlsplit(view_href)
                    view_params = dict(parse_qsl(view_url.query))
                    self.assertEqual(int(view_params["document_id"]), recipient.id)
                    self.assertEqual(view_params["email"], recipient.email_normalized)
                    self.assertEqual(
                        mailing._generate_mailing_recipient_token(
                            view_params["document_id"], (view_params["email"])
                        ),
                        view_params["hash_token"],
                    )

            self.assertMailTraces(
                [recipient_info],
                mailing,
                recipient,
                mail_links_info=[
                    [
                        (
                            "url0",
                            "https://www.odoo.tz/my/%s" % recipient.name,
                            True,
                            {},
                        ),
                        ("url1", "https://www.odoo.be", True, {}),
                        ("url2", "https://www.odoo.com", True, {}),
                        ("url3", "https://www.odoo.eu", True, {}),
                        (
                            "url4",
                            "https://www.example.com/foo/bar?baz=qux",
                            True,
                            {"baz": "qux"},
                        ),
                        (
                            "url5",
                            "%s/event/dummy-event-0" % mailing.get_base_url(),
                            True,
                            {},
                        ),
                        ("url6", "%s/view" % mailing.get_base_url(), False, {}),
                        ("url7", "mailto:test@odoo.com", False, {}),
                        (
                            "url8",
                            "%s/unsubscribe_from_list" % mailing.get_base_url(),
                            False,
                            {},
                        ),
                    ]
                ],
                check_mail=True,
            )

        self.assertMailingStatistics(
            mailing, expected=16, delivered=7, sent=7, canceled=9, failed=0
        )
