import logging
import re
import smtplib
from datetime import UTC as datetime_UTC
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from email import message_from_string
from functools import partial
from pathlib import Path
from socket import gaierror
from unittest.mock import PropertyMock, call, patch

import psycopg
from freezegun import freeze_time
from markupsafe import Markup
from OpenSSL.SSL import Error as SSLError

import odoo.modules.module
from odoo import SUPERUSER_ID, Command, api, fields
from odoo.exceptions import AccessError, LockError
from odoo.libs.datetime import timezone
from odoo.tests import tagged, users
from odoo.tools import file_path, formataddr, mute_logger

from odoo.addons.mail.models import mail_mail as mail_mail_module
from odoo.addons.mail.models.ir_mail_server import (
    MailDeliveryError,
    OutgoingEmailError,
    SMTPSessionLost,
)
from odoo.addons.mail.tests.common import MailCommon
from odoo.addons.mail.tools.failure_type import (
    DELIVERY_FAILURE_TYPES,
    OUTGOING_FAILURE_TYPES,
)


def _personalize(mail, body, partner=False, doc_to_followers=None):
    return mail._apply_unfollow_block(
        body, mail._resolve_unfollow_block(body), partner, doc_to_followers
    )


@tagged("mail_mail")
class TestMailMail(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.test_record = (
            cls.env["mail.test.gateway"]
            .with_context(cls._test_context)
            .create(
                {
                    "name": "Test",
                    "email_from": "ignasse@example.com",
                }
            )
            .with_context({})
        )

        cls.test_message = cls.test_record.message_post(
            body=Markup("<p>Message</p>"), subject="Subject"
        )
        cls.test_mail = cls.env["mail.mail"].create(
            [
                {
                    "body": Markup("<p>Body</p>"),
                    "email_from": False,
                    "email_to": "test@example.com",
                    "is_notification": True,
                    "subject": "Subject",
                }
            ]
        )
        cls.test_notification = cls.env[
            "mail.notification"
        ].create(
            {
                "is_read": False,
                "mail_mail_id": cls.test_mail.id,
                "mail_message_id": cls.test_message.id,
                "notification_type": "email",
                "res_partner_id": cls.partner_employee.id,
            }
        )

        cls.emails_falsy = [False, "", " "]
        cls.emails_invalid = ["buggy", "buggy, wrong"]
        cls.emails_invalid_ascii = ["raoul@example¢¡.com"]
        cls.emails_valid = ["raoul¢¡@example.com", "raoul@example.com"]

    def _reset_data(self, track_email=None):
        self._init_mail_mock()
        self.test_mail.write(
            {"failure_reason": False, "failure_type": False, "state": "outgoing"}
        )
        values = {
            "failure_reason": False,
            "failure_type": False,
            "notification_status": "ready",
        }
        if track_email is not None:
            values |= {
                "mail_email_address": track_email or False,
                "res_partner_id": False,
            }
        self.test_notification.write(values)

    @users("admin")
    def test_mail_mail_attachment_access(self):
        mail = self.env["mail.mail"].create(
            {
                "body_html": "Test",
                "email_to": "test@example.com",
                "partner_ids": [(4, self.user_employee.partner_id.id)],
                "attachment_ids": [
                    (0, 0, {"name": "file 1", "datas": "c2VjcmV0"}),
                    (0, 0, {"name": "file 2", "datas": "c2VjcmV0"}),
                    (0, 0, {"name": "file 3", "datas": "c2VjcmV0"}),
                    (0, 0, {"name": "file 4", "datas": "c2VjcmV0"}),
                ],
            }
        )

        def _patched_check_access(self, *args, **kwargs):
            if self.env.su:
                return None
            inaccessible = self.filtered(lambda att: att.name in ("file 2", "file 4"))
            if inaccessible:
                return inaccessible, lambda: AccessError(self.env._("No access"))
            return None

        mail.invalidate_recordset()

        new_attachment = self.env["ir.attachment"].create(
            {
                "name": "new file",
                "datas": "c2VjcmV0",
            }
        )

        with patch.object(
            self.env.registry["ir.attachment"], "_check_access", _patched_check_access
        ):
            self.assertEqual(mail.restricted_attachment_count, 2)
            self.assertEqual(len(mail.unrestricted_attachment_ids), 2)
            self.assertEqual(
                mail.unrestricted_attachment_ids.mapped("name"), ["file 3", "file 1"]
            )

            mail.write(
                {
                    "unrestricted_attachment_ids": [Command.link(new_attachment.id)],
                }
            )
            self.assertEqual(mail.restricted_attachment_count, 2)
            self.assertEqual(len(mail.unrestricted_attachment_ids), 3)
            self.assertEqual(
                mail.unrestricted_attachment_ids.mapped("name"),
                ["new file", "file 3", "file 1"],
            )
            self.assertEqual(len(mail.attachment_ids), 5)

            mail.write(
                {
                    "unrestricted_attachment_ids": [Command.unlink(new_attachment.id)],
                }
            )
            self.assertEqual(mail.restricted_attachment_count, 2)
            self.assertEqual(len(mail.unrestricted_attachment_ids), 2)
            self.assertEqual(
                mail.unrestricted_attachment_ids.mapped("name"), ["file 3", "file 1"]
            )
            self.assertEqual(len(mail.attachment_ids), 4)

            mail.invalidate_recordset()
            mail.write({"unrestricted_attachment_ids": [Command.clear()]})
            self.assertEqual(len(mail.unrestricted_attachment_ids), 0)
            self.assertEqual(len(mail.attachment_ids), 2)

            mail.invalidate_recordset()
            self.assertEqual(mail.sudo().restricted_attachment_count, 2)
            self.assertEqual(len(mail.sudo().unrestricted_attachment_ids), 0)

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_headers(self):
        base_values = {
            "body_html": "<p>Test</p>",
            "email_to": "test@example.com",
            "headers": {"foo": "bar"},
        }

        for headers, expected in [
            ({"foo": "bar"}, {"foo": "bar"}),
            ({"foo": "bar", "baz": "3+2"}, {"foo": "bar", "baz": "3+2"}),
            ("{'foo': 'bar'}", {}),
            (["not_a_dict"], {}),
            ("alsonotadict", {}),
            (False, {}),
        ]:
            with self.subTest(headers=headers, expected=expected):
                mail = self.env["mail.mail"].create(
                    [dict(base_values, headers=headers)]
                )
                with self.mock_mail_gateway():
                    mail.send()
                for key, value in expected.items():
                    self.assertIn(key, self._mails[0]["headers"])
                    self.assertEqual(self._mails[0]["headers"][key], value)
                if not expected:
                    self.assertNotIn("foo", self._mails[0]["headers"])

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_recipients(self):
        mail = (
            self.env["mail.mail"]
            .sudo()
            .create(
                {
                    "body_html": "<p>Test</p>",
                    "email_to": "test@example.com",
                    "partner_ids": [(4, self.user_employee.partner_id.id)],
                }
            )
        )
        with self.mock_mail_gateway():
            mail.send()
        self.assertSentEmail(mail.env.user.partner_id, ["test@example.com"])
        self.assertEqual(len(self._mails), 1)

        mail = (
            self.env["mail.mail"]
            .sudo()
            .create(
                {
                    "body_html": "<p>Test</p>",
                    "email_to": "test@example.com",
                    "recipient_ids": [(4, self.user_employee.partner_id.id)],
                }
            )
        )
        with self.mock_mail_gateway():
            mail.send()
        self.assertSentEmail(mail.env.user.partner_id, ["test@example.com"])
        self.assertSentEmail(
            mail.env.user.partner_id, [self.user_employee.email_formatted]
        )
        self.assertEqual(len(self._mails), 2)

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_recipients_cc(self):
        mail = (
            self.env["mail.mail"]
            .sudo()
            .create(
                {
                    "body_html": "<p>Test</p>",
                    "email_cc": 'test.cc.1@example.com, "Herbert" <test.cc.2@example.com>',
                    "email_to": 'test.rec.1@example.com, "Raoul" <test.rec.2@example.com>',
                    "recipient_ids": [(4, self.user_employee.partner_id.id)],
                }
            )
        )

        with self.mock_mail_gateway():
            mail.send()
        self.assertSentEmail(
            mail.env.user.partner_id,
            ["test.rec.1@example.com", '"Raoul" <test.rec.2@example.com>'],
            email_cc=["test.cc.1@example.com", '"Herbert" <test.cc.2@example.com>'],
        )
        self.assertSentEmail(
            mail.env.user.partner_id, [self.user_employee.email_formatted], email_cc=[]
        )
        self.assertEqual(len(self._mails), 2)

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_recipients_formatting(self):
        mail = (
            self.env["mail.mail"]
            .sudo()
            .create(
                {
                    "author_id": False,
                    "body_html": "<p>Test</p>",
                    "email_cc": 'test.cc.1@example.com, "Herbert" <test.cc.2@example.com>',
                    "email_from": '"Ignasse" <test.from@example.com>',
                    "email_to": 'test.rec.1@example.com, "Raoul" <test.rec.2@example.com>',
                }
            )
        )

        with self.mock_mail_gateway():
            mail.send()
        self.assertSentEmail(
            '"Ignasse" <test.from@example.com>',
            ["test.rec.1@example.com", '"Raoul" <test.rec.2@example.com>'],
            email_cc=['"Herbert" <test.cc.2@example.com>', "test.cc.1@example.com"],
        )
        self.assertEqual(len(self._mails), 1)

    def test_mail_mail_recipients_add_msg_to(self):
        self.maxDiff = None
        test_partners = self.env["res.partner"].create(
            [
                {
                    "name": name,
                    "email": email,
                }
                for name, email in [
                    ("Partner1", "partner.test@test.example.com"),
                    ("Partner2", "<partner.test.2@test.example.com>"),
                ]
            ]
        )
        for mail_values, exp_smtp, exp_to, exp_cc in [
            (
                {
                    "email_to": '"Customer" <customer@test.example.com>, user2@test.mycompany.com',
                    "recipient_ids": [(4, p.id) for p in test_partners],
                    "headers": {
                        "X-Msg-To-Add": 'add.1@test.example.com, "Add 2" <add.2@test.example.com>',
                    },
                },
                [
                    ["customer@test.example.com", "user2@test.mycompany.com"],
                    ["partner.test@test.example.com"],
                    ["partner.test.2@test.example.com"],
                ],
                [
                    [
                        '"Customer" <customer@test.example.com>',
                        "user2@test.mycompany.com",
                        "add.1@test.example.com",
                        '"Add 2" <add.2@test.example.com>',
                    ],
                    [
                        '"Partner1" <partner.test@test.example.com>',
                        "add.1@test.example.com",
                        '"Add 2" <add.2@test.example.com>',
                    ],
                    [
                        '"Partner2" <partner.test.2@test.example.com>',
                        "add.1@test.example.com",
                        '"Add 2" <add.2@test.example.com>',
                    ],
                ],
                [[], [], []],
            ),
            (
                {
                    "email_cc": '"Cc Customer" <customer.cc@test.example.com>, customer.cc.2@test.example.com',
                    "recipient_ids": [(4, p.id) for p in test_partners],
                    "headers": {
                        "X-Msg-To-Add": 'add.1@test.example.com, "Add 2" <add.2@test.example.com>',
                    },
                },
                [
                    ["customer.cc@test.example.com", "customer.cc.2@test.example.com"],
                    ["partner.test@test.example.com"],
                    ["partner.test.2@test.example.com"],
                ],
                [
                    ["add.1@test.example.com", '"Add 2" <add.2@test.example.com>'],
                    [
                        '"Partner1" <partner.test@test.example.com>',
                        "add.1@test.example.com",
                        '"Add 2" <add.2@test.example.com>',
                    ],
                    [
                        '"Partner2" <partner.test.2@test.example.com>',
                        "add.1@test.example.com",
                        '"Add 2" <add.2@test.example.com>',
                    ],
                ],
                [
                    [
                        '"Cc Customer" <customer.cc@test.example.com>',
                        "customer.cc.2@test.example.com",
                    ],
                    [],
                    [],
                ],
            ),
            (
                {
                    "email_cc": '"Cc Customer" <customer.cc@test.example.com>',
                    "email_to": '"Customer" <customer@test.example.com>',
                    "recipient_ids": [(4, p.id) for p in test_partners],
                    "headers": {
                        "X-Msg-To-Add": 'add.1@test.example.com, "Add 2" <add.2@test.example.com>, customer@test.example.com, ,wrong',
                    },
                },
                [
                    [
                        "customer@test.example.com",
                        "customer.cc@test.example.com",
                    ],
                    ["partner.test@test.example.com"],
                    ["partner.test.2@test.example.com"],
                ],
                [
                    [
                        '"Customer" <customer@test.example.com>',
                        "add.1@test.example.com",
                        '"Add 2" <add.2@test.example.com>',
                    ],
                    [
                        '"Partner1" <partner.test@test.example.com>',
                        "add.1@test.example.com",
                        '"Add 2" <add.2@test.example.com>',
                        "customer@test.example.com",
                    ],
                    [
                        '"Partner2" <partner.test.2@test.example.com>',
                        "add.1@test.example.com",
                        '"Add 2" <add.2@test.example.com>',
                        "customer@test.example.com",
                    ],
                ],
                [['"Cc Customer" <customer.cc@test.example.com>'], [], []],
            ),
        ]:
            with self.subTest(mail_values=mail_values):
                with self.mock_mail_gateway():
                    self.env["mail.mail"].create(
                        {
                            "subject": "Test Recipients",
                            **mail_values,
                        }
                    ).send()
                for exp_smtp_to_lst, exp_msg_to_lst, exp_msg_cc_lst in zip(
                    exp_smtp, exp_to, exp_cc, strict=True
                ):
                    self.assertSMTPEmailsSent(
                        msg_from=f"{self.user_root.name} <{self.default_from}@{self.alias_domain}>",
                        smtp_from=f"{self.default_from}@{self.alias_domain}",
                        smtp_to_list=exp_smtp_to_lst,
                        msg_cc_lst=exp_msg_cc_lst,
                        msg_to_lst=exp_msg_to_lst,
                    )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_return_path(self):
        base_values = {
            "body_html": "<p>Test</p>",
            "email_to": "test@example.com",
        }

        mail = self.env["mail.mail"].create(base_values)
        with self.mock_mail_gateway():
            mail.send()
        self.assertEqual(
            self._mails[0]["headers"]["Return-Path"],
            "%s@%s" % (self.alias_bounce, self.alias_domain),
        )

        mail = self.env["mail.mail"].create(
            dict(
                base_values,
                model=self.test_record._name,
                res_id=self.test_record.id,
            )
        )
        with self.mock_mail_gateway():
            mail.send()
        self.assertEqual(
            self._mails[0]["headers"]["Return-Path"],
            "%s@%s" % (self.alias_bounce, self.alias_domain),
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_send_nothing_left_to_deliver(self):
        message = self.test_record.message_post(
            body=Markup("<p>Body</p>"), subject="Subject"
        )
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.user@test.example.com",
                "is_notification": True,
                "mail_message_id": message.id,
                "recipient_ids": [Command.link(self.partner_employee.id)],
            }
        )
        notification = self.env["mail.notification"].create(
            {
                "mail_mail_id": mail.id,
                "mail_message_id": message.id,
                "notification_status": "sent",
                "notification_type": "email",
                "res_partner_id": self.partner_employee.id,
            }
        )

        with self.mock_mail_gateway():
            mail.send()

        self.assertEqual(len(self._mails), 0, "Nothing is delivered a second time")
        self.assertEqual(mail.state, "sent")
        self.assertFalse(mail.failure_type)
        self.assertFalse(mail.failure_reason)
        self.assertEqual(notification.notification_status, "sent")

        void = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.user@test.example.com",
            }
        )
        with self.mock_mail_gateway():
            void.send()
        self.assertEqual(void.state, "exception")
        self.assertEqual(void.failure_type, "mail_email_missing")

        never_sent = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.user@test.example.com",
                "is_notification": True,
                "mail_message_id": message.id,
                "recipient_ids": [Command.link(self.partner_employee.id)],
            }
        )
        with (
            self.mock_mail_gateway(),
            patch.object(
                type(self.env["mail.mail"]),
                "_prepare_outgoing_list",
                lambda self, **kwargs: [],
            ),
        ):
            never_sent.send()
        self.assertEqual(never_sent.state, "exception")
        self.assertNotEqual(
            never_sent.state,
            "sent",
            "nothing was handed to SMTP, so nothing may be recorded as sent",
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_send_prefetch_window_follows_commits(self):
        mails = self.env["mail.mail"].create(
            [
                {
                    "auto_delete": False,
                    "body_html": "<p>Test %s</p>" % idx,
                    "email_from": "test.user@test.example.com",
                    "email_to": "test.%s@example.com" % idx,
                }
                for idx in range(5)
            ]
        )

        MailMail = type(self.env["mail.mail"])
        original_send_one = MailMail._send_one

        def _record_window(records, batch, raise_exception=False):
            windows.append(len(records._prefetch_ids))
            return original_send_one(records, batch, raise_exception=raise_exception)

        windows = []
        with (
            self.mock_mail_gateway(),
            patch.object(MailMail, "_send_one", _record_window),
            patch.object(self.env.cr, "commit", self.env.invalidate_all),
        ):
            mails.send(auto_commit=True)
        self.assertEqual(
            windows,
            [1] * 5,
            "Committing after each mail throws the cache away, so anything the "
            "window prefetches beyond the mail being sent is fetched and dropped.",
        )

        mails.write({"state": "outgoing"})
        windows = []
        with (
            self.mock_mail_gateway(),
            patch.object(MailMail, "_send_one", _record_window),
        ):
            mails.send()
        self.assertEqual(
            windows,
            [5, 4, 3, 2, 1],
            "Without commits the cache survives the loop, so the window spans the "
            "mails still to come -- and only those: the tail must not prefetch the "
            "auto_delete rows _postprocess_sent_message has already unlinked.",
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_send_auto_delete_logs_without_reading_the_deleted_mail(self):
        mails = self.env["mail.mail"].create(
            [
                {
                    "auto_delete": True,
                    "body_html": "<p>Bye %s</p>" % idx,
                    "email_from": "test.user@test.example.com",
                    "email_to": "test.%s@example.com" % idx,
                }
                for idx in range(3)
            ]
        )
        mail_ids = mails.ids
        logger = "odoo.addons.mail.models.mail_mail"
        with (
            self.mock_mail_gateway(mail_unlink_sent=True),
            patch.object(self.env.cr, "commit", self.env.invalidate_all),
            self.assertLogs(logger, level="INFO") as captured,
        ):
            mails.send(auto_commit=True)

        self.assertFalse(self.env["mail.mail"].sudo().browse(mail_ids).exists())
        sent_lines = [
            r for r in captured.records if "successfully sent" in r.getMessage()
        ]
        self.assertEqual(len(sent_lines), 3, "one success line per mail")
        self.assertFalse(
            [r for r in captured.records if r.levelno >= logging.ERROR],
            "the success line must not fail on the mail it has just deleted",
        )

    def test_mail_mail_schedule(self):
        now = datetime(2022, 6, 28, 14, 0, 0)
        scheduled_datetimes = [
            False,
            "",
            "This is not a date format",
            now,
            now.replace(tzinfo=timezone("Australia/Brisbane")),
            fields.Datetime.to_string(now - timedelta(days=1)),
            fields.Datetime.to_string(now + timedelta(days=1)),
            (now + timedelta(days=1)).strftime("%H:%M:%S %d-%m-%Y"),
            (now + timedelta(hours=3)).strftime("%H:%M:%S %d-%m-%Y") + " +0400",
            (now + timedelta(hours=-3)).strftime("%H:%M:%S %d-%m-%Y") + " -0400",
        ]
        expected_datetimes = [
            False,
            False,
            False,
            now,
            now - timezone("Australia/Brisbane").utcoffset(now),
            now - timedelta(days=1),
            now + timedelta(days=1),
            now + timedelta(days=1),
            now + timedelta(hours=-1),
            now + timedelta(hours=1),
        ]
        expected_states = [
            "sent",
            "sent",
            "sent",
            "sent",
            "sent",
            "sent",
            "outgoing",
            "outgoing",
            "sent",
            "outgoing",
        ]

        mails = self.env["mail.mail"].create(
            [
                {
                    "body_html": "<p>Test</p>",
                    "email_to": "test@example.com",
                    "scheduled_date": scheduled_datetime,
                }
                for scheduled_datetime in scheduled_datetimes
            ]
        )

        for mail, expected_datetime, scheduled_datetime in zip(
            mails, expected_datetimes, scheduled_datetimes, strict=True
        ):
            self.assertEqual(
                mail.scheduled_date,
                expected_datetime,
                "Scheduled date: %s should be stored as %s, received %s"
                % (scheduled_datetime, expected_datetime, mail.scheduled_date),
            )
            self.assertEqual(mail.state, "outgoing")

        with freeze_time(now), self.mock_mail_gateway():
            self.env["mail.mail"].process_email_queue()
            for mail, expected_state in zip(mails, expected_states, strict=True):
                self.assertEqual(mail.state, expected_state)

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_send_configuration(self):
        self.env["mail.mail"].search([]).unlink()

        for queue_batch_size, exp_send_count in [
            (3, 3),
            (0, 10),
            (False, 10),
        ]:
            with (
                self.subTest(queue_batch_size=queue_batch_size),
                self.mock_mail_gateway(),
            ):
                self.env["ir.config_parameter"].sudo().set_param(
                    "mail.mail.queue.batch.size", queue_batch_size
                )
                mails = self.env["mail.mail"].create(
                    [
                        {
                            "auto_delete": False,
                            "body_html": f"Batch Email {idx}",
                            "email_from": "test.from@mycompany.example.com",
                            "email_to": "test.outgoing@test.example.com",
                            "state": "outgoing",
                        }
                        for idx in range(10)
                    ]
                )

                self.env["mail.mail"].process_email_queue()
                self.assertEqual(len(self._mails), exp_send_count)
                mails.write({"state": "sent"})

        self.env["ir.config_parameter"].sudo().set_param(
            "mail.mail.queue.batch.size", False
        )
        for session_batch_size, exp_call_count in [
            (3, 4),
            (0, 1),
            (False, 1),
        ]:
            with (
                self.subTest(session_batch_size=session_batch_size),
                self.mock_mail_gateway(),
            ):
                self.env["ir.config_parameter"].sudo().set_param(
                    "mail.session.batch.size", session_batch_size
                )
                mails = self.env["mail.mail"].create(
                    [
                        {
                            "auto_delete": False,
                            "body_html": f"Batch Email {idx}",
                            "email_from": "test.from@mycompany.example.com",
                            "email_to": "test.outgoing@test.example.com",
                            "state": "outgoing",
                        }
                        for idx in range(10)
                    ]
                )

                self.env["mail.mail"].process_email_queue()
                self.assertEqual(
                    self.mail_mail_private_send_mocked.call_count, exp_call_count
                )
                mails.write({"state": "sent"})

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_send_exceptions_origin(self):
        mail, notification = self.test_mail, self.test_notification

        for default_from in [False, ""]:
            self.mail_alias_domain.default_from = default_from
            self._reset_data()
            with (
                self.mock_mail_gateway(),
                mute_logger("odoo.addons.mail.models.mail_mail"),
            ):
                mail.send(raise_exception=False)
            self.assertEqual(len(self._mails), 0)
            self.assertEqual(
                mail.failure_reason,
                "You must either provide a sender address explicitly or configure using the combination of `mail.catchall.domain` and `mail.default.from` ICPs, in the server configuration file or with the --email-from startup parameter.",
            )
            self.assertEqual(mail.failure_type, "mail_from_missing")
            self.assertEqual(mail.state, "exception")
            self.assertEqual(
                notification.failure_reason,
                "You must either provide a sender address explicitly or configure using the combination of `mail.catchall.domain` and `mail.default.from` ICPs, in the server configuration file or with the --email-from startup parameter.",
            )
            self.assertEqual(notification.failure_type, "mail_from_missing")
            self.assertEqual(notification.notification_status, "exception")

        self.mail_alias_domain.bounce_alias = False
        self.env.company.invalidate_recordset(
            fnames={"bounce_email", "bounce_formatted"}
        )
        for email_from in ["strange@example¢¡.com", "robert"]:
            self._reset_data()
            mail.write({"email_from": email_from})
            with self.mock_mail_gateway():
                mail.send(raise_exception=False)
            self.assertEqual(self._mails[0]["email_from"], email_from)
            self.assertEqual(
                mail.failure_reason,
                f"Malformed 'Return-Path' or 'From' address: {email_from} - It should contain one valid plain ASCII email",
            )
            self.assertEqual(mail.failure_type, "mail_from_invalid")
            self.assertEqual(mail.state, "exception")
            self.assertEqual(
                notification.failure_reason,
                f"Malformed 'Return-Path' or 'From' address: {email_from} - It should contain one valid plain ASCII email",
            )
            self.assertEqual(notification.failure_type, "mail_from_invalid")
            self.assertEqual(notification.notification_status, "exception")

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_send_exceptions_recipients_emails(self):
        mail, notification = self.test_mail, self.test_notification

        for email_to in self.emails_falsy:
            with self.subTest(email_to=email_to):
                self._reset_data(track_email=email_to)
                mail.write({"email_to": email_to})
                with self.mock_mail_gateway():
                    mail.send(raise_exception=False)
                self.assertEqual(
                    mail.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(
                    mail.failure_type, "mail_email_missing", "Mail: missing email_to"
                )
                self.assertEqual(mail.state, "exception")
                self.assertEqual(
                    notification.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(notification.failure_type, "mail_email_missing")
                self.assertEqual(notification.notification_status, "exception")

        for email_to, failure_type in zip(
            self.emails_invalid,
            ["mail_email_missing", "mail_email_missing"],
            strict=True,
        ):
            with self.subTest(email_to=email_to):
                self._reset_data(track_email=email_to)
                mail.write({"email_to": email_to})
                with self.mock_mail_gateway():
                    mail.send(raise_exception=False)
                self.assertEqual(
                    mail.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(mail.failure_type, failure_type)
                self.assertEqual(mail.state, "exception")
                self.assertEqual(
                    notification.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(
                    notification.failure_type,
                    failure_type,
                    "Mail: invalid email_to: missing instead of invalid",
                )
                self.assertEqual(notification.notification_status, "exception")

        for email_to in self.emails_invalid_ascii:
            with self.subTest(email_to=email_to):
                self._reset_data(track_email=email_to)
                mail.write({"email_to": email_to})
                with self.mock_mail_gateway():
                    mail.send(raise_exception=False)
                self.assertEqual(
                    mail.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(
                    mail.failure_type,
                    "mail_email_invalid",
                    "Mail: invalid (ascii) recipient",
                )
                self.assertEqual(mail.state, "exception")
                self.assertEqual(
                    notification.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(notification.failure_type, "mail_email_invalid")
                self.assertEqual(notification.notification_status, "exception")

        for email_to in self.emails_valid:
            with self.subTest(email_to=email_to):
                self._reset_data(track_email=email_to)
                mail.write({"email_to": email_to})
                with self.mock_mail_gateway():
                    mail.send(raise_exception=False)
                self.assertFalse(mail.failure_reason)
                self.assertFalse(mail.failure_type)
                self.assertEqual(mail.state, "sent")
                self.assertFalse(notification.failure_reason)
                self.assertFalse(notification.failure_type)
                self.assertEqual(notification.notification_status, "sent")

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_send_exceptions_recipients_partners(self):
        mail, notification = self.test_mail, self.test_notification

        mail.write({"email_from": "test.user@test.example.com", "email_to": False})
        partners_falsy = self.env["res.partner"].create(
            [{"name": "Name %s" % email, "email": email} for email in self.emails_falsy]
        )
        partners_invalid = self.env["res.partner"].create(
            [
                {"name": "Name %s" % email, "email": email}
                for email in self.emails_invalid
            ]
        )
        partners_invalid_ascii = self.env["res.partner"].create(
            [
                {"name": "Name %s" % email, "email": email}
                for email in self.emails_invalid_ascii
            ]
        )
        partners_valid = self.env["res.partner"].create(
            [{"name": "Name %s" % email, "email": email} for email in self.emails_valid]
        )

        for partner in partners_falsy:
            with self.subTest(partner_email=partner.email):
                self._reset_data()
                mail.write({"recipient_ids": [(5, 0), (4, partner.id)]})
                notification.write({"res_partner_id": partner.id})
                with self.mock_mail_gateway():
                    mail.send(raise_exception=False)
                self.assertEqual(
                    mail.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(
                    mail.failure_type,
                    "mail_email_missing",
                    "Mail: void recipient partner: missing, not invalid",
                )
                self.assertEqual(mail.state, "exception")
                self.assertEqual(
                    notification.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(
                    notification.failure_type,
                    "mail_email_missing",
                    "Mail: void recipient partner: missing, not invalid",
                )
                self.assertEqual(notification.notification_status, "exception")

        for partner in partners_invalid:
            with self.subTest(partner_email=partner.email):
                self._reset_data()
                mail.write({"recipient_ids": [(5, 0), (4, partner.id)]})
                notification.write({"res_partner_id": partner.id})
                with self.mock_mail_gateway():
                    mail.send(raise_exception=False)
                self.assertEqual(
                    mail.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(mail.failure_type, "mail_email_invalid")
                self.assertEqual(mail.state, "exception")
                self.assertEqual(
                    notification.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(notification.failure_type, "mail_email_invalid")
                self.assertEqual(notification.notification_status, "exception")

        for partner in partners_invalid_ascii:
            with self.subTest(partner_email=partner.email):
                self._reset_data()
                mail.write({"recipient_ids": [(5, 0), (4, partner.id)]})
                notification.write({"res_partner_id": partner.id})
                with self.mock_mail_gateway():
                    mail.send(raise_exception=False)
                self.assertEqual(
                    mail.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(mail.failure_type, "mail_email_invalid")
                self.assertEqual(mail.state, "exception")
                self.assertEqual(
                    notification.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(notification.failure_type, "mail_email_invalid")
                self.assertEqual(notification.notification_status, "exception")

        for partner in partners_valid:
            with self.subTest(partner_email=partner.email):
                self._reset_data()
                mail.write({"recipient_ids": [(5, 0), (4, partner.id)]})
                notification.write({"res_partner_id": partner.id})
                with self.mock_mail_gateway():
                    mail.send(raise_exception=False)
                self.assertFalse(mail.failure_reason)
                self.assertFalse(mail.failure_type)
                self.assertEqual(mail.state, "sent")
                self.assertFalse(notification.failure_reason)
                self.assertFalse(notification.failure_type)
                self.assertEqual(notification.notification_status, "sent")

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_send_exceptions_recipients_partners_mixed(self):
        mail, notification = self.test_mail, self.test_notification

        mail.write({"email_to": "test@example.com"})
        partners_falsy = self.env["res.partner"].create(
            [{"name": "Name %s" % email, "email": email} for email in self.emails_falsy]
        )
        partners_invalid = self.env["res.partner"].create(
            [
                {"name": "Name %s" % email, "email": email}
                for email in self.emails_invalid
            ]
        )
        partners_valid = self.env["res.partner"].create(
            [{"name": "Name %s" % email, "email": email} for email in self.emails_valid]
        )

        for partner in partners_falsy + partners_invalid:
            self._reset_data()
            mail.write({"recipient_ids": [(5, 0), (4, partner.id)]})
            notification.write({"res_partner_id": partner.id})
            with self.mock_mail_gateway():
                mail.send(raise_exception=False)
            self.assertFalse(
                mail.failure_reason,
                "Mail: at least one valid recipient, mail is sent to avoid send loops and spam",
            )
            self.assertFalse(
                mail.failure_type,
                "Mail: at least one valid recipient, mail is sent to avoid send loops and spam",
            )
            self.assertEqual(
                mail.state,
                "sent",
                "Mail: at least one valid recipient, mail is sent to avoid send loops and spam",
            )
            self.assertEqual(
                notification.failure_reason,
                self.env["ir.mail_server"]._get_outgoing_email_message(
                    self.env["ir.mail_server"].NO_VALID_RECIPIENT
                ),
            )
            self.assertEqual(
                notification.failure_type,
                "mail_email_missing"
                if partner in partners_falsy
                else "mail_email_invalid",
                "Mail: a partner with no address is missing, one with an unparseable address is invalid",
            )
            self.assertEqual(notification.notification_status, "exception")

        mail.write(
            {
                "recipient_ids": [
                    (5, 0),
                    (4, partners_valid[1].id),
                    (4, partners_falsy[0].id),
                ]
            }
        )
        notification.write({"res_partner_id": partners_valid[1].id})
        notification2 = notification.create(
            {
                "is_read": False,
                "mail_mail_id": mail.id,
                "mail_message_id": self.test_message.id,
                "notification_type": "email",
                "res_partner_id": partners_falsy[0].id,
            }
        )

        for email_to in self.emails_falsy + self.emails_invalid:
            with self.subTest(email_to=email_to):
                self._reset_data()
                notification2.write(
                    {
                        "failure_reason": False,
                        "failure_type": False,
                        "notification_status": "ready",
                    }
                )
                mail.write({"email_to": email_to})
                with self.mock_mail_gateway():
                    mail.send(raise_exception=False)
                self.assertFalse(
                    mail.failure_reason,
                    "Mail: at least one valid recipient, mail is sent to avoid send loops and spam",
                )
                self.assertFalse(
                    mail.failure_type,
                    "Mail: at least one valid recipient, mail is sent to avoid send loops and spam",
                )
                self.assertEqual(
                    mail.state,
                    "sent",
                    "Mail: at least one valid recipient, mail is sent to avoid send loops and spam",
                )
                self.assertFalse(notification.failure_reason)
                self.assertFalse(notification.failure_type)
                self.assertEqual(notification.notification_status, "sent")
                self.assertEqual(
                    notification2.failure_reason,
                    self.env["ir.mail_server"]._get_outgoing_email_message(
                        self.env["ir.mail_server"].NO_VALID_RECIPIENT
                    ),
                )
                self.assertEqual(
                    notification2.failure_type,
                    "mail_email_missing",
                    "Mail: partners_falsy[0] carries no address at all",
                )
                self.assertEqual(notification2.notification_status, "exception")

        for email_to in self.emails_invalid_ascii:
            with self.subTest(email_to=email_to):
                self._reset_data()
                notification2.write(
                    {
                        "failure_reason": False,
                        "failure_type": False,
                        "notification_status": "ready",
                    }
                )
                mail.write({"email_to": email_to})
                with self.mock_mail_gateway():
                    mail.send(raise_exception=False)

                self.assertFalse(
                    mail.failure_type,
                    "Mail: at least one valid recipient, mail is sent to avoid send loops and spam",
                )
                self.assertEqual(mail.state, "sent")
                self.assertFalse(notification.failure_type)
                self.assertEqual(notification.notification_status, "sent")
                self.assertEqual(notification2.failure_type, "mail_email_invalid")
                self.assertEqual(notification2.notification_status, "exception")

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_send_exceptions_raise_management(self):
        mail, notification = self.test_mail, self.test_notification
        mail.write(
            {"email_from": "test.user@test.example.com", "email_to": "test@example.com"}
        )

        with self.mock_mail_gateway():
            _connect_current = self.connect_mocked.side_effect

            for error, msg in [
                (
                    smtplib.SMTPServerDisconnected("SMTPServerDisconnected"),
                    "SMTPServerDisconnected",
                ),
                (
                    smtplib.SMTPResponseException("code", "SMTPResponseException"),
                    "code\nSMTPResponseException",
                ),
                (
                    smtplib.SMTPNotSupportedError("SMTPNotSupportedError"),
                    "SMTPNotSupportedError",
                ),
                (smtplib.SMTPException("SMTPException"), "SMTPException"),
                (SSLError("SSLError"), "SSLError"),
                (gaierror("gaierror"), "gaierror"),
                (TimeoutError("timeout"), "timeout"),
            ]:
                self.connect_mocked.side_effect = error

                mail.send(raise_exception=False)
                self.assertEqual(mail.failure_reason, msg)
                self.assertEqual(
                    mail.failure_type,
                    "mail_smtp",
                    "The mail records the same failure type it reports to its "
                    "notifications. It used to record none, so the Technical menu "
                    "showed an exception with an empty Failure type column in the one "
                    "class of failure where the type is most diagnostic.",
                )
                self.assertEqual(mail.state, "exception")
                self.assertEqual(
                    notification.failure_reason,
                    msg,
                    "The notification carries the same reason as the mail, as it does "
                    "for every other class of failure below. It used to carry none on "
                    "this path alone, so a connection failure -- where the reason is "
                    "what names the cause -- was the one exception whose Failure Reason "
                    "column was blank in Discuss and in the resend wizard.",
                )
                self.assertEqual(notification.failure_type, "mail_smtp")
                self.assertEqual(notification.notification_status, "exception")
                self._reset_data()

        self.connect_mocked.side_effect = _connect_current

        with self.mock_mail_gateway():
            _send_current = self.send_email_mocked.side_effect
            self.addCleanup(
                setattr, self.send_email_mocked, "side_effect", _send_current
            )

            self._reset_data()
            mail.write({"email_to": "test@example.com"})

            self.send_email_mocked.side_effect = MemoryError("Some exception")
            with self.assertRaises(MemoryError):
                mail.send(raise_exception=False)
            self.assertFalse(mail.failure_reason, "MemoryError raises and rolls back")
            self.assertFalse(mail.failure_type, "MemoryError raises and rolls back")
            self.assertEqual(
                mail.state, "outgoing", "MemoryError raises and rolls back"
            )
            self.assertEqual(notification.notification_status, "ready")

            for error, state, failure_type in [
                (
                    smtplib.SMTPServerDisconnected("Some exception"),
                    "exception",
                    "mail_smtp",
                ),
                (
                    SMTPSessionLost("Some exception", payload_submitted=True),
                    "exception",
                    "mail_smtp",
                ),
                (
                    SMTPSessionLost("Some exception", payload_submitted=False),
                    "outgoing",
                    False,
                ),
            ]:
                self._reset_data()
                self.send_email_mocked.side_effect = error
                with mute_logger("odoo.addons.mail.models.mail_mail"):
                    self.assertFalse(mail.send(raise_exception=False))
                self.assertEqual(mail.state, state, error)
                self.assertEqual(mail.failure_type, failure_type)
                self.assertEqual(notification.failure_type, failure_type)
                self.assertEqual(
                    notification.notification_status,
                    "exception" if failure_type else "ready",
                )

            for error, msg, failure_type in [
                (MailDeliveryError("Some exception"), "Some exception", "unknown"),
                (
                    MailDeliveryError("OutboundSpamException"),
                    "OutboundSpamException",
                    "mail_spam",
                ),
                (ValueError("Unexpected issue"), "Unexpected issue", "unknown"),
            ]:
                self.send_email_mocked.side_effect = error

                self._reset_data()
                mail.send(raise_exception=False)
                self.assertEqual(mail.failure_reason, msg)
                self.assertEqual(mail.failure_type, failure_type)
                self.assertEqual(mail.state, "exception")
                self.assertEqual(notification.failure_reason, msg)
                self.assertEqual(notification.failure_type, failure_type)
                self.assertEqual(notification.notification_status, "exception")

    def test_mail_mail_values_misc(self):
        msg = self.env["mail.mail"].create({})
        self.assertEqual(
            msg.message_type,
            "email_outgoing",
            "Mails should have outgoing email type by default",
        )


@tagged("mail_mail", "mail_server")
class TestMailMailServer(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.mail_server_domain_2 = cls.env["ir.mail_server"].create(
            {
                "from_filter": "test_2.com",
                "name": "Server 2",
                "smtp_host": "test_2.com",
            }
        )
        cls.test_record = (
            cls.env["mail.test.gateway"]
            .with_context(cls._test_context)
            .create(
                {
                    "name": "Test",
                    "email_from": "ignasse@example.com",
                }
            )
            .with_context({})
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_send_server(self):
        self.assertEqual(
            self.env["ir.mail_server"]._get_default_from_address(),
            f"{self.default_from}@{self.alias_domain}",
        )

        mail_values = {
            "body_html": "<p>Test</p>",
            "email_to": "user@example.com",
        }

        mails = self.env["mail.mail"].create(
            [
                {
                    **mail_values,
                    "email_from": "test@unknown_domain.com",
                }
                for _ in range(5)
            ]
        ) | self.env["mail.mail"].create(
            [
                {
                    **mail_values,
                    "email_from": "test_2@unknown_domain.com",
                }
                for _ in range(5)
            ]
        )

        mails += self.env["mail.mail"].create(
            [
                {
                    **mail_values,
                    "email_from": "user_1@test_2.com",
                }
                for _ in range(5)
            ]
        ) + self.env["mail.mail"].create(
            [
                {
                    **mail_values,
                    "email_from": "user_2@test_2.com",
                }
                for _ in range(5)
            ]
        )

        mails += self.env["mail.mail"].create(
            [
                {
                    **mail_values,
                    "email_from": "user_1@test_2.com",
                    "mail_server_id": self.mail_server_domain.id,
                }
                for _ in range(5)
            ]
        )

        with self.mock_smtplib_connection():
            mails.send()

        self.assertEqual(
            self.find_mail_server_mocked.call_count,
            4,
            'Must be called only once per "mail from" when the mail server is not forced',
        )
        self.assertEqual(len(self.emails), 25)

        self.assertEqual(
            self.connect_mocked.call_count,
            4,
            "Must be called once per batch which share the same mail server and the same smtp from",
        )
        self.connect_mocked.assert_has_calls(
            calls=[
                call(
                    smtp_from=f"{self.default_from}@{self.alias_domain}",
                    mail_server_id=self.mail_server_notification.id,
                    resolve_server=False,
                ),
                call(
                    smtp_from="user_1@test_2.com",
                    mail_server_id=self.mail_server_domain_2.id,
                    resolve_server=False,
                ),
                call(
                    smtp_from="user_2@test_2.com",
                    mail_server_id=self.mail_server_domain_2.id,
                    resolve_server=False,
                ),
                call(
                    smtp_from="user_1@test_2.com",
                    mail_server_id=self.mail_server_domain.id,
                    resolve_server=False,
                ),
            ],
            any_order=True,
        )

        self.assertSMTPEmailsSent(
            message_from=f'"test" <{self.default_from}@{self.alias_domain}>',
            emails_count=5,
            from_filter=self.mail_server_notification.from_filter,
        )
        self.assertSMTPEmailsSent(
            message_from=f'"test_2" <{self.default_from}@{self.alias_domain}>',
            emails_count=5,
            from_filter=self.mail_server_notification.from_filter,
        )
        self.assertSMTPEmailsSent(
            message_from="user_1@test_2.com",
            emails_count=5,
            mail_server=self.mail_server_domain_2,
        )
        self.assertSMTPEmailsSent(
            message_from="user_2@test_2.com",
            emails_count=5,
            mail_server=self.mail_server_domain_2,
        )
        self.assertSMTPEmailsSent(
            message_from="user_1@test_2.com",
            emails_count=5,
            mail_server=self.mail_server_domain,
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_values_email_formatted(self):
        customer = self.env["res.partner"].create(
            {
                "name": "Tony Customer",
                "email": '"Formatted Emails" <tony.customer@test.example.com>',
            }
        )
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Test</p>",
                "email_cc": '"Ignasse, le Poilu" <test.cc.1@test.example.com>',
                "email_to": '"Raoul, le Grand" <test.email.1@test.example.com>, "Micheline, l\'immense" <test.email.2@test.example.com>',
                "recipient_ids": [
                    (4, self.user_employee.partner_id.id),
                    (4, customer.id),
                ],
            }
        )
        with self.mock_mail_gateway():
            mail.send()
        self.assertEqual(
            len(self._mails), 3, "Mail: sent 3 emails: 1 for email_to, 1 / recipient"
        )
        self.assertEqual(
            sorted(sorted(_mail["email_to"]) for _mail in self._mails),
            sorted(
                [
                    sorted(
                        [
                            '"Raoul, le Grand" <test.email.1@test.example.com>',
                            '"Micheline, l\'immense" <test.email.2@test.example.com>',
                        ]
                    ),
                    [
                        formataddr(
                            (
                                self.user_employee.name,
                                self.user_employee.email_normalized,
                            )
                        )
                    ],
                    [formataddr(("Tony Customer", "tony.customer@test.example.com"))],
                ]
            ),
            "Mail: formatting issues should have been removed as much as possible",
        )
        self.assertEqual(
            [_mail["email_cc"] for _mail in self._mails],
            [['"Ignasse, le Poilu" <test.cc.1@test.example.com>'], [], []],
            "Mail: currently always removing formatting in email_cc",
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_values_email_multi(self):
        customer = self.env["res.partner"].create(
            {
                "name": "Tony Customer",
                "email": "tony.customer@test.example.com, norbert.customer@test.example.com",
            }
        )
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Test</p>",
                "email_cc": "test.cc.1@test.example.com, test.cc.2@test.example.com",
                "email_to": "test.email.1@test.example.com, test.email.2@test.example.com",
                "recipient_ids": [
                    (4, self.user_employee.partner_id.id),
                    (4, customer.id),
                ],
            }
        )
        with self.mock_mail_gateway():
            mail.send()
        self.assertEqual(
            len(self._mails), 3, "Mail: sent 3 emails: 1 for email_to, 1 / recipient"
        )
        self.assertEqual(
            sorted(sorted(_mail["email_to"]) for _mail in self._mails),
            sorted(
                [
                    sorted(
                        [
                            "test.email.1@test.example.com",
                            "test.email.2@test.example.com",
                        ]
                    ),
                    [
                        formataddr(
                            (
                                self.user_employee.name,
                                self.user_employee.email_normalized,
                            )
                        )
                    ],
                    sorted(
                        [
                            formataddr(
                                ("Tony Customer", "tony.customer@test.example.com")
                            ),
                            formataddr(
                                ("Tony Customer", "norbert.customer@test.example.com")
                            ),
                        ]
                    ),
                ]
            ),
            "Mail: formatting issues should have been removed as much as possible (multi emails in a single address are managed "
            "like separate emails when sending with recipient_ids",
        )
        self.assertEqual(
            [_mail["email_cc"] for _mail in self._mails],
            [["test.cc.1@test.example.com", "test.cc.2@test.example.com"], [], []],
        )

        customer = self.env["res.partner"].create(
            {
                "name": "Tony Customer",
                "email": 'tony.customer@test.example.com, "Norbert Customer" <norbert.customer@test.example.com>',
            }
        )
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Test</p>",
                "email_cc": "test.cc.1@test.example.com, test.cc.2@test.example.com",
                "email_to": "test.email.1@test.example.com, test.email.2@test.example.com",
                "recipient_ids": [
                    (4, self.user_employee.partner_id.id),
                    (4, customer.id),
                ],
            }
        )
        with self.mock_mail_gateway():
            mail.send()
        self.assertEqual(
            len(self._mails), 3, "Mail: sent 3 emails: 1 for email_to, 1 / recipient"
        )
        self.assertEqual(
            sorted(sorted(_mail["email_to"]) for _mail in self._mails),
            sorted(
                [
                    sorted(
                        [
                            "test.email.1@test.example.com",
                            "test.email.2@test.example.com",
                        ]
                    ),
                    [
                        formataddr(
                            (
                                self.user_employee.name,
                                self.user_employee.email_normalized,
                            )
                        )
                    ],
                    sorted(
                        [
                            formataddr(
                                ("Tony Customer", "tony.customer@test.example.com")
                            ),
                            formataddr(
                                ("Tony Customer", "norbert.customer@test.example.com")
                            ),
                        ]
                    ),
                ]
            ),
            "Mail: formatting issues should have been removed as much as possible (multi emails in a single address are managed "
            "like separate emails when sending with recipient_ids (and partner name is always used as name part)",
        )
        self.assertEqual(
            [_mail["email_cc"] for _mail in self._mails],
            [["test.cc.1@test.example.com", "test.cc.2@test.example.com"], [], []],
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_values_email_unicode(self):
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Test</p>",
                "email_cc": "test.😊.cc@example.com",
                "email_to": "test.😊@example.com",
            }
        )
        with self.mock_mail_gateway():
            mail.send()
        self.assertEqual(len(self._mails), 1)
        self.assertEqual(self._mails[0]["email_cc"], ["test.😊.cc@example.com"])
        self.assertEqual(self._mails[0]["email_to"], ["test.😊@example.com"])

    @users("admin")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_mail_values_email_uppercase(self):
        customer = self.env["res.partner"].create(
            {
                "name": "Uppercase Partner",
                "email": "Uppercase.Partner.youpie@example.gov.uni",
            }
        )
        for recipient_values, exp_recipients in zip(
            [
                {"email_to": "Uppercase.Customer.to@example.gov.uni"},
                {
                    "email_to": '"Formatted Customer" <Uppercase.Customer.to@example.gov.uni>',
                    "email_cc": '"UpCc" <Uppercase.Customer.cc@example.gov.uni>',
                },
                {
                    "recipient_ids": [(4, customer.id)],
                    "email_cc": '"UpCc" <Uppercase.Customer.cc@example.gov.uni>',
                },
            ],
            [
                [(["uppercase.customer.to@example.gov.uni"], [])],
                [
                    (
                        [
                            '"Formatted Customer" <uppercase.customer.to@example.gov.uni>'
                        ],
                        ['"UpCc" <uppercase.customer.cc@example.gov.uni>'],
                    )
                ],
                [
                    (
                        [
                            '"Uppercase Partner" <uppercase.partner.youpie@example.gov.uni>'
                        ],
                        [],
                    ),
                    ([], ['"UpCc" <uppercase.customer.cc@example.gov.uni>']),
                ],
            ],
            strict=True,
        ):
            with self.subTest(values=recipient_values):
                mail = self.env["mail.mail"].create(
                    {
                        "body_html": "<p>Test</p>",
                        "email_from": '"Forced From" <Forced.From@test.example.com>',
                        **recipient_values,
                    }
                )
                with self.mock_mail_gateway():
                    mail.send()
                for exp_to, exp_cc in exp_recipients:
                    self.assertSentEmail(
                        '"Forced From" <forced.from@test.example.com>',
                        exp_to,
                        email_cc=exp_cc,
                    )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    @patch(
        "odoo.addons.base.models.ir_attachment.IrAttachment.file_size",
        new_callable=PropertyMock,
    )
    def test_mail_mail_send_server_attachment_to_download_link(
        self, mock_attachment_file_size
    ):

        def count_attachments(message):
            if isinstance(message, str):
                return 0
            elif message.is_multipart():
                return sum(count_attachments(part) for part in message.get_payload())
            elif "attachment" in message.get("Content-Disposition", ""):
                return 1
            return 0

        mock_attachment_file_size.return_value = 1024 * 128
        test_mail_server = self.mail_server_domain_2
        max_size_always_exceed = 0.1
        max_size_never_exceed = 10

        for n_attachment, mail_server, business_attachment, expected_is_links in (
            (1, self.env["ir.mail_server"], True, False),
            (3, self.env["ir.mail_server"], True, True),
            (1, self.env["ir.mail_server"], True, True),
            (1, test_mail_server, True, False),
            (3, test_mail_server, True, True),
            (1, test_mail_server, True, True),
            (3, self.env["ir.mail_server"], False, False),
            (1, test_mail_server, False, False),
        ):
            if expected_is_links:
                max_size_test_succeed = max_size_always_exceed * n_attachment
                max_size_test_fail = max_size_never_exceed
            else:
                max_size_test_succeed = max_size_never_exceed
                max_size_test_fail = max_size_always_exceed * n_attachment
            if mail_server:
                self.env["ir.config_parameter"].sudo().set_param(
                    "base.default_max_email_size", max_size_test_fail
                )
                mail_server.max_email_size = max_size_test_succeed
            else:
                self.env["ir.config_parameter"].sudo().set_param(
                    "base.default_max_email_size", max_size_test_succeed
                )

            attachments = (
                self.env["ir.attachment"]
                .sudo()
                .create(
                    [
                        {
                            "name": f"attachment{idx_attachment}",
                            "res_name": "test",
                            "res_model": self.test_record._name
                            if business_attachment
                            else "mail.message",
                            "res_id": self.test_record.id if business_attachment else 0,
                            "datas": "IA==",
                        }
                        for idx_attachment in range(n_attachment)
                    ]
                )
            )
            with self.mock_smtplib_connection():
                mails = self.env["mail.mail"].create(
                    [
                        {
                            "attachment_ids": attachments.ids,
                            "body_html": "<p>Test</p>",
                            "email_from": "test@test_2.com",
                            "email_to": f"mail_{mail_idx}@test.com",
                        }
                        for mail_idx in range(2)
                    ]
                )
                mails._send(mail_server=mail_server)

            self.assertEqual(len(self.emails), 2)
            for outgoing_email in self.emails:
                message_raw = outgoing_email["message"]
                message_parsed = message_from_string(message_raw)
                message_cleaned = re.sub(r"[\s=]", "", message_raw)
                with self.subTest(
                    n_attachment=n_attachment,
                    mail_server=mail_server,
                    business_attachment=business_attachment,
                    expected_is_links=expected_is_links,
                ):
                    if expected_is_links:
                        self.assertEqual(
                            count_attachments(message_parsed),
                            0,
                            "Attachments should have been removed (replaced by download links)",
                        )
                        self.assertTrue(
                            all(attachment.access_token for attachment in attachments),
                            "Original attachment should have been modified (access_token added)",
                        )
                        self.assertTrue(
                            all(
                                attachment.access_token in message_cleaned
                                for attachment in attachments
                            ),
                            "All attachments should have been turned into download links",
                        )
                    else:
                        self.assertEqual(
                            count_attachments(message_parsed),
                            n_attachment,
                            "All attachments should be present",
                        )
                        self.assertEqual(
                            message_cleaned.count("access_token"),
                            0,
                            "Attachments should not have been turned into download links",
                        )
                        self.assertTrue(
                            all(
                                not attachment.access_token
                                for attachment in attachments
                            ),
                            "Original attachment should not have been modified (access_token not added)",
                        )


@tagged("mail_mail")
class TestMailMailRace(MailCommon):
    registry_test_mode = False

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mail_bounce_during_send(self):
        cr = self.registry.cursor()
        env = api.Environment(cr, SUPERUSER_ID, {})

        self.partner = env["res.partner"].create(
            {
                "name": "Ernest Partner",
            }
        )
        mail = (
            env["mail.mail"]
            .sudo()
            .create(
                {
                    "body_html": "<p>Test</p>",
                    "is_notification": True,
                    "state": "outgoing",
                    "recipient_ids": [(4, self.partner.id)],
                }
            )
        )
        mail_message = mail.mail_message_id

        message = env["mail.message"].create(
            {
                "subject": "S",
                "body": "B",
                "subtype_id": self.ref("mail.mt_comment"),
                "notification_ids": [
                    (
                        0,
                        0,
                        {
                            "res_partner_id": self.partner.id,
                            "mail_mail_id": mail.id,
                            "notification_type": "email",
                            "is_read": True,
                            "notification_status": "ready",
                        },
                    )
                ],
            }
        )
        notif = env["mail.notification"].search(
            [("res_partner_id", "=", self.partner.id)]
        )
        notif.check_singleton()
        cr.commit()

        this = self
        bounce_deferred = []

        @api.model
        def send_email(self, message, *args, **kwargs):
            with this.registry.cursor() as cr, mute_logger("odoo.db"):
                try:
                    notif.with_env(notif.env(cr=cr)).lock_for_update()
                except LockError:
                    bounce_deferred.append(True)
                else:
                    cr.execute(
                        "UPDATE mail_notification SET notification_status='bounce' WHERE id = %s",
                        [notif.id],
                    )
            return message["Message-Id"]

        with self.mock_mail_gateway():
            self.patch(self.registry["ir.mail_server"], "send_email", send_email)
            mail.send()

        self.assertTrue(bounce_deferred, "The bounce should have been deferred")
        self.assertEqual(notif.notification_status, "sent")


        notif.unlink()
        mail.unlink()
        (mail_message | message).unlink()
        self.partner.unlink()
        cr.commit()
        cr.close()


@tagged("mail_mail")
class TestMailMailQueueResilience(MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["mail.mail"].search([]).unlink()

    def _create_outgoing(self, count):
        return self.env["mail.mail"].create(
            [
                {
                    "auto_delete": False,
                    "body_html": f"<p>Queue {idx}</p>",
                    "email_from": "test.from@mycompany.example.com",
                    "email_to": f"queue.{idx}@test.example.com",
                    "state": "outgoing",
                }
                for idx in range(count)
            ]
        )

    @mute_logger("odoo.addons.mail.models.mail_mail", "odoo.db.cursor")
    def test_queue_batch_size_negative(self):
        self._create_outgoing(3)
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.mail.queue.batch.size", -5
        )
        with self.mock_mail_gateway():
            self.env["mail.mail"].process_email_queue()
        self.assertEqual(
            len(self._mails), 3, "A bad batch size is not a reason to stop sending"
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_session_batch_size_negative(self):
        self._create_outgoing(3)
        self.env["ir.config_parameter"].sudo().set_param("mail.session.batch.size", -3)
        with self.mock_mail_gateway():
            self.env["mail.mail"].process_email_queue()
        self.assertEqual(
            len(self._mails), 3, "A bad session size is not a reason to stop sending"
        )

    def test_personal_limit_negative(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.server.personal.limit.minutes", -10
        )
        self.assertGreater(
            self.env["ir.mail_server"]._get_personal_mail_servers_limit(),
            0,
            "A per-minute quota below one delays every mail forever",
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.server.personal.setup.grace.minutes", -10
        )
        self.assertGreater(
            self.env["ir.mail_server"]._get_personal_mail_server_grace(), 0
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_unauthorized_server_does_not_poison_the_queue(self):
        owner = self.env["res.users"].create(
            {
                "login": "server.owner",
                "name": "Server Owner",
                "email": "test.from@mycompany.example.com",
            }
        )
        server = self.env["ir.mail_server"].create(
            {
                "from_filter": "test.from@mycompany.example.com",
                "name": "Shared server",
                "smtp_host": "smtp.example.com",
                "smtp_port": 25,
            }
        )
        poisoned = self.env["mail.mail"].create(
            {
                "auto_delete": False,
                "body_html": "<p>Poison</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "poison@test.example.com",
                "mail_server_id": server.id,
                "state": "outgoing",
            }
        )
        healthy = self._create_outgoing(1)
        server.owner_user_id = owner.id
        self.assertEqual(owner.outgoing_mail_server_id, server)

        with self.mock_mail_gateway():
            self.env["mail.mail"].process_email_queue()

        self.assertEqual(healthy.state, "sent", "An unrelated mail must still go out")
        self.assertEqual(
            poisoned.state,
            "exception",
            "The mail that may not use its server is the one that fails",
        )
        self.assertEqual(
            poisoned.failure_type,
            "mail_server_unauthorized",
            poisoned.failure_reason,
        )


@tagged("mail_mail")
class TestMailMailOutcomeReporting(MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_record = (
            cls.env["mail.test.gateway"]
            .with_context(cls._test_context)
            .create({"name": "Reporting", "email_from": "ignasse@example.com"})
            .with_context({})
        )

    def _failed_notification_mail(self):
        message = self.test_record.message_post(
            body=Markup("<p>Body</p>"), subject="Subject"
        )
        mail = self.env["mail.mail"].create(
            {
                "auto_delete": False,
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "failure_reason": "previous run",
                "failure_type": "mail_smtp",
                "is_notification": True,
                "mail_message_id": message.id,
                "recipient_ids": [Command.link(self.partner_employee.id)],
                "state": "exception",
            }
        )
        notification = self.env["mail.notification"].create(
            {
                "failure_reason": "previous run",
                "failure_type": "mail_smtp",
                "mail_mail_id": mail.id,
                "mail_message_id": message.id,
                "notification_status": "exception",
                "notification_type": "email",
                "res_partner_id": self.partner_employee.id,
            }
        )
        return mail, notification

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_recovered_notification_updates_the_thread(self):
        mail, notification = self._failed_notification_mail()
        with patch.object(
            type(self.env["mail.message"]),
            "_notify_message_notification_update",
            autospec=True,
        ) as notify_mocked:
            mail.action_retry()
            self.assertEqual(
                notification.notification_status,
                "ready",
                "Retrying puts the notification back in the queue",
            )
            with self.mock_mail_gateway():
                mail.send()
        self.assertEqual(notification.notification_status, "sent")
        self.assertFalse(notification.failure_type)
        self.assertTrue(
            notify_mocked.called,
            "The chatter is told when a notification starts failing; it must be "
            "told when it stops",
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_cancelled_notification_updates_the_thread(self):
        mail, notification = self._failed_notification_mail()
        with patch.object(
            type(self.env["mail.message"]),
            "_notify_message_notification_update",
            autospec=True,
        ) as notify_mocked:
            mail.cancel()
        self.assertEqual(notification.notification_status, "canceled")
        self.assertTrue(notify_mocked.called)

    def test_retry_clears_the_previous_failure(self):
        mail, notification = self._failed_notification_mail()
        mail.action_retry()
        self.assertEqual(mail.state, "outgoing")
        self.assertFalse(mail.failure_type, "An outgoing mail has no failure")
        self.assertFalse(mail.failure_reason)
        self.assertFalse(notification.failure_type)
        self.assertFalse(notification.failure_reason)


@tagged("mail_mail", "mail_server")
class TestMailMailPersonalServerQuota(MailCommon):

    def test_personal_server_cost_counts_the_raw_address_message(self):
        partners = self.env["res.partner"].create(
            [
                {"name": f"Recipient {idx}", "email": f"recipient.{idx}@example.com"}
                for idx in range(3)
            ]
        )
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "raw@test.example.com",
                "recipient_ids": [Command.set(partners.ids)],
            }
        )
        self.assertEqual(
            len(mail._prepare_outgoing_list()),
            4,
            "one message for the raw addresses, one per partner",
        )
        self.assertEqual(
            mail._personal_server_cost(),
            4,
            "the quota charges what the mail actually sends",
        )

        cc_only = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_cc": "cc@test.example.com",
                "email_from": "test.from@mycompany.example.com",
                "recipient_ids": [Command.set(partners.ids)],
            }
        )
        self.assertEqual(len(cc_only._prepare_outgoing_list()), 4)
        self.assertEqual(cc_only._personal_server_cost(), 4)

        partners_only = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "recipient_ids": [Command.set(partners.ids)],
            }
        )
        self.assertEqual(len(partners_only._prepare_outgoing_list()), 3)
        self.assertEqual(partners_only._personal_server_cost(), 3)


@tagged("mail_mail")
class TestMailMailRecipientDeduplication(MailCommon):

    def test_a_raw_address_a_partner_also_holds_is_sent_once(self):
        partner = self.env["res.partner"].create(
            {"name": "Twice", "email": '"Twice" <twice@test.example.com>'}
        )
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": '"Twice" <TWICE@test.example.com>, other@test.example.com',
                "email_cc": "twice@test.example.com",
                "recipient_ids": [Command.set(partner.ids)],
            }
        )
        with self.assertLogs("odoo.addons.mail.models.mail_mail", level="INFO") as logs:
            raw_group, partner_group = mail._prepare_recipient_groups()
        self.assertIn("also name a recipient partner", logs.output[0])
        self.assertEqual(raw_group["email_to"], ["other@test.example.com"])
        self.assertEqual(raw_group["email_cc"], [])
        self.assertEqual(raw_group["email_to_normalized"], ["other@test.example.com"])
        self.assertEqual(partner_group["partner"], partner)
        self.assertEqual(
            mail._personal_server_cost(), 2, "the quota charges what is sent"
        )

        mail.write({"email_cc": False, "email_to": "twice@test.example.com"})
        self.assertEqual(len(mail._prepare_recipient_groups()), 1)
        self.assertEqual(mail._personal_server_cost(), 1)
        with self.mock_mail_gateway():
            mail.send()
        self.assertEqual(mail.state, "sent")
        self.assertEqual(len(self._mails), 1)
        self.assertEqual(self._mails[0]["email_to"], [partner.email_formatted])


@tagged("mail_mail")
class TestMailMailSchedule(MailCommon):

    def _scheduled_mail(self):
        return self.env["mail.mail"].create(
            {
                "body_html": "<p>Later</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "later@test.example.com",
                "scheduled_date": "2099-01-01 10:00:00",
            }
        )

    def test_send_leaves_a_future_mail_in_the_queue(self):
        mail = self._scheduled_mail()
        with self.mock_mail_gateway():
            mail.send()
        self.assertEqual(mail.state, "outgoing")
        self.assertFalse(self._mails)
        with freeze_time("2099-01-01 10:00:00"), self.mock_mail_gateway():
            mail.send()
        self.assertEqual(mail.state, "sent")

    def test_send_now_drops_the_schedule(self):
        mail = self._scheduled_mail()
        with self.mock_mail_gateway():
            mail.action_send_and_close()
        self.assertFalse(mail.scheduled_date)
        self.assertEqual(mail.state, "sent")
        self.assertEqual(len(self._mails), 1)


@tagged("mail_mail", "mail_server")
class TestMailMailSendGuarantees(MailCommon):

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_another_users_mail_is_still_refused_on_a_personal_server(self):
        owner = self.env["res.users"].create(
            {
                "email": "guar.owner@test.example.com",
                "login": "guar.owner",
                "name": "Guarantee Owner",
            }
        )
        stranger = self.env["res.users"].create(
            {
                "email": "guar.stranger@test.example.com",
                "login": "guar.stranger",
                "name": "Guarantee Stranger",
            }
        )
        server = self.env["ir.mail_server"].create(
            {
                "from_filter": owner.email,
                "name": "Owned server",
                "owner_user_id": owner.id,
                "smtp_host": "smtp.example.com",
                "smtp_port": 25,
            }
        )
        MailMail = self.env["mail.mail"]
        base_vals = {
            "auto_delete": False,
            "email_from": owner.email,
            "email_to": "dest@test.example.com",
            "mail_server_id": server.id,
            "state": "outgoing",
        }
        owner_mail = (
            MailMail.with_user(owner)
            .sudo()
            .create(dict(base_vals, body_html="<p>mine</p>"))
        )
        server.owner_user_id = False
        stranger_mail = (
            MailMail.with_user(stranger)
            .sudo()
            .create(dict(base_vals, body_html="<p>not mine</p>"))
        )
        server.owner_user_id = owner.id

        with self.mock_mail_gateway():
            (owner_mail | stranger_mail)._send(mail_server=server)

        self.assertEqual(
            stranger_mail.state,
            "exception",
            "another user's mail must never go out over a personal server",
        )
        self.assertEqual(
            owner_mail.state, "sent", "the owner's own mail is not collateral damage"
        )

    def test_disable_personal_mail_servers_survives_the_per_mail_check(self):
        owner = self.env["res.users"].create(
            {
                "email": "guar.owner2@test.example.com",
                "login": "guar.owner2",
                "name": "Guarantee Owner 2",
            }
        )
        server = self.env["ir.mail_server"].create(
            {
                "from_filter": owner.email,
                "name": "Owned server 2",
                "owner_user_id": owner.id,
                "smtp_host": "smtp.example.com",
                "smtp_port": 25,
            }
        )
        mail = (
            self.env["mail.mail"]
            .with_user(owner)
            .sudo()
            .create(
                {
                    "body_html": "<p>mine</p>",
                    "email_from": owner.email,
                    "email_to": "dest@test.example.com",
                }
            )
        )
        self.assertTrue(
            mail._filtered_mail_mail_servers(server), "allowed while enabled"
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.disable_personal_mail_servers", True
        )
        self.assertFalse(
            mail._filtered_mail_mail_servers(server),
            "the kill-switch is still honoured one mail at a time",
        )

    def test_return_path_falls_back_to_the_env_company(self):
        naked = self.env["res.company"].create({"name": "No Alias Domain Co"})
        naked.alias_domain_id = False
        self.assertFalse(naked.bounce_email)
        self.assertTrue(self.env.company.bounce_email)

        mail = self.env["mail.mail"].create(
            {
                "auto_delete": False,
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "customer@test.example.com",
                "record_company_id": naked.id,
            }
        )
        with self.mock_mail_gateway():
            mail.send()
        self.assertEqual(
            self._mails[0]["headers"]["Return-Path"], self.env.company.bounce_email
        )

    def test_negative_personal_limit_would_stall_the_server(self):
        with patch.object(
            type(self.env["ir.mail_server"]),
            "_get_personal_mail_servers_limit",
            lambda self: -10,
        ):
            server = self.env["ir.mail_server"].create(
                {
                    "from_filter": self.user_employee.email,
                    "name": "Negative limit server",
                    "owner_user_id": self.user_employee.id,
                    "smtp_host": "smtp.example.com",
                    "smtp_port": 25,
                }
            )
            mails = self.env["mail.mail"].create(
                [
                    {
                        "body_html": "<p>x</p>",
                        "email_from": self.user_employee.email,
                        "email_to": f"d{idx}@test.example.com",
                        "state": "outgoing",
                    }
                    for idx in range(3)
                ]
            )
            to_send = mails._split_by_delayed_batch(server)
        self.assertFalse(to_send, "a quota below one sends nothing at all")
        self.assertTrue(all(mails.mapped("scheduled_date")), "and delays everything")

    def test_negative_grace_would_delete_archived_servers_at_once(self):
        owner = self.env["res.users"].create(
            {
                "email": "grace.owner@test.example.com",
                "login": "grace.owner",
                "name": "Grace Owner",
            }
        )
        server = self.env["ir.mail_server"].create(
            {
                "active": False,
                "from_filter": owner.email,
                "name": "Archived personal",
                "owner_user_id": owner.id,
                "smtp_host": "smtp.example.com",
                "smtp_port": 25,
            }
        )
        self.env["res.users"]._gc_personal_mail_servers()
        self.assertTrue(server.exists(), "kept while inside the grace window")

        with patch.object(
            type(self.env["ir.mail_server"]),
            "_get_personal_mail_server_grace",
            lambda self: -1440,
        ):
            self.env["res.users"]._gc_personal_mail_servers()
        self.assertFalse(server.exists())

        self.env["ir.config_parameter"].sudo().set_param(
            "mail.server.personal.setup.grace.minutes", -1440
        )
        self.assertEqual(
            self.env["ir.mail_server"]._get_personal_mail_server_grace(),
            1440,
            "and the guard reads it as unset",
        )

    @mute_logger("odoo.models.unlink", "odoo.addons.mail.models.mail_mail")
    def test_messages_per_minute_never_exceed_the_personal_limit(self):
        TEST_LIMIT = 5
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.server.personal.limit.minutes", str(TEST_LIMIT)
        )
        owner = self.user_employee
        self.env["ir.mail_server"].create(
            {
                "from_filter": owner.email,
                "name": "Invariant server",
                "owner_user_id": owner.id,
                "smtp_host": "smtp.example.com",
                "smtp_port": 25,
            }
        )
        partners = self.env["res.partner"].create(
            [
                {"name": f"Inv {idx}", "email": f"inv{idx}@test.example.com"}
                for idx in range(16)
            ]
        )
        with self.mock_datetime_and_now("2025-01-01 20:30:23"):
            self.env["mail.mail"].with_user(owner).sudo().create(
                {
                    "email_cc": "cc.1@test.com",
                    "email_from": owner.email,
                    "email_to": "to.1@test.com",
                    "recipient_ids": [Command.set(partners.ids)],
                    "state": "outgoing",
                }
            )

        sent_per_minute = []
        for minute in range(31, 37):
            with (
                self.mock_smtplib_connection(),
                self.mock_mail_gateway(),
                self.mock_datetime_and_now(f"2025-01-01 20:{minute}:23"),
            ):
                self.env["mail.mail"].process_email_queue()
                sent_per_minute.append(
                    len(
                        [
                            mail
                            for mail in self._mails
                            if mail["email_from"] == owner.email
                        ]
                    )
                )
        self.assertTrue(
            all(count <= TEST_LIMIT for count in sent_per_minute),
            f"a personal server was handed more than {TEST_LIMIT} messages in one "
            f"minute: {sent_per_minute}",
        )
        self.assertEqual(
            sum(sent_per_minute),
            17,
            "and nothing is dropped on the way: 1 raw-address message + 16 partners",
        )

    def test_personal_server_cost_over_charges_an_already_notified_partner(self):
        record = (
            self.env["mail.test.gateway"]
            .with_context(self._test_context)
            .create({"name": "Cost", "email_from": "ignasse@example.com"})
        )
        message = record.message_post(body=Markup("<p>b</p>"))
        partners = self.env["res.partner"].create(
            [
                {"name": f"Cost {idx}", "email": f"cost{idx}@test.example.com"}
                for idx in range(3)
            ]
        )
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>b</p>",
                "email_from": "test.from@mycompany.example.com",
                "is_notification": True,
                "mail_message_id": message.id,
                "recipient_ids": [Command.set(partners.ids)],
            }
        )
        self.env["mail.notification"].create(
            {
                "mail_mail_id": mail.id,
                "mail_message_id": message.id,
                "notification_status": "sent",
                "notification_type": "email",
                "res_partner_id": partners[0].id,
            }
        )
        self.assertEqual(
            len(mail._prepare_outgoing_list()),
            2,
            "the partner already reached is not messaged again",
        )
        self.assertEqual(
            mail._personal_server_cost(), 3, "but the quota still charges for them"
        )


@tagged("mail_mail")
class TestMailMailChatterPush(MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_record = (
            cls.env["mail.test.gateway"]
            .with_context(cls._test_context)
            .create({"name": "Push", "email_from": "ignasse@example.com"})
            .with_context({})
        )

    def _failed_notification_mail(self, partner):
        message = self.test_record.message_post(
            body=Markup("<p>Body</p>"), subject="Subject"
        )
        mail = self.env["mail.mail"].create(
            {
                "auto_delete": False,
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "failure_reason": "previous run",
                "failure_type": "mail_smtp",
                "is_notification": True,
                "mail_message_id": message.id,
                "recipient_ids": [Command.link(partner.id)],
                "state": "exception",
            }
        )
        self.env["mail.notification"].create(
            {
                "failure_reason": "previous run",
                "failure_type": "mail_smtp",
                "mail_mail_id": mail.id,
                "mail_message_id": message.id,
                "notification_status": "exception",
                "notification_type": "email",
                "res_partner_id": partner.id,
            }
        )
        return mail

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_recovery_emits_a_real_bus_message(self):
        mail = self._failed_notification_mail(self.user_employee.partner_id)
        bus_bus = self.env["bus.bus"]
        last_id = bus_bus.search([], order="id desc", limit=1).id or 0

        mail.action_retry()
        with self.mock_mail_gateway():
            mail.send()
        self.env.cr.flush()

        payloads = bus_bus.search([("id", ">", last_id)]).mapped("message")
        self.assertTrue(
            any("mail.message" in (payload or "") for payload in payloads),
            f"a bus message carrying the message state must be emitted: {payloads}",
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_a_first_send_that_works_never_reaches_the_hook(self):
        partners = self.env["res.partner"].create(
            [
                {"name": f"Fresh {idx}", "email": f"fresh{idx}@test.example.com"}
                for idx in range(3)
            ]
        )
        mails = self.env["mail.mail"]
        for idx, partner in enumerate(partners):
            message = self.test_record.message_post(
                body=Markup(f"<p>Body {idx}</p>"), subject="Subject"
            )
            mail = self.env["mail.mail"].create(
                {
                    "auto_delete": False,
                    "body_html": f"<p>Body {idx}</p>",
                    "email_from": "test.from@mycompany.example.com",
                    "is_notification": True,
                    "mail_message_id": message.id,
                    "recipient_ids": [Command.link(partner.id)],
                    "state": "outgoing",
                }
            )
            self.env["mail.notification"].create(
                {
                    "mail_mail_id": mail.id,
                    "mail_message_id": message.id,
                    "notification_status": "ready",
                    "notification_type": "email",
                    "res_partner_id": partner.id,
                }
            )
            mails |= mail

        calls = []
        MailMessage = type(self.env["mail.message"])
        original = MailMessage._notify_message_notification_update

        def counted(records, *args, **kwargs):
            calls.append(len(records))
            return original(records, *args, **kwargs)

        with (
            self.mock_mail_gateway(),
            patch.object(MailMessage, "_notify_message_notification_update", counted),
        ):
            mails.send()

        self.assertEqual(
            calls,
            [],
            "nothing was failing, so the chatter has nothing to hear and the hook "
            "must not be reached at all",
        )


@tagged("mail_mail")
class TestFailureTypeCoherence(MailCommon):

    def _js_handled_codes(self):
        source = Path(
            file_path("mail/static/src/core/common/notification_model.js")
        ).read_text(encoding="utf-8")
        codes = set()
        for getter in ("failureMessage", "autoCanceledFailureType"):
            match = re.search(
                rf"get {getter}\(\)[^{{]*{{(.*?)\n    }}", source, re.DOTALL
            )
            self.assertTrue(match, f"{getter} not found in notification_model.js")
            codes |= set(re.findall(r'case "([a-z_]+)":', match.group(1)))
        return codes

    def test_every_model_carrying_a_failure_uses_the_shared_selection(self):
        shared = dict(DELIVERY_FAILURE_TYPES)
        outgoing = dict(OUTGOING_FAILURE_TYPES)
        self.assertLessEqual(
            shared.items(),
            dict(
                self.env["mail.notification"]._fields["failure_type"].selection
            ).items(),
            "mail.notification tracks a delivery it did not perform",
        )
        self.assertLessEqual(
            outgoing.items(),
            dict(self.env["mail.mail"]._fields["failure_type"].selection).items(),
            "mail.mail performs the send, so it never records a bounce",
        )
        if "mailing.trace" in self.env:
            self.assertLessEqual(
                shared.items(),
                dict(
                    self.env["mailing.trace"]._fields["failure_type"].selection
                ).items(),
            )
        self.assertLess(
            set(outgoing),
            set(shared),
            "the outgoing set is a strict subset -- mail_bounce is the difference",
        )

    def test_the_chatter_can_name_every_failure_the_server_can_store(self):
        handled = self._js_handled_codes()
        codes = set(dict(DELIVERY_FAILURE_TYPES))
        missing = codes - handled - {"unknown"}
        self.assertFalse(
            missing,
            f"notification_model.js cannot name {sorted(missing)}; add a case for "
            "each, or the chatter shows 'Exception' for a failure the server was "
            "specific about",
        )
        stale = handled - codes
        self.assertFalse(
            stale,
            f"notification_model.js names {sorted(stale)}, which no model can "
            "store any more",
        )


@tagged("mail_mail")
class TestMailMailDurableMarker(MailCommon):

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_the_marker_is_committed_before_the_first_message_leaves(self):
        mail = self.env["mail.mail"].create(
            {
                "auto_delete": False,
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "dest@test.example.com",
                "state": "outgoing",
            }
        )
        events = []
        MailMail = type(self.env["mail.mail"])
        original_mark = MailMail._mark_sending

        def traced_mark(records, *args, **kwargs):
            result = original_mark(records, *args, **kwargs)
            events.append(("mark", records.id, records.state))
            return result

        with (
            self.mock_mail_gateway(),
            patch.object(MailMail, "_mark_sending", traced_mark),
            patch.object(
                self.env.cr,
                "commit",
                lambda: (events.append(("commit",)), self.env.invalidate_all())[1],
            ),
        ):
            self.send_email_mocked.side_effect = lambda *a, **kw: (
                events.append(("smtp",)) or "<mocked@example.com>"
            )
            mail.send(auto_commit=True)

        kinds = [event[0] for event in events]
        self.assertEqual(
            kinds[:3],
            ["mark", "commit", "smtp"],
            f"the placeholder must be committed before SMTP is called: {kinds}",
        )
        self.assertEqual(
            events[0][2],
            "exception",
            "and what is committed is the placeholder, not the original state",
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_no_extra_commit_without_auto_commit(self):
        mail = self.env["mail.mail"].create(
            {
                "auto_delete": False,
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "dest@test.example.com",
                "state": "outgoing",
            }
        )
        commits = []
        with (
            self.mock_mail_gateway(),
            patch.object(self.env.cr, "commit", lambda: commits.append(1)),
        ):
            mail.send()
        self.assertEqual(commits, [], "a caller that did not ask for commits gets none")


@tagged("mail_mail")
class TestMailMailUnfollowBlock(MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_record = (
            cls.env["mail.test.gateway"]
            .with_context(cls._test_context)
            .create({"name": "Unfollow", "email_from": "ignasse@example.com"})
            .with_context({})
        )

    def test_a_half_block_is_stripped_rather_than_shipped_untokenised(self):
        mail = self.env["mail.mail"].create(
            {
                "body_html": '<p>x</p><a href="/mail/unfollow">Unfollow</a>',
                "email_from": "test.from@mycompany.example.com",
                "email_to": "dest@test.example.com",
                "model": self.test_record._name,
                "res_id": self.test_record.id,
            }
        )
        self.assertFalse(mail._has_unfollow_block(mail.body_html))
        personalized = _personalize(
            mail, mail.body_html, self.partner_employee, doc_to_followers={}
        )
        self.assertNotIn(
            "/mail/unfollow",
            personalized,
            "an unfollow link that cannot be tokenised must not be sent",
        )

    def test_a_span_without_a_link_is_stripped_too(self):
        body = '<p>x</p><span id="mail_unfollow">Not interested?</span>'
        mail = self.env["mail.mail"].create(
            {
                "body_html": body,
                "email_from": "test.from@mycompany.example.com",
                "email_to": "dest@test.example.com",
            }
        )
        self.assertFalse(mail._has_unfollow_block(body))
        self.assertNotIn("mail_unfollow", _personalize(mail, body, doc_to_followers={}))

    def test_a_whole_block_is_recognised_by_both_readers(self):
        body = (
            '<p>x</p><span id="mail_unfollow">'
            '<a href="/mail/unfollow">Unfollow</a></span>'
        )
        mail = self.env["mail.mail"].create(
            {
                "body_html": body,
                "email_from": "test.from@mycompany.example.com",
                "email_to": "dest@test.example.com",
            }
        )
        self.assertTrue(mail._has_unfollow_block(body))
        batch = mail._prepare_send_batch(False, False, None)
        self.assertEqual(
            list(batch.doc_to_followers),
            [],
            "no model/res_id, so no followers -- but the mail was selected",
        )
        self.assertTrue(
            mail._has_unfollow_block(mail.body_html),
            "the batch pass and personalisation now ask the same question",
        )


@tagged("mail_mail")
class TestMailMailHeaders(MailCommon):

    def test_headers_round_trip_as_a_mapping(self):
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "dest@test.example.com",
                "headers": {"X-Odoo-Test": "value", "Return-Path": "b@e.com"},
            }
        )
        mail.invalidate_recordset(["headers"])
        self.assertEqual(
            mail.headers, {"X-Odoo-Test": "value", "Return-Path": "b@e.com"}
        )
        self.assertEqual(self.env["mail.mail"]._fields["headers"].type, "json")

        with self.mock_mail_gateway():
            mail.send()
        self.assertEqual(self._mails[0]["headers"]["X-Odoo-Test"], "value")
        self.assertEqual(
            self._mails[0]["headers"]["Return-Path"],
            "b@e.com",
            "an explicit Return-Path wins over the alias domain's",
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_a_non_mapping_costs_the_headers_and_says_so(self):
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "dest@test.example.com",
                "headers": ["not", "a", "mapping"],
            }
        )
        with self.mock_mail_gateway():
            mail.send()
        self.assertEqual(mail.state, "sent", "the mail still goes out")
        self.assertNotIn("not", self._mails[0]["headers"])

    def test_the_notify_path_writes_a_mapping(self):
        record = (
            self.env["mail.test.gateway"]
            .with_context(self._test_context)
            .create({"name": "Hdr", "email_from": "ignasse@example.com"})
        )
        customer = self.env["res.partner"].create(
            {"name": "Hdr customer", "email": "hdr.customer@test.example.com"}
        )
        with self.mock_mail_gateway():
            record.message_post(
                body=Markup("<p>hi</p>"),
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                partner_ids=customer.ids,
            )
        mail = self._new_mails
        self.assertTrue(mail)
        self.assertIsInstance(
            mail.headers, dict, "stored as a mapping, not a repr of one"
        )


@tagged("mail_mail")
class TestNumericParameterGuards(MailCommon):

    def _accessors(self):
        icp = self.env["ir.config_parameter"]
        return [
            ("mail.batch_size", self.env["mail.mail"]._get_send_batch_size),
            (
                "mail.server.personal.limit.minutes",
                self.env["ir.mail_server"]._get_personal_mail_servers_limit,
            ),
            (
                "mail.server.personal.setup.grace.minutes",
                self.env["ir.mail_server"]._get_personal_mail_server_grace,
            ),
            (
                "mail.activity.systray.limit",
                partial(
                    icp._get_positive_int_param, "mail.activity.systray.limit", 1000
                ),
            ),
            (
                "mail.scheduled_notification.batch.size",
                partial(
                    icp._get_positive_int_param,
                    "mail.scheduled_notification.batch.size",
                    500,
                ),
            ),
        ]

    @mute_logger("odoo.addons.mail.models.ir_config_parameter")
    def test_every_count_clamps_to_something_usable(self):
        ICP = self.env["ir.config_parameter"].sudo()
        for parameter, read in self._accessors():
            for value in ("-1", "-1000", "0", "not a number", ""):
                with self.subTest(parameter=parameter, value=value):
                    ICP.set_param(parameter, value)
                    self.assertGreater(
                        read(),
                        0,
                        f"{parameter}={value!r} must read as unset, not as a "
                        "count the consumer cannot use",
                    )
            ICP.set_param(parameter, "7")
            self.assertEqual(read(), 7, f"{parameter}: a usable value is honoured")

    @mute_logger(
        "odoo.addons.mail.models.ir_config_parameter",
        "odoo.addons.mail.models.mail_mail",
    )
    def test_the_scheduled_notification_cron_survives_a_bad_batch_size(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.scheduled_notification.batch.size", "-500"
        )
        with self.mock_mail_gateway():
            self.env["mail.message.schedule"]._send_notifications_cron()

    @mute_logger("odoo.addons.mail.models.ir_config_parameter")
    def test_the_activity_systray_survives_a_bad_limit(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.activity.systray.limit", "-1"
        )
        self.env["res.users"].with_user(self.user_employee)._get_systray_activities()


@tagged("mail_mail")
class TestMailMailFailureClassification(MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_invalid = cls.env["res.partner"].create(
            {"name": "Unparseable", "email": "buggy, wrong"}
        )
        cls.partner_valid = cls.env["res.partner"].create(
            {"name": "Deliverable", "email": "deliverable@test.example.com"}
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_a_delivery_failure_is_not_an_address_problem(self):
        mail = self.env["mail.mail"].create(
            {
                "auto_delete": True,
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "recipient_ids": [
                    Command.link(self.partner_invalid.id),
                    Command.link(self.partner_valid.id),
                ],
            }
        )
        deliverable = self.partner_valid.email

        def failing_send(mail_server, message, *args, **kwargs):
            if deliverable in (message["To"] or ""):
                raise MailDeliveryError("Mail Delivery Failed", "greylisted")
            return original_send(mail_server, message, *args, **kwargs)

        original_send = type(self.env["ir.mail_server"]).send_email
        with self.mock_mail_gateway(mail_unlink_sent=True):
            self.send_email_mocked.side_effect = failing_send
            mail.send()

        self.assertTrue(
            mail.exists(),
            "a mail whose delivery genuinely failed is evidence, and auto_delete "
            "must not take it away",
        )
        self.assertEqual(
            mail.failure_type,
            "unknown",
            "the delivery failure is classified as one, not as the address "
            "problem an earlier recipient had",
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_an_address_problem_is_still_an_address_problem(self):
        mail = self.env["mail.mail"].create(
            {
                "auto_delete": True,
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "recipient_ids": [Command.link(self.partner_invalid.id)],
            }
        )
        with self.mock_mail_gateway(mail_unlink_sent=True):
            mail.send()
        self.assertFalse(
            mail.exists(), "an unparseable address will not parse next time either"
        )


@tagged("mail_mail")
class TestMailMailFailureRanking(MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_invalid = cls.env["res.partner"].create(
            {"name": "AAA Unparseable", "email": "buggy, wrong"}
        )
        cls.partner_greylisted = cls.env["res.partner"].create(
            {"name": "ZZZ Greylisted", "email": "greylisted@test.example.com"}
        )

    def _send_mixed(self, deliverable_first):
        mail = self.env["mail.mail"].create(
            {
                "auto_delete": True,
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "recipient_ids": [
                    Command.link(self.partner_invalid.id),
                    Command.link(self.partner_greylisted.id),
                ],
            }
        )
        first = (
            self.partner_greylisted.id if deliverable_first else self.partner_invalid.id
        )
        MailMail = self.registry["mail.mail"]
        prepare_origin = MailMail._prepare_outgoing_list

        def ordered(records, **kwargs):
            emails = prepare_origin(records, **kwargs)
            emails.sort(key=lambda values: values["partner"].id != first)
            return emails

        def send_email(mail_server, message, *args, **kwargs):
            if self.partner_greylisted.email in (message["To"] or ""):
                raise MailDeliveryError("Mail Delivery Failed", "greylisted")
            raise OutgoingEmailError(
                self.env["ir.mail_server"]._get_outgoing_email_message(
                    self.env["ir.mail_server"].NO_VALID_RECIPIENT
                ),
                self.env["ir.mail_server"].NO_VALID_RECIPIENT,
            )

        with self.mock_mail_gateway(mail_unlink_sent=True):
            self.send_email_mocked.side_effect = send_email
            self.patch(MailMail, "_prepare_outgoing_list", ordered)
            mail.send()
        return mail

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_a_delivery_failure_survives_a_later_address_failure(self):
        mail = self._send_mixed(deliverable_first=True)
        self.assertTrue(
            mail.exists(),
            "the mail carries evidence of a delivery failure and auto_delete "
            "must not take it away because another recipient's address was bad",
        )
        self.assertEqual(mail.failure_type, "unknown")

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_an_address_failure_first_reaches_the_same_answer(self):
        mail = self._send_mixed(deliverable_first=False)
        self.assertTrue(mail.exists())
        self.assertEqual(mail.failure_type, "unknown")


@tagged("mail_mail")
class TestMailMailNotificationTruth(MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_record = (
            cls.env["mail.test.gateway"]
            .with_context(cls._test_context)
            .create({"name": "Truth", "email_from": "ignasse@example.com"})
            .with_context({})
        )

    def _message(self):
        return self.test_record.message_post(
            body=Markup("<p>Body</p>"), subject="Subject"
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_a_mail_with_no_addressee_fails_its_notifications(self):
        message = self._message()
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "is_notification": True,
                "mail_message_id": message.id,
            }
        )
        notification = self.env["mail.notification"].create(
            {
                "mail_email_address": "nobody@test.example.com",
                "mail_mail_id": mail.id,
                "mail_message_id": message.id,
                "notification_status": "ready",
                "notification_type": "email",
            }
        )

        with self.mock_mail_gateway():
            mail.send()

        self.assertEqual(len(self._mails), 0, "nothing was handed to SMTP")
        self.assertEqual(mail.state, "exception")
        self.assertEqual(mail.failure_type, "mail_email_missing")
        self.assertEqual(
            notification.notification_status,
            "exception",
            "the notification of a mail that was never sent is not 'sent'",
        )
        self.assertEqual(notification.failure_type, "mail_email_missing")

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_an_address_the_envelope_dropped_is_not_reported_delivered(self):
        message = self._message()
        addresses = ["good@test.example.com", "garbage", "also.good@test.example.com"]
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": ",".join(addresses),
                "is_notification": True,
                "mail_message_id": message.id,
            }
        )
        notifications = self.env["mail.notification"].create(
            [
                {
                    "mail_email_address": address,
                    "mail_mail_id": mail.id,
                    "mail_message_id": message.id,
                    "notification_status": "ready",
                    "notification_type": "email",
                }
                for address in addresses
            ]
        )

        with self.mock_mail_gateway():
            mail.send()

        per_address = {
            notification.mail_email_address: notification
            for notification in notifications
        }
        self.assertEqual(
            per_address["good@test.example.com"].notification_status, "sent"
        )
        self.assertEqual(
            per_address["also.good@test.example.com"].notification_status, "sent"
        )
        self.assertEqual(
            per_address["garbage"].notification_status,
            "exception",
            "an address no message was addressed to was not delivered to",
        )
        self.assertEqual(per_address["garbage"].failure_type, "mail_email_invalid")

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_a_partner_the_mail_does_not_carry_is_not_reported_delivered(self):
        message = self._message()
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "is_notification": True,
                "mail_message_id": message.id,
                "recipient_ids": [Command.link(self.partner_employee.id)],
            }
        )
        carried, adrift = self.env["mail.notification"].create(
            [
                {
                    "mail_mail_id": mail.id,
                    "mail_message_id": message.id,
                    "notification_status": "ready",
                    "notification_type": "email",
                    "res_partner_id": partner.id,
                }
                for partner in (self.partner_employee, self.partner_admin)
            ]
        )

        with self.mock_mail_gateway():
            mail.send()

        self.assertEqual(mail.state, "sent")
        self.assertEqual(carried.notification_status, "sent")
        self.assertEqual(adrift.notification_status, "exception")
        self.assertEqual(adrift.failure_type, "unknown")


@tagged("mail_mail")
class TestMailMailSplitNotifications(MailCommon):

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_the_copy_takes_the_notifications_for_what_it_carries(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.server.personal.limit.minutes", "2"
        )
        owner = self.user_employee
        server = self.env["ir.mail_server"].create(
            {
                "from_filter": owner.email,
                "name": "Split server",
                "owner_user_id": owner.id,
                "smtp_host": "smtp.example.com",
                "smtp_port": 25,
            }
        )
        partners = self.env["res.partner"].create(
            [
                {"email": f"split{idx}@test.example.com", "name": f"Split {idx}"}
                for idx in range(3)
            ]
        )
        message = (
            self.env["mail.message"]
            .with_user(owner)
            .sudo()
            .create(
                {
                    "body": "<p>Body</p>",
                    "mail_server_id": server.id,
                    "message_type": "email_outgoing",
                    "model": "res.partner",
                    "res_id": partners[0].id,
                    "subtype_id": self.env.ref("mail.mt_note").id,
                }
            )
        )
        mail = (
            self.env["mail.mail"]
            .with_user(owner)
            .sudo()
            .create(
                {
                    "body_html": "<p>Body</p>",
                    "email_from": owner.email,
                    "email_to": "raw.one@test.example.com",
                    "is_notification": True,
                    "mail_message_id": message.id,
                    "recipient_ids": [Command.set(partners.ids)],
                    "state": "outgoing",
                }
            )
        )
        raw_notification = self.env["mail.notification"].create(
            {
                "mail_email_address": "raw.one@test.example.com",
                "mail_mail_id": mail.id,
                "mail_message_id": message.id,
                "notification_status": "ready",
                "notification_type": "email",
            }
        )

        with self.mock_mail_gateway():
            self.env["mail.mail"].browse(mail.id)._split_by_delayed_batch(server)

        self.assertNotEqual(
            raw_notification.mail_mail_id,
            mail,
            "the raw address moved to the copy, so the row that tracks it did too",
        )
        self.assertFalse(mail.email_to, "and the original no longer carries it")
        self.assertEqual(
            raw_notification.mail_mail_id.email_to, "raw.one@test.example.com"
        )


@tagged("mail_mail")
class TestMailMailQueueNarrowing(MailCommon):

    def _one_mail(self, state):
        return self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "narrow@test.example.com",
                "state": state,
            }
        )

    def test_a_recordset_with_nothing_outgoing_opens_no_session(self):
        mails = self._one_mail("sent") | self._one_mail("cancel")
        with self.mock_mail_gateway():
            mails.send()
        self.assertEqual(
            self.connect_mocked.call_count,
            0,
            "no mail was going to be sent, so no session was worth opening",
        )
        self.assertEqual(len(self._mails), 0)

    def test_a_personal_server_is_not_charged_for_mails_it_will_not_send(self):
        owner = self.user_employee
        server = self.env["ir.mail_server"].create(
            {
                "from_filter": owner.email,
                "name": "Narrowing server",
                "owner_user_id": owner.id,
                "smtp_host": "smtp.example.com",
                "smtp_port": 25,
            }
        )
        messages = (
            self.env["mail.message"]
            .with_user(owner)
            .sudo()
            .create(
                [
                    {
                        "body": "<p>Body</p>",
                        "mail_server_id": server.id,
                        "message_type": "email_outgoing",
                        "subtype_id": self.env.ref("mail.mt_note").id,
                    }
                    for _ in range(3)
                ]
            )
        )
        mails = (
            self.env["mail.mail"]
            .with_user(owner)
            .sudo()
            .create(
                [
                    {
                        "body_html": "<p>Body</p>",
                        "email_from": owner.email,
                        "email_to": "narrow@test.example.com",
                        "mail_message_id": message.id,
                        "state": state,
                    }
                    for message, state in zip(
                        messages, ("sent", "cancel", "sent"), strict=True
                    )
                ]
            )
        )
        with self.mock_mail_gateway():
            mails.send()
        self.assertEqual(
            server.owner_limit_count,
            0,
            "nothing was sent, so nothing was charged",
        )


@tagged("mail_mail")
class TestMailMailUnfollowScope(MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.doc = cls.env["res.partner"].create(
            {"email": "doc@test.example.com", "name": "Unfollow Doc"}
        )
        cls.body = (
            '<p>See <a href="https://help.example.com/mail/unfollow">the page</a> '
            'and <a href="https://help.example.com/mail/unfollow-policy">the policy</a>.</p>'
            '<span id="mail_unfollow"> | <a href="/mail/unfollow">Unfollow</a></span>'
        )

    def _mail(self, model="res.partner", res_id=None):
        message = self.env["mail.message"].create(
            {
                "body": "<p>Body</p>",
                "message_type": "email_outgoing",
                "model": model,
                "res_id": self.doc.id if res_id is None else res_id,
                "subtype_id": self.env.ref("mail.mt_note").id,
            }
        )
        return self.env["mail.mail"].create(
            {
                "body_html": self.body,
                "email_from": "test.from@mycompany.example.com",
                "is_notification": True,
                "mail_message_id": message.id,
                "recipient_ids": [Command.link(self.partner_employee.id)],
            }
        )

    def test_the_token_never_leaves_the_block(self):
        mail = self._mail()
        followers = {("res.partner", self.doc.id): {self.partner_employee.id}}
        personalized = _personalize(
            mail, mail.body_html, self.partner_employee, doc_to_followers=followers
        )
        self.assertIn(
            'href="https://help.example.com/mail/unfollow">',
            personalized,
            "the author's own link is untouched",
        )
        self.assertIn(
            'href="https://help.example.com/mail/unfollow-policy">', personalized
        )
        self.assertEqual(
            personalized.count("token="), 1, "exactly one link carries the token"
        )
        self.assertIn('id="mail_unfollow"', personalized)
        self.assertIn("/mail/unfollow?model=res.partner", personalized)

    def test_a_link_the_author_wrote_survives_the_strip(self):
        mail = self._mail()
        stripped = _personalize(
            mail, mail.body_html, self.partner_employee, doc_to_followers={}
        )
        self.assertNotIn('id="mail_unfollow"', stripped, "the block is gone")
        self.assertIn('href="https://help.example.com/mail/unfollow">', stripped)
        self.assertIn('href="https://help.example.com/mail/unfollow-policy">', stripped)

    def test_a_nested_span_is_removed_whole(self):
        nested = (
            "<p>Before</p>"
            '<span id="mail_unfollow">Not interested? '
            '<span class="o_x">Unfollow</span> here</span>'
            "<p>After</p>"
        )
        self.assertEqual(
            self.env["mail.mail"]._strip_unfollow_block(nested),
            "<p>Before</p><p>After</p>",
        )

    def test_a_model_outside_the_registry_is_not_a_crash(self):
        mail = self._mail()
        mail.mail_message_id.sudo().write({"model": "no.such.model"})
        personalized = _personalize(
            mail,
            mail.body_html,
            self.partner_employee,
            doc_to_followers={
                ("no.such.model", self.doc.id): {self.partner_employee.id}
            },
        )
        self.assertIn("/mail/unfollow?model=no.such.model", personalized)


@tagged("mail_mail")
class TestMailMailOutcomeWrites(MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_record = (
            cls.env["mail.test.gateway"]
            .with_context(cls._test_context)
            .create({"name": "Outcome", "email_from": "ignasse@example.com"})
            .with_context({})
        )

    def _notification_mail(self):
        message = self.test_record.message_post(
            body=Markup("<p>Body</p>"), subject="Subject"
        )
        return self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "is_notification": True,
                "mail_message_id": message.id,
                "recipient_ids": [Command.link(self.partner_employee.id)],
            }
        )

    def test_an_unchanged_message_id_is_not_written_back(self):
        mail = self._notification_mail()
        message_write_date = mail.mail_message_id.write_date
        with self.mock_mail_gateway():
            mail.send()
        self.assertEqual(mail.state, "sent")
        self.assertEqual(
            mail.mail_message_id.write_date,
            message_write_date,
            "sending a mail is not a modification of its message",
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_a_logging_failure_does_not_unsend_a_sent_mail(self):
        mail = self._notification_mail()

        def boom(records, outcome, email_list):
            raise TypeError("a bug in the log line")

        with self.mock_mail_gateway(), mute_logger("odoo.addons.mail.models.mail_mail"):
            self.patch(self.registry["mail.mail"], "_log_sent", boom)
            mail.send()
        self.assertEqual(len(self._mails), 1, "SMTP accepted the message")
        self.assertEqual(
            mail.state,
            "sent",
            "the mail was delivered; a log line failing afterwards does not make "
            "that untrue, and it must not turn the record into a retryable "
            "failure that a human then sends a second time",
        )
        self.assertFalse(mail.failure_type)

    def test_an_administrator_s_send_records_the_delivery_on_others_notifications(
        self,
    ):
        mail = self._notification_mail()
        Notification = self.env["mail.notification"]
        notification = Notification.search(
            [
                ("mail_message_id", "=", mail.mail_message_id.id),
                ("res_partner_id", "=", self.partner_employee.id),
            ]
        ) or Notification.create(
            {
                "author_id": self.partner_admin.id,
                "mail_message_id": mail.mail_message_id.id,
                "res_partner_id": self.partner_employee.id,
            }
        )
        notification.write(
            {
                "mail_mail_id": mail.id,
                "notification_status": "ready",
                "notification_type": "email",
            }
        )
        admin_mail = mail.with_user(self.user_admin)
        self.assertFalse(admin_mail.env.su)
        with self.assertRaises(AccessError):
            notification.with_user(self.user_admin).notification_status = "sent"
        with self.mock_mail_gateway():
            admin_mail.send()
        self.assertEqual(mail.state, "sent")
        self.assertEqual(notification.notification_status, "sent")


@tagged("mail_mail")
class TestMailMailQueueProgress(MailCommon):

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_progress_is_reported_in_chunks(self):
        partner = self.env["res.partner"].create(
            {"email": "progress@test.example.com", "name": "Progress"}
        )
        self.env["mail.mail"].create(
            [
                {
                    "body_html": "<p>Body</p>",
                    "email_from": "test.from@mycompany.example.com",
                    "recipient_ids": [Command.link(partner.id)],
                    "state": "outgoing",
                }
                for _ in range(5)
            ]
        )
        cron = self.env.ref("mail.ir_cron_mail_scheduler_action")
        progress = self.env["ir.cron.progress"].create(
            {"cron_id": cron.id, "done": 0, "remaining": 0}
        )
        reports = []
        IrCron = self.registry["ir.cron"]
        commit_progress_origin = IrCron._commit_progress

        def counted(records, processed=0, **kwargs):
            reports.append(processed)
            return commit_progress_origin(records, processed, **kwargs)

        self.patch(IrCron, "_commit_progress", counted)
        with self.mock_mail_gateway():
            self.env["mail.mail"].with_context(
                cron_id=cron.id, ir_cron_progress_id=progress.id
            ).process_email_queue()

        self.assertEqual(
            len(reports),
            1,
            f"five mails are one chunk, not five reports: {reports}",
        )
        self.assertEqual(sum(reports), 5, "and every one of them is accounted for")


@tagged("mail_mail")
class TestMailMailSelfClosingUnfollowSpan(MailCommon):

    def test_a_self_closing_span_keeps_the_rest_of_the_body(self):
        body = '<p>Important</p><span id="mail_unfollow"/><p>Content after the span</p>'
        self.assertEqual(
            self.env["mail.mail"]._strip_unfollow_block(body),
            "<p>Important</p><p>Content after the span</p>",
            "the span carries no content, so only the span is removed",
        )

    def test_the_block_of_a_self_closing_span_is_the_span(self):
        body = '<p>A</p><span id="mail_unfollow"/><p>B</p>'
        start, end = self.env["mail.mail"]._resolve_unfollow_span(body)
        self.assertEqual(
            body[start:end],
            '<span id="mail_unfollow"/>',
            "an empty element spans itself and nothing more",
        )

    def test_the_pipeline_that_produces_the_form_round_trips(self):
        from odoo.addons.mail.tools.html_body import (
            parse_body_fragments,
            render_body_fragments,
        )

        serialized = str(
            render_body_fragments(
                parse_body_fragments(
                    '<p>Keep me</p><span id="mail_unfollow"></span><p>Keep me too</p>'
                )
            )
        )
        self.assertIn(
            '<span id="mail_unfollow"/>',
            serialized,
            "etree.tostring self-closes the empty span -- this is the trigger",
        )
        self.assertEqual(
            self.env["mail.mail"]._strip_unfollow_block(serialized),
            "<p>Keep me</p><p>Keep me too</p>",
        )

    def test_a_populated_span_is_unaffected(self):
        body = (
            '<p>A</p><span id="mail_unfollow"> | '
            '<a href="/mail/unfollow">Unfollow</a></span><p>B</p>'
        )
        self.assertEqual(
            self.env["mail.mail"]._strip_unfollow_block(body), "<p>A</p><p>B</p>"
        )

    def test_a_slash_inside_an_attribute_does_not_read_as_self_closing(self):
        body = (
            '<p>A</p><span id="mail_unfollow" data-path="a/"> | '
            '<a href="/mail/unfollow">Unfollow</a></span><p>B</p>'
        )
        self.assertEqual(
            self.env["mail.mail"]._strip_unfollow_block(body), "<p>A</p><p>B</p>"
        )


@tagged("mail_mail")
class TestMailMailBodyIsBuiltOncePerMail(MailCommon):

    def test_the_document_is_scanned_a_fixed_number_of_times(self):
        partners = self.env["res.partner"].create(
            [
                {"email": "scan%s@test.example.com" % idx, "name": "Scan %s" % idx}
                for idx in range(20)
            ]
        )
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>"
                + "<div>filler</div>" * 200
                + '<span id="mail_unfollow"> | '
                '<a href="/mail/unfollow">Unfollow</a></span>',
                "email_from": "test.from@mycompany.example.com",
                "recipient_ids": [Command.set(partners.ids)],
            }
        )
        MailMail = self.registry["mail.mail"]
        origin = MailMail._resolve_unfollow_span
        scans = []

        def counted(records, body):
            scans.append(body)
            return origin(records, body)

        self.patch(MailMail, "_resolve_unfollow_span", counted)
        results = mail._prepare_outgoing_list()

        self.assertEqual(len(results), 20, "one message per recipient")
        self.assertLessEqual(
            len(scans),
            2,
            "the block is located once for the body, not once per recipient: "
            f"{len(scans)} scans for 20 recipients",
        )
        self.assertEqual(
            len({values["body"] for values in results}),
            1,
            "none of these recipients follows the document, so they all get "
            "the same body",
        )


@tagged("mail_mail")
class TestMailMailSettlingIsNotDelivery(MailCommon):

    def _notification_mail(self):
        partner = self.env["res.partner"].create(
            {"email": "settle@test.example.com", "name": "Settle"}
        )
        message = self.env["mail.message"].create(
            {
                "body": "<p>Body</p>",
                "message_type": "email_outgoing",
                "model": "res.partner",
                "res_id": partner.id,
                "subject": "Subject",
            }
        )
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "is_notification": True,
                "mail_message_id": message.id,
                "recipient_ids": [Command.link(partner.id)],
            }
        )
        self.env["mail.notification"].create(
            {
                "mail_mail_id": mail.id,
                "mail_message_id": message.id,
                "notification_status": "ready",
                "notification_type": "email",
                "res_partner_id": partner.id,
            }
        )
        return mail

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_a_failure_settling_notifications_does_not_unsend_the_mail(self):
        mail = self._notification_mail()
        MailMail = self.registry["mail.mail"]

        def boom(records, *args, **kwargs):
            raise ValueError("an override of the settling seam raised")

        with self.mock_mail_gateway():
            self.patch(MailMail, "_postprocess_sent_message", boom)
            mail.send()

        self.assertEqual(len(self._mails), 1, "SMTP accepted the message")
        self.assertEqual(
            mail.state,
            "sent",
            "the mail was delivered; a later failure recording that fact does "
            "not make it untrue, and must not hand the record back to the queue",
        )
        self.assertFalse(mail.failure_type)

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_a_real_delivery_failure_is_still_an_exception(self):
        mail = self._notification_mail()
        with self.mock_mail_gateway():
            self.send_email_mocked.side_effect = MailDeliveryError("nope")
            mail.send()
        self.assertEqual(mail.state, "exception")
        self.assertEqual(mail.failure_type, "unknown")

    def test_settling_survives_a_multi_record_caller(self):
        mails = self._notification_mail() | self._notification_mail()
        mails._postprocess_sent_message(
            success_partners=[], success_emails=[], failure_type=None
        )
        self.assertEqual(
            set(
                self.env["mail.notification"]
                .search([("mail_mail_id", "in", mails.ids)])
                .mapped("notification_status")
            ),
            {"exception"},
            "every recipient went unreached, and each is recorded as such",
        )


@tagged("mail_mail")
class TestMailMailReturnPath(MailCommon):

    def test_no_bounce_address_leaves_the_header_unset(self):
        self.env.company.bounce_email = False
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "dest@test.example.com",
            }
        )
        self.assertNotIn(
            "Return-Path",
            mail._prepare_outgoing_list()[0]["headers"],
            "stamping '' plants a key that defeats any later setdefault, for a "
            "value ir_mail_server drops anyway",
        )

    def test_a_bounce_address_is_stamped(self):
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "dest@test.example.com",
            }
        )
        expected = (
            mail.record_alias_domain_id.bounce_email or self.env.company.bounce_email
        )
        if not expected:
            self.skipTest("no bounce address configured for this company")
        self.assertEqual(
            mail._prepare_outgoing_list()[0]["headers"]["Return-Path"], expected
        )


@tagged("mail_mail")
class TestMailMailScheduledDateBounds(MailCommon):

    def _fixed_offset(self, hours):
        return datetime_timezone(timedelta(hours=hours))

    def _far_future(self, offset_hours):
        return datetime.max.replace(
            microsecond=0, tzinfo=self._fixed_offset(offset_hours)
        )

    def _far_past(self, offset_hours):
        return datetime.min.replace(tzinfo=self._fixed_offset(offset_hours))

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_a_date_that_overflows_on_conversion_is_dropped(self):
        for label, value in [
            ("max datetime, negative offset", self._far_future(-14)),
            ("min datetime, positive offset", self._far_past(14)),
        ]:
            with self.subTest(case=label):
                with self.assertRaises(OverflowError, msg="the premise: python raises"):
                    value.astimezone(datetime_UTC)
                self.assertFalse(
                    self.env["mail.mail"]._normalize_scheduled_date(value),
                    "an unconvertible date is no date, not an exception",
                )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_create_survives_an_unconvertible_scheduled_date(self):
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "dest@test.example.com",
                "scheduled_date": self._far_future(-14),
            }
        )
        self.assertFalse(
            mail.scheduled_date, "no schedule means the queue sends it immediately"
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_a_string_too_large_for_a_date_is_dropped(self):
        self.assertFalse(
            self.env["mail.mail"]._normalize_scheduled_date("99999999999999999999")
        )

    def test_an_offset_that_stays_in_range_is_converted_not_dropped(self):
        mail = self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "dest@test.example.com",
                "scheduled_date": "2026-06-01 10:00:00+04:00",
            }
        )
        self.assertEqual(
            mail.scheduled_date,
            datetime(2026, 6, 1, 6, 0, 0),
            "stored naive UTC, four hours earlier",
        )


@tagged("mail_mail")
class TestMailMailSizeEstimate(MailCommon):

    def test_attachments_are_counted_at_their_base64_size(self):
        MailMail = self.env["mail.mail"]
        empty = MailMail._estimate_email_size({}, "", [])
        self.assertEqual(
            MailMail._estimate_email_size({}, "", [3_000_000]) - empty,
            4_000_000,
            "base64 is four bytes out for every three in",
        )

    def test_the_envelope_overhead_is_counted_once(self):
        self.assertEqual(
            self.env["mail.mail"]._estimate_email_size({}, "", []),
            10 * 1024 + 2,
            "an empty headers dict serialises to '{}'",
        )

    def test_body_and_headers_are_counted_in_bytes_not_characters(self):
        MailMail = self.env["mail.mail"]
        self.assertEqual(
            MailMail._estimate_email_size({}, "é" * 100, [])
            - MailMail._estimate_email_size({}, "", []),
            200,
            "a two-byte character costs two bytes, not one",
        )

    def test_absent_headers_and_body_are_not_an_error(self):
        self.assertEqual(
            self.env["mail.mail"]._estimate_email_size(None, None, []),
            self.env["mail.mail"]._estimate_email_size({}, "", []),
        )


class _DroppingSMTPSession:

    def __init__(self, drop_on, after_payload=False):
        self.drop_on = drop_on
        self.after_payload = after_payload
        self.attempts = 0
        self.delivered = []

    def send(self, data):
        pass

    def send_message(self, message, smtp_from, smtp_to_list):
        self.attempts += 1
        self.send(f"mail FROM:<{smtp_from}>\r\n")
        if self.attempts == self.drop_on and not self.after_payload:
            raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
        self.send(b"payload\r\n.\r\n")
        if self.attempts == self.drop_on:
            raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
        self.delivered.append(smtp_to_list)

    def quit(self):
        pass

    def set_debuglevel(self, smtp_debug):
        pass

    def ehlo_or_helo_if_needed(self):
        pass


class MailQueueCronCase(MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["mail.mail"].search([]).unlink()
        cls.queue_cron = cls.env.ref("mail.ir_cron_mail_scheduler_action")

    def _as_production(self, model_name, method_name):
        Model = self.registry[model_name]
        origin = getattr(Model, method_name)
        calls = []

        def in_production(records, *args, **kwargs):
            calls.append(records)
            with patch.object(odoo.modules.module, "current_test", False):
                return origin(records, *args, **kwargs)

        self.patch(Model, method_name, in_production)
        return calls

    def _run_cron(self, cron):
        with (
            self.sync_env_with_side_cursors(),
            mute_logger("odoo.addons.base.models.ir_cron"),
            self.registry.cursor() as cr,
        ):
            IrCron = self.registry["ir.cron"]
            IrCron._run_job(
                cr, IrCron._acquire_job(cr, cron.id, include_not_ready=True)
            )
        self.env.invalidate_all()

    def _cron_triggers(self, cron):
        return self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)])

    def _outgoing(self, count, partner=None):
        return self.env["mail.mail"].create(
            [
                {
                    "auto_delete": False,
                    "body_html": f"<p>Queue {idx}</p>",
                    "email_from": "test.from@mycompany.example.com",
                    "email_to": f"queue.{idx}@test.example.com",
                    "recipient_ids": [Command.link(partner.id)] if partner else [],
                    "state": "outgoing",
                }
                for idx in range(count)
            ]
        )


@tagged("mail_mail", "mail_server")
class TestMailMailSessionLoss(MailQueueCronCase):

    def _notified_mail(self, partner):
        message = self.env["mail.message"].create(
            {
                "body": "<p>Body</p>",
                "message_type": "email_outgoing",
                "model": "res.partner",
                "res_id": partner.id,
            }
        )
        mail = self.env["mail.mail"].create(
            {
                "auto_delete": False,
                "body_html": "<p>Notified</p>",
                "email_from": "test.from@mycompany.example.com",
                "is_notification": True,
                "mail_message_id": message.id,
                "recipient_ids": [Command.link(partner.id)],
            }
        )
        notification = self.env["mail.notification"].create(
            {
                "mail_mail_id": mail.id,
                "mail_message_id": message.id,
                "notification_status": "ready",
                "notification_type": "email",
                "res_partner_id": partner.id,
            }
        )
        return mail, notification

    def _run_queue_dropping(self, drop_on, after_payload):
        partner = self.env["res.partner"].create(
            {"email": "dropped@test.example.com", "name": "Dropped"}
        )
        first = self._outgoing(1)
        interrupted, notification = self._notified_mail(partner)
        last = self._outgoing(1)
        self._cron_triggers(self.queue_cron).unlink()
        self._as_production("mail.mail", "process_email_queue")
        with self.mock_mail_gateway(), mute_logger("odoo.addons.mail.models.mail_mail"):
            self.testing_smtp_session = _DroppingSMTPSession(drop_on, after_payload)
            self._run_cron(self.queue_cron)
        return first, interrupted, notification, last

    def test_session_lost_before_handover_keeps_the_mail_queued(self):
        first, interrupted, notification, last = self._run_queue_dropping(
            drop_on=2, after_payload=False
        )
        self.assertEqual(
            self.queue_cron.failure_count, 0, "a lost session is not a job failure"
        )
        self.assertTrue(self.queue_cron.active)
        self.assertEqual(first.state, "sent")
        self.assertEqual(
            (interrupted.state, interrupted.failure_type, interrupted.failure_reason),
            ("outgoing", False, False),
            "nothing was handed over, so the mail goes back to the queue instead "
            "of keeping the placeholder",
        )
        self.assertEqual(
            (notification.notification_status, notification.failure_type),
            ("ready", False),
        )
        self.assertEqual(last.state, "outgoing", "the pass ended with the session")
        triggers = self._cron_triggers(self.queue_cron)
        self.assertTrue(triggers, "the queue runs again shortly, not in an hour")
        self.assertLessEqual(
            max(triggers.mapped("call_at")),
            fields.Datetime.now() + timedelta(minutes=5),
        )

    def test_session_lost_after_handover_is_an_explicit_failure(self):
        first, interrupted, notification, last = self._run_queue_dropping(
            drop_on=2, after_payload=True
        )
        self.assertEqual(self.queue_cron.failure_count, 0)
        self.assertEqual(first.state, "sent")
        self.assertEqual(
            (interrupted.state, interrupted.failure_type),
            ("exception", "mail_smtp"),
            "the server may hold the message: at most once, and the reason says so",
        )
        self.assertIn("may have been delivered", interrupted.failure_reason)
        self.assertEqual(
            (notification.notification_status, notification.failure_type),
            ("exception", "mail_smtp"),
        )
        self.assertEqual(last.state, "outgoing")

    def test_session_lost_outside_the_cron_does_not_raise(self):
        mails = self._outgoing(3)
        self._cron_triggers(self.queue_cron).unlink()
        with self.mock_mail_gateway(), mute_logger("odoo.addons.mail.models.mail_mail"):
            self.testing_smtp_session = _DroppingSMTPSession(2)
            completed = mails.send()
        self.assertFalse(completed)
        self.assertEqual(mails.mapped("state"), ["sent", "outgoing", "outgoing"])
        self.assertTrue(self._cron_triggers(self.queue_cron))

    def test_session_lost_raises_a_delivery_error_when_asked_to(self):
        mails = self._outgoing(2)
        with (
            self.mock_mail_gateway(),
            mute_logger("odoo.addons.mail.models.mail_mail"),
            self.assertRaises(MailDeliveryError),
        ):
            self.testing_smtp_session = _DroppingSMTPSession(1)
            mails.send(raise_exception=True)


@tagged("mail_mail")
class TestMailMailQueueTimeBudget(MailQueueCronCase):

    def test_the_queue_stops_when_the_budget_is_spent(self):
        self._outgoing(3)
        sent_per_call = []
        MailMail = self.registry["mail.mail"]
        origin = MailMail.process_email_queue

        def counting(records, *args, **kwargs):
            before = len(self._mails)
            with patch.object(odoo.modules.module, "current_test", False):
                origin(records, *args, **kwargs)
            sent_per_call.append(len(self._mails) - before)

        self.patch(MailMail, "process_email_queue", counting)
        IrCron = self.registry["ir.cron"]
        commit_progress_origin = IrCron._commit_progress

        def spent(records, *args, **kwargs):
            commit_progress_origin(records, *args, **kwargs)
            return 0.0

        self.patch(IrCron, "_commit_progress", spent)
        with (
            self.mock_mail_gateway(),
            patch.object(mail_mail_module, "_PROGRESS_REPORT_EVERY", 1),
        ):
            self._run_cron(self.queue_cron)
        self.assertEqual(
            sent_per_call[0], 1, f"one mail per exhausted budget: {sent_per_call}"
        )
        self.assertEqual(sum(sent_per_call), 3, "and the next calls finish the queue")


@tagged("mail_mail")
class TestMailMailQueueTriggers(MailCommon):

    def _triggers(self):
        cron = self.env.ref("mail.ir_cron_mail_scheduler_action")
        return self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)])

    def _mail(self, **values):
        return self.env["mail.mail"].create(
            {
                "body_html": "<p>Body</p>",
                "email_from": "test.from@mycompany.example.com",
                "email_to": "trigger@test.example.com",
                **values,
            }
        )

    def test_a_future_scheduled_date_triggers_the_queue_then(self):
        self._triggers().unlink()
        at = fields.Datetime.now().replace(second=0) + timedelta(hours=3)
        self._mail(scheduled_date=at)
        self.assertEqual(self._triggers().mapped("call_at"), [at])

    def test_rescheduling_triggers_the_queue_then(self):
        mail = self._mail()
        self._triggers().unlink()
        at = fields.Datetime.now().replace(second=0) + timedelta(hours=5)
        mail.scheduled_date = at
        self.assertEqual(self._triggers().mapped("call_at"), [at])

    def test_an_immediate_mail_does_not_trigger_on_create(self):
        self._triggers().unlink()
        self._mail()
        self.assertFalse(
            self._triggers(),
            "an immediate mail is sent by whoever created it; waking the queue "
            "too would race the two senders",
        )

    def test_retrying_triggers_the_queue(self):
        mail = self._mail()
        mail.write({"state": "exception", "failure_type": "unknown"})
        self._triggers().unlink()
        mail.action_retry()
        self.assertEqual(mail.state, "outgoing")
        self.assertTrue(self._triggers())
        self.assertLessEqual(
            max(self._triggers().mapped("call_at")),
            fields.Datetime.now() + timedelta(minutes=1),
        )


@tagged("mail_mail")
class TestMailMessageScheduleCron(MailQueueCronCase):

    def _schedules(self, count):
        partner = self.env["res.partner"].create(
            {"email": "scheduled@test.example.com", "name": "Scheduled"}
        )
        messages = self.env["mail.message"].create(
            [
                {
                    "body": f"<p>Scheduled {idx}</p>",
                    "message_type": "comment",
                    "model": "res.partner",
                    "res_id": partner.id,
                }
                for idx in range(count)
            ]
        )
        return self.env["mail.message.schedule"].create(
            [
                {
                    "mail_message_id": message.id,
                    "scheduled_datetime": fields.Datetime.now() - timedelta(minutes=1),
                }
                for message in messages
            ]
        )

    def test_due_schedules_are_sent_as_one_chunk(self):
        self._schedules(3)
        Schedule = self.registry["mail.message.schedule"]
        origin = Schedule._send_notifications
        sizes = []

        def counted(records, *args, **kwargs):
            sizes.append(len(records))
            return origin(records, *args, **kwargs)

        self.patch(Schedule, "_send_notifications", counted)
        self.env["mail.message.schedule"]._send_notifications_cron()
        self.assertEqual(
            sizes, [3], "one grouped exists() and one commit, not one per schedule"
        )
        self.assertFalse(self.env["mail.message.schedule"].search([]))

    @mute_logger("odoo.addons.mail.models.mail_message_schedule")
    def test_a_transient_failure_retries_soon(self):
        schedules = self._schedules(2)
        conflicted = schedules[0]
        Schedule = self.registry["mail.message.schedule"]
        origin = Schedule._send_notifications

        def conflicting(records, *args, **kwargs):
            if conflicted in records:
                raise psycopg.errors.SerializationFailure("concurrent update")
            return origin(records, *args, **kwargs)

        self.patch(Schedule, "_send_notifications", conflicting)
        cron = self.env.ref("mail.ir_cron_send_scheduled_message")
        self._cron_triggers(cron).unlink()
        self.env["mail.message.schedule"]._send_notifications_cron()
        self.assertEqual(
            self.env["mail.message.schedule"].search([]),
            conflicted,
            "the other schedule is sent; the conflicted one waits for a retry",
        )
        self.assertTrue(
            self._cron_triggers(cron),
            "and the retry is scheduled, not left to the hourly run",
        )


@tagged("mail_mail")
class TestMailMailSettlingDatabaseError(MailQueueCronCase):

    def _failing_on(self, mail):
        MailMail = self.registry["mail.mail"]
        origin = MailMail._postprocess_sent_message

        def failing_statement(records, *args, **kwargs):
            if records == mail:
                records.env.cr.execute("SELECT 1 / 0")
            return origin(records, *args, **kwargs)

        self.patch(MailMail, "_postprocess_sent_message", failing_statement)

    @mute_logger("odoo.addons.mail.models.mail_mail", "odoo.db.cursor")
    def test_under_auto_commit_the_delivery_survives(self):
        first, second = self._outgoing(2)
        self._failing_on(first)
        self._as_production("mail.mail", "process_email_queue")
        with self.mock_mail_gateway():
            self._run_cron(self.queue_cron)
        self.assertEqual(len(self._mails), 2, "both mails went out")
        self.assertEqual(self.queue_cron.failure_count, 0)
        self.assertEqual(
            (first.state, first.failure_type), ("sent", False), "and say so"
        )
        self.assertEqual(second.state, "sent", "the run went on to the next mail")

    @mute_logger("odoo.addons.mail.models.mail_mail", "odoo.db.cursor")
    def test_without_auto_commit_the_error_propagates(self):
        first, second = self._outgoing(2)
        self._failing_on(first)
        with (
            self.mock_mail_gateway(),
            self.assertRaises(psycopg.errors.DivisionByZero),
        ):
            (first | second).send()
