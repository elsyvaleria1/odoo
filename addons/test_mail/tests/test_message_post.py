import base64
from datetime import UTC, datetime, timedelta
from itertools import product
from unittest.mock import patch

from freezegun import freeze_time
from markupsafe import Markup, escape

from odoo import tools
from odoo.exceptions import AccessError
from odoo.libs.json import loads as json_loads
from odoo.service.model import call_kw
from odoo.tests import tagged
from odoo.tests.common import users
from odoo.tools import formataddr, mute_logger

from odoo.addons.base.tests.test_ir_cron import CronMixinCase
from odoo.addons.mail.tests.common import MailCommon, mail_new_test_user
from odoo.addons.test_mail.data.test_mail_data import MAIL_TEMPLATE_PLAINTEXT
from odoo.addons.test_mail.models.test_mail_models import MailTestSimple
from odoo.addons.test_mail.tests.common import TestRecipients


class TestMessagePostCommon(MailCommon, TestRecipients):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user_portal = cls._create_portal_user()
        cls.partner_portal = cls.user_portal.partner_id

        cls.user_employee_2 = mail_new_test_user(
            cls.env,
            login="employee2",
            groups="base.group_user",
            company_id=cls.company_admin.id,
            email="eglantine@example.com",
            name="Eglantine Employee2",
            notification_type="email",
            signature="--\nEglantine",
        )
        cls.partner_employee_2 = cls.user_employee_2.partner_id

        cls.test_record = (
            cls.env["mail.test.simple"]
            .with_context(cls._test_context)
            .create({"name": "Test", "email_from": "ignasse@example.com"})
        )
        cls.test_records_simple, _partners = cls._create_records_for_batch(
            "mail.test.simple",
            3,
        )
        cls.test_record_container = cls.env["mail.test.container.mc"].create(
            {
                "name": "MC Container",
            }
        )
        cls.test_record_ticket = cls.env["mail.test.ticket.mc"].create(
            {
                "container_id": cls.test_record_container.id,
                "email_from": "test.customer@test.example.com",
                "name": "MC Ticket",
            }
        )
        cls._reset_mail_context(cls.test_record)
        cls.test_message = cls.env["mail.message"].create(
            {
                "author_id": cls.partner_employee.id,
                "body": "<p>Notify Body <span>Woop Woop</span></p>",
                "email_from": cls.partner_employee.email_formatted,
                "is_internal": False,
                "message_id": tools.mail.generate_tracking_message_id("dummy-generate"),
                "message_type": "comment",
                "model": cls.test_record._name,
                "reply_to": "wrong.alias@test.example.com",
                "subtype_id": cls.env["ir.model.data"]._xmlid_to_res_id(
                    "mail.mt_comment"
                ),
                "subject": "Notify Test",
            }
        )
        cls.user_admin.write({"notification_type": "email"})

    def setUp(self):
        super().setUp()
        self.patch(self.env.registry, "ready", True)


@tagged("mail_post", "mail_notify")
class TestMailNotifyAPI(TestMessagePostCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_lang_records = cls.env["mail.test.lang"].create(
            [
                {
                    "customer_id": False,
                    "email_from": "test.record.1@test.customer.com",
                    "lang": "es_ES",
                    "name": "TestRecord1",
                },
                {
                    "customer_id": cls.partner_2.id,
                    "email_from": "valid.other@gmail.com",
                    "name": "TestRecord2",
                },
            ]
        )
        cls.test_lang_template = cls.env[
            "mail.template"
        ].create(
            {
                "auto_delete": True,
                "body_html": '<p>EnglishBody for <t t-out="object.name"/></p>',
                "email_from": "{{ user.email_formatted }}",
                "email_layout_xmlid": "mail.test_layout",
                "lang": "{{ object.customer_id.lang or object.lang }}",
                "model_id": cls.env["ir.model"]._get("mail.test.lang").id,
                "name": "TestTemplate",
                "subject": "EnglishSubject for {{ object.name }}",
                "use_default_to": True,
            }
        )
        cls._activate_multi_lang(
            test_record=cls.test_lang_records[0], test_template=cls.test_lang_template
        )

    @mute_logger("odoo.models.unlink")
    @users("employee")
    def test_email_notification_layouts(self):
        self.user_employee.write({"notification_type": "email"})
        test_record = self.env["mail.test.simple"].browse(self.test_record.ids)
        test_message = self.env["mail.message"].browse(self.test_message.ids)

        recipients_data = self._generate_notify_recipients(
            self.partner_1 + self.partner_2 + self.partner_employee
        )
        for email_xmlid in [
            "mail.mail_notification_light",
            "mail.mail_notification_layout",
            "mail.mail_notification_layout_with_responsible_signature",
        ]:
            test_message.sudo().notification_ids.unlink()
            test_message.write({"email_layout_xmlid": email_xmlid})
            with self.mock_mail_gateway():
                test_record._notify_thread_by_email(
                    test_message,
                    recipients_data,
                    force_send=False,
                )
            self.assertEqual(
                len(self._new_mails),
                2,
                "Should have 2 emails: one for customers, one for internal users",
            )

            customer_email = self._new_mails.filtered(
                lambda mail: mail.recipient_ids == self.partner_1 + self.partner_2
            )
            self.assertTrue(customer_email)

            user_email = self._new_mails.filtered(
                lambda mail: mail.recipient_ids == self.partner_employee
            )
            self.assertTrue(user_email)

    @mute_logger("odoo.models.unlink")
    @users("employee")
    def test_email_notification_layouts_header_footer(self):
        (self.user_employee + self.user_employee_c2).write(
            {"notification_type": "email"}
        )
        test_lang_record = self.env["mail.test.lang"].browse(
            self.test_lang_records[0].ids
        )
        test_lang_record.message_subscribe(
            partner_ids=(self.partner_1 + self.partner_employee_c2).ids
        )
        test_classic_record = self.env["mail.test.simple"].browse(self.test_record.ids)
        test_classic_record.message_subscribe(
            partner_ids=(self.partner_1 + self.partner_employee_c2).ids
        )

        for record, add_ctx, exp_header_for, exp_footer_for, exp_unfollow_for in [
            (
                test_lang_record,
                {},
                self.partner_1 + self.partner_2 + self.partner_employee_c2,
                self.env["res.partner"],
                self.env["res.partner"],
            ),
            (
                test_lang_record,
                {"email_notification_allow_footer": True},
                self.partner_1 + self.partner_2 + self.partner_employee_c2,
                self.partner_1
                + self.partner_2
                + self.partner_employee_c2,
                self.partner_employee_c2,
            ),
            (
                test_classic_record,
                {},
                self.partner_employee_c2,
                self.env["res.partner"],
                self.env["res.partner"],
            ),
            (
                test_classic_record,
                {"email_notification_force_header": True},
                self.partner_1 + self.partner_2 + self.partner_employee_c2,
                self.env["res.partner"],
                self.env["res.partner"],
            ),
            (
                test_classic_record,
                {
                    "email_notification_force_header": True,
                    "email_notification_allow_footer": True,
                },
                self.partner_1 + self.partner_2 + self.partner_employee_c2,
                self.partner_1
                + self.partner_2
                + self.partner_employee_c2,
                self.partner_employee_c2,
            ),
            (
                test_classic_record,
                {"email_notification_force_footer": True},
                self.partner_employee_c2,
                self.partner_1
                + self.partner_2
                + self.partner_employee_c2,
                self.partner_employee_c2,
            ),
        ]:
            with self.subTest(record_name=record.name, add_ctx=add_ctx):
                with self.mock_mail_gateway():
                    _message = record.with_context(**add_ctx).message_post(
                        body="Test Layout / Tweak",
                        email_layout_xmlid="mail.test_layout",
                        partner_ids=self.partner_2.ids,
                        message_type="comment",
                        subtype_id=self.env.ref("mail.mt_comment").id,
                    )

                for partner in (
                    self.partner_1 + self.partner_2 + self.partner_employee_c2
                ):
                    found_email = self._find_sent_email(
                        self.env.user.email_formatted, [partner.email_formatted]
                    )
                    if partner in exp_header_for:
                        self.assertIn("HEADER", found_email["body"])
                    else:
                        self.assertNotIn("HEADER", found_email["body"])
                    if partner in exp_footer_for:
                        self.assertIn(
                            f"Sent by {self.env.company.name}", found_email["body"]
                        )
                    else:
                        self.assertNotIn(
                            f"Sent by {self.env.company.name}", found_email["body"]
                        )
                    if partner in exp_unfollow_for:
                        self.assertIn(
                            f"mail/unfollow?model={record._name}&pid={partner.id}&res_id={record.id}",
                            found_email["body"],
                        )
                    else:
                        self.assertNotIn("mail/unfollow", found_email["body"])

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_notify_by_mail_add_signature(self):
        test_track = (
            self.env["mail.test.track"]
            .with_context(self._test_context)
            .with_user(self.user_employee)
            .create({"name": "Test", "email_from": "ignasse@example.com"})
        )
        test_track.user_id = self.env.user

        signature = self.env.user.signature

        template = self.env.ref(
            "mail.mail_notification_layout_with_responsible_signature",
            raise_if_not_found=True,
        ).sudo()
        self.assertIn("record.user_id.sudo().signature", template.arch)

        with self.mock_mail_gateway():
            test_track.message_post(
                body="Test body",
                email_add_signature=True,
                email_layout_xmlid="mail.mail_notification_layout_with_responsible_signature",
                mail_auto_delete=False,
                partner_ids=[self.partner_1.id, self.partner_2.id],
            )
        found_mail = self._new_mails
        self.assertIn(signature, found_mail.body_html)
        self.assertEqual(found_mail.body_html.count(signature), 1)

        with self.mock_mail_gateway():
            test_track.message_post(
                body="Test body",
                email_add_signature=False,
                email_layout_xmlid="mail.mail_notification_layout_with_responsible_signature",
                mail_auto_delete=False,
                partner_ids=[self.partner_1.id, self.partner_2.id],
            )
        found_mail = self._new_mails
        self.assertNotIn(signature, found_mail.body_html)
        self.assertEqual(found_mail.body_html.count(signature), 0)

    @users("employee")
    def test_notify_by_email_add_signature_no_author_user_or_no_user(self):
        test_record = self.env["mail.test.simple"].browse(self.test_record.ids)
        test_message = self.env["mail.message"].browse(self.test_message.ids)
        test_message.write(
            {
                "author_id": self.env["res.partner"]
                .sudo()
                .create(
                    {
                        "name": "Steve",
                    }
                )
                .id
            }
        )
        test_message.sudo().email_add_signature
        template_values = test_record._notify_by_email_prepare_rendering_context(
            test_message, {}
        )
        self.assertNotEqual(
            escape(template_values["signature"]), escape("<p>-- <br/>Steve</p>")
        )

        self.test_message.author_id = None
        template_values = test_record._notify_by_email_prepare_rendering_context(
            test_message, {}
        )
        self.assertEqual(template_values["signature"], "")

    @users("employee")
    def test_notify_by_email_prepare_rendering_context(self):
        current_user = self.env.user
        main_company = current_user.company_id
        other_company = (
            self.env["res.company"]
            .with_user(self.user_admin)
            .create({"name": "Company B"})
        )
        current_user.sudo().write({"company_ids": [(4, other_company.id)]})
        test_record = (
            self.env["mail.test.multi.company"]
            .with_user(self.user_admin)
            .create(
                {
                    "name": "Multi Company Record",
                    "company_id": False,
                }
            )
        )

        self.assertEqual(self.env.company.id, main_company.id)
        self.assertEqual(test_record.company_id.id, False)
        template_values = test_record._notify_by_email_prepare_rendering_context(
            test_record.message_ids, {}
        )
        self.assertEqual(template_values.get("company").id, self.env.company.id)

        current_user.company_id = other_company
        test_record = self.env["mail.test.multi.company"].browse(test_record.id)
        self.assertEqual(self.env.company.id, other_company.id)
        self.assertEqual(test_record.company_id.id, False)
        template_values = test_record._notify_by_email_prepare_rendering_context(
            test_record.message_ids, {}
        )
        self.assertEqual(template_values.get("company").id, self.env.company.id)

        test_record.company_id = main_company
        test_record = self.env["mail.test.multi.company"].browse(test_record.id)
        self.assertEqual(self.env.company.id, other_company.id)
        self.assertEqual(test_record.company_id.id, main_company.id)
        template_values = test_record._notify_by_email_prepare_rendering_context(
            test_record.message_ids, {}
        )
        self.assertEqual(template_values.get("company").id, main_company.id)

    @users("employee")
    def test_notify_recipients_internals(self):
        base_record = self.test_record.with_env(self.env)
        pdata = self._generate_notify_recipients(self.partner_1 | self.partner_employee)
        msg_vals = {
            "body": "Message body",
            "model": base_record._name,
            "res_id": base_record.id,
            "subject": "Message subject",
        }
        link_vals = {
            "token": "token_val",
            "access_token": "access_token_val",
            "auth_signup_token": "auth_signup_token_val",
            "auth_login": "auth_login_val",
        }
        notify_msg_vals = dict(msg_vals, **link_vals)

        classify_res = self.env[base_record._name]._notify_get_recipients_classify(
            self.env["mail.message"],
            pdata,
            "My Custom Model Name",
            msg_vals=notify_msg_vals,
        )
        partner_info = next(
            item
            for item in classify_res
            if item["recipients_ids"] == self.partner_1.ids
        )
        emp_info = next(
            item
            for item in classify_res
            if item["recipients_ids"] == self.partner_employee.ids
        )
        self.assertFalse(partner_info["has_button_access"])
        self.assertTrue(emp_info["has_button_access"])
        for param, value in link_vals.items():
            self.assertIn(f"{param}={value}", emp_info["button_access"]["url"])
        self.assertIn(f"model={base_record._name}", emp_info["button_access"]["url"])
        self.assertIn(f"res_id={base_record.id}", emp_info["button_access"]["url"])
        self.assertNotIn("body", emp_info["button_access"]["url"])
        self.assertNotIn("subject", emp_info["button_access"]["url"])

        for model, res_id in (
            (base_record._name, False),
            (base_record._name, 0),
            ("mixin.mail.thread", False),
            ("mixin.mail.thread", base_record.id),
        ):
            with self.subTest(model=model, res_id=res_id):
                notify_msg_vals.update(
                    {
                        "model": model,
                        "res_id": res_id,
                    }
                )
                classify_res = (
                    self.env[model]
                    .browse(res_id)
                    ._notify_get_recipients_classify(
                        self.env["mail.message"],
                        pdata,
                        "Test",
                        msg_vals=notify_msg_vals,
                    )
                )
                partner_info = next(
                    item
                    for item in classify_res
                    if item["recipients_ids"] == self.partner_1.ids
                )
                emp_info = next(
                    item
                    for item in classify_res
                    if item["recipients_ids"] == self.partner_employee.ids
                )
                self.assertFalse(partner_info["has_button_access"])
                self.assertFalse(emp_info["has_button_access"])

        for model, res_id in (
            (base_record._name, False),
            (base_record._name, 0),
            (False, base_record.id),
            (False, False),
            ("mixin.mail.thread", False),
            ("mixin.mail.thread", base_record.id),
        ):
            with self.subTest(model=model, res_id=res_id):
                notify_msg_vals.update(
                    {
                        "model": model,
                        "res_id": res_id,
                    }
                )
                classify_res = base_record._notify_get_recipients_classify(
                    self.env["mail.message"],
                    pdata,
                    "Test",
                    msg_vals=notify_msg_vals,
                )
                partner_info = next(
                    item
                    for item in classify_res
                    if item["recipients_ids"] == self.partner_1.ids
                )
                emp_info = next(
                    item
                    for item in classify_res
                    if item["recipients_ids"] == self.partner_employee.ids
                )
                self.assertFalse(partner_info["has_button_access"])
                self.assertFalse(emp_info["has_button_access"])


@tagged("mail_post", "mail_notify")
class TestMessageNotify(TestMessagePostCommon):
    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_notify(self):
        test_record = self.env["mail.test.simple"].browse(self.test_record.ids)

        with self.assertSinglePostNotifications(
            [
                {
                    "partner": self.partner_1,
                    "type": "email",
                },
                {
                    "partner": self.partner_admin,
                    "type": "email",
                },
                {
                    "partner": self.partner_employee_2,
                    "type": "email",
                },
            ],
            message_info={
                "content": "<p>You have received a notification</p>",
                "message_type": "user_notification",
                "message_values": {
                    "author_id": self.partner_employee,
                    "body": "<p>You have received a notification</p>",
                    "email_from": formataddr(
                        (
                            self.partner_employee.name,
                            self.partner_employee.email_normalized,
                        )
                    ),
                    "message_type": "user_notification",
                    "model": test_record._name,
                    "notified_partner_ids": self.partner_1
                    | self.partner_employee_2
                    | self.partner_admin,
                    "res_id": test_record.id,
                    "subtype_id": self.env.ref("mail.mt_note"),
                },
                "subtype": "mail.mt_note",
            },
        ):
            new_notification = test_record.message_notify(
                body=Markup("<p>You have received a notification</p>"),
                partner_ids=[
                    self.partner_1.id,
                    self.partner_admin.id,
                    self.partner_employee_2.id,
                ],
                subject="This should be a subject",
            )
        self.assertNotIn(new_notification, self.test_record.message_ids)

        copy = new_notification.copy()
        self.assertFalse(copy.notified_partner_ids)

        admin_mails = [
            mail
            for mail in self._mails
            if self.partner_admin.name in mail.get("email_to")[0]
        ]
        self.assertEqual(
            len(admin_mails), 1, "There should be exactly one email sent to admin"
        )
        admin_mail_body = admin_mails[0].get("body")

        self.assertTrue(
            "model=" in admin_mail_body,
            "The email sent to admin should contain an access link",
        )
        admin_access_link = admin_mail_body[
            admin_mail_body.index("model=") : admin_mail_body.index(
                "/>", admin_mail_body.index("model=")
            )
            - 1
        ]
        self.assertIn(
            f"model={self.test_record._name}",
            admin_access_link,
            "The access link should contain a valid model argument",
        )
        self.assertIn(
            f"res_id={self.test_record.id}",
            admin_access_link,
            "The access link should contain a valid res_id argument",
        )

        partner_mails = [
            x for x in self._mails if self.partner_1.name in x.get("email_to")[0]
        ]
        self.assertEqual(
            len(partner_mails), 1, "There should be exactly one email sent to partner"
        )
        partner_mail_body = partner_mails[0].get("body")
        self.assertNotIn(
            "/mail/view?model=",
            partner_mail_body,
            "The email sent to customer should not contain an access link",
        )

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_notify_author(self):
        test_record = self.env["mail.test.simple"].browse(self.test_record.ids)

        with self.mock_mail_gateway():
            new_notification = test_record.message_notify(
                body=Markup("<p>You have received a notification</p>"),
                notify_author_mention=False,
                partner_ids=(self.partner_1 + self.partner_employee).ids,
                subject="This should be a subject",
            )

        self.assertEqual(new_notification.notified_partner_ids, self.partner_1)

        with self.mock_mail_gateway():
            new_notification = test_record.message_notify(
                body=Markup("<p>You have received a notification</p>"),
                partner_ids=(self.partner_1 + self.partner_employee).ids,
                subject="This should be a subject",
            )

        self.assertEqual(
            new_notification.notified_partner_ids,
            self.partner_1 + self.partner_employee,
            "Notify: notify_author parameter skips the author restriction",
        )

        with self.mock_mail_gateway():
            new_notification = test_record.with_context(
                mail_notify_author=True
            ).message_notify(
                body=Markup("<p>You have received a notification</p>"),
                partner_ids=(self.partner_1 + self.partner_employee).ids,
                subject="This should be a subject",
            )

        self.assertEqual(
            new_notification.notified_partner_ids,
            self.partner_1 + self.partner_employee,
            "Notify: mail_notify_author context key skips the author restriction",
        )

    @users("employee")
    def test_notify_batch(self):
        test_records, _partners = self._create_records_for_batch("mail.test.simple", 10)

        with self.assertRaises(ValueError):
            test_records.message_notify(
                body=Markup("<p>Nice notification content</p>"),
                partner_ids=self.partner_employee_2.ids,
                subject="Notify Subject",
            )

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_notify_from_user_id(self):
        test_records, _ = self._create_records_for_batch(
            "mail.test.track",
            10,
            {
                "company_id": self.env.user.company_id.id,
                "email_from": self.env.user.email_formatted,
                "user_id": False,
            },
        )
        test_records = self.env["mail.test.track"].browse(test_records.ids)
        self.flush_tracking()

        with self.mock_mail_gateway(), self.mock_mail_app():
            test_records.write({"user_id": self.user_employee_2.id})
            self.flush_tracking()

        self.assertEqual(
            len(self._new_msgs),
            20,
            "Should have 20 messages: 10 tracking and 10 assignments",
        )
        model_name = self.env["ir.model"].sudo()._get(test_records._name).name
        for test_record in test_records:
            assign_notif = self._new_msgs.filtered_domain(
                [
                    ("message_type", "=", "user_notification"),
                    ("res_id", "=", test_record.id),
                ]
            )
            self.assertTrue(assign_notif)
            self.assertMailNotifications(
                assign_notif,
                [
                    {
                        "content": f"You have been assigned to the {model_name}",
                        "email_values": {
                            "subject": f"You have been assigned to {test_record.name}",
                        },
                        "message_type": "user_notification",
                        "message_values": {
                            "author_id": self.partner_employee,
                            "email_from": formataddr(
                                (
                                    self.partner_employee.name,
                                    self.partner_employee.email_normalized,
                                )
                            ),
                            "model": test_record._name,
                            "notified_partner_ids": self.partner_employee_2,
                            "res_id": test_record.id,
                        },
                        "notif": [
                            {
                                "partner": self.partner_employee_2,
                                "type": "email",
                            },
                        ],
                        "subtype": "mail.mt_note",
                    }
                ],
            )

    @users("employee")
    @mute_logger(
        "odoo.addons.mail.models.mail_mail", "odoo.models.unlink", "odoo.tests"
    )
    def test_notify_parameters(self):
        test_record = self.test_record.with_env(self.env)

        for parameters in [
            {"message_type": "comment"},
            {"child_ids": []},
            {"mail_ids": []},
            {"notification_ids": []},
            {"notified_partner_ids": []},
            {"reaction_ids": []},
            {"starred_partner_ids": []},
        ]:
            with (
                self.subTest(parameters=parameters),
                self.mock_mail_gateway(),
                self.assertRaises(ValueError),
            ):
                _new_message = test_record.message_notify(
                    body=Markup("<p>You will not receive a notification</p>"),
                    partner_ids=self.partner_1.ids,
                    subject="This should not be accepted",
                    **parameters,
                )

        new_message = test_record.message_notify(
            body=Markup("<p>You will not receive a notification</p>"),
            partner_ids=self.partner_1.ids,
            subtype_xmlid="mail.mt_note",
        )
        self.assertEqual(new_message.subtype_id, self.env.ref("mail.mt_note"))

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_notify_thread(self):
        with self.mock_mail_gateway():
            new_notification = self.env["mixin.mail.thread"].message_notify(
                body=Markup("<p>You have received a notification</p>"),
                partner_ids=[
                    self.partner_1.id,
                    self.partner_admin.id,
                    self.partner_employee_2.id,
                ],
                subject="This should be a subject",
            )

        self.assertMailNotifications(
            new_notification,
            [
                {
                    "content": "<p>You have received a notification</p>",
                    "message_type": "user_notification",
                    "message_values": {
                        "author_id": self.partner_employee,
                        "body": "<p>You have received a notification</p>",
                        "email_from": formataddr(
                            (
                                self.partner_employee.name,
                                self.partner_employee.email_normalized,
                            )
                        ),
                        "model": False,
                        "res_id": False,
                        "notified_partner_ids": self.partner_1
                        | self.partner_employee_2
                        | self.partner_admin,
                        "subtype_id": self.env.ref("mail.mt_note"),
                    },
                    "notif": [
                        {
                            "partner": self.partner_1,
                            "type": "email",
                        },
                        {
                            "partner": self.partner_employee_2,
                            "type": "email",
                        },
                        {
                            "partner": self.partner_admin,
                            "type": "email",
                        },
                    ],
                    "subtype": "mail.mt_note",
                }
            ],
        )


@tagged("mail_post")
class TestMessageLog(TestMessagePostCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_records, cls.test_partners = cls._create_records_for_batch(
            "mail.test.ticket",
            10,
        )

    @users("employee")
    def test_message_log(self):
        test_record = self.env["mail.test.simple"].browse(self.test_record.ids)
        test_record.message_subscribe(self.partner_employee_2.ids)

        with self.mock_mail_gateway():
            new_note = test_record._message_log(
                body=Markup("<p>Labrador</p>"),
            )
        self.assertMailNotifications(
            new_note,
            [
                {
                    "content": "<p>Labrador</p>",
                    "message_type": "notification",
                    "message_values": {
                        "author_id": self.partner_employee,
                        "body": "<p>Labrador</p>",
                        "email_from": formataddr(
                            (
                                self.partner_employee.name,
                                self.partner_employee.email_normalized,
                            )
                        ),
                        "is_internal": True,
                        "model": test_record._name,
                        "notified_partner_ids": self.env["res.partner"],
                        "partner_ids": self.env["res.partner"],
                        "reply_to": formataddr(
                            (
                                self.partner_employee.name,
                                f"{self.alias_catchall}@{self.alias_domain}",
                            )
                        ),
                        "res_id": test_record.id,
                    },
                    "notif": [],
                    "subtype": "mail.mt_note",
                }
            ],
        )

    @users("employee")
    def test_message_log_batch_author_from_email(self):
        test_records = self.test_records.with_env(self.env)
        self.assertGreater(len(test_records), 1, "sanity: needs a real batch")
        bodies = {record.id: Markup("<p>log</p>") for record in test_records}

        notes = test_records._message_log_batch(
            bodies=bodies, email_from="ext@example.com"
        )
        self.assertEqual(len(notes), len(test_records))
        self.assertEqual(set(notes.mapped("email_from")), {"ext@example.com"})

        notes = test_records._message_log_batch(
            bodies=bodies,
            email_from="ext@example.com",
            author_id=self.partner_employee_2.id,
        )
        self.assertEqual(set(notes.mapped("author_id")), {self.partner_employee_2})

    @users("employee")
    def test_message_log_batch(self):
        test_records = self.test_records.with_env(self.env)
        test_records.message_subscribe(self.partner_employee_2.ids)

        with self.mock_mail_gateway():
            new_notes = test_records._message_log_batch(
                bodies={
                    test_record.id: Markup("<p>Test _message_log_batch</p>")
                    for test_record in test_records
                },
            )
        for test_record, new_note in zip(test_records, new_notes, strict=True):
            self.assertMailNotifications(
                new_note,
                [
                    {
                        "content": "<p>Test _message_log_batch</p>",
                        "message_type": "notification",
                        "message_values": {
                            "author_id": self.partner_employee,
                            "body": "<p>Test _message_log_batch</p>",
                            "email_from": formataddr(
                                (
                                    self.partner_employee.name,
                                    self.partner_employee.email_normalized,
                                )
                            ),
                            "is_internal": True,
                            "model": test_record._name,
                            "notified_partner_ids": self.env["res.partner"],
                            "partner_ids": self.env["res.partner"],
                            "reply_to": formataddr(
                                (
                                    self.partner_employee.name,
                                    f"{self.alias_catchall}@{self.alias_domain}",
                                )
                            ),
                            "res_id": test_record.id,
                        },
                        "notif": [],
                        "subtype": "mail.mt_note",
                    }
                ],
            )

    @users("employee")
    def test_message_log_batch_with_partners(self):
        test_records = self.test_records.with_env(self.env)
        test_records.message_subscribe(self.partner_employee_2.ids)

        with self.mock_mail_gateway():
            new_notes = test_records._message_log_batch(
                bodies={
                    test_record.id: Markup("<p>Test _message_log_batch</p>")
                    for test_record in test_records
                },
                partner_ids=self.test_partners[:5].ids,
            )
        for test_record, new_note in zip(test_records, new_notes, strict=True):
            self.assertMailNotifications(
                new_note,
                [
                    {
                        "content": "<p>Test _message_log_batch</p>",
                        "message_type": "notification",
                        "message_values": {
                            "author_id": self.partner_employee,
                            "body": "<p>Test _message_log_batch</p>",
                            "email_from": formataddr(
                                (
                                    self.partner_employee.name,
                                    self.partner_employee.email_normalized,
                                )
                            ),
                            "is_internal": True,
                            "model": test_record._name,
                            "notified_partner_ids": self.env["res.partner"],
                            "partner_ids": self.test_partners[:5],
                            "reply_to": formataddr(
                                (
                                    self.partner_employee.name,
                                    f"{self.alias_catchall}@{self.alias_domain}",
                                )
                            ),
                            "res_id": test_record.id,
                        },
                        "notif": [],
                        "subtype": "mail.mt_note",
                    }
                ],
            )

    def _ticket_tracking_commands(self, record, index):
        fields_info = record.fields_get(["email_from", "user_id"])
        Tracking = self.env["mail.tracking.value"]
        return [
            [
                0,
                0,
                Tracking._prepare_tracking_values(
                    f"old.{index}@test.example.com",
                    f"new.{index}@test.example.com",
                    "email_from",
                    fields_info["email_from"],
                    record,
                ),
            ],
            [
                0,
                0,
                Tracking._prepare_tracking_values(
                    self.env["res.users"],
                    self.user_employee_2,
                    "user_id",
                    fields_info["user_id"],
                    record,
                ),
            ],
        ]

    def _logged_message_snapshot(self, message):
        return {
            **{
                fname: message[fname]
                for fname in (
                    "attachment_ids",
                    "author_id",
                    "body",
                    "email_add_signature",
                    "email_from",
                    "is_internal",
                    "message_type",
                    "model",
                    "notification_ids",
                    "notified_partner_ids",
                    "partner_ids",
                    "record_alias_domain_id",
                    "record_company_id",
                    "reply_to",
                    "res_id",
                    "subject",
                    "subtype_id",
                )
            },
            "message_id_kind": "message-notify" in message.message_id,
            "tracking": [
                {key: value for key, value in values.items() if key != "id"}
                for values in message.sudo().tracking_value_ids._tracking_value_format()
            ],
        }

    @users("employee")
    def test_message_log_entries_match_message_log(self):
        record = self.test_records[0].with_env(self.env)
        record.message_subscribe(self.partner_employee_2.ids)
        specs = [
            (
                Markup("<p>Entry %s</p>") % index,
                self._ticket_tracking_commands(record, index),
            )
            for index in range(5)
        ]

        with self.mock_mail_gateway():
            singles = self.env["mail.message"].concat(
                *(
                    record._message_log(body=body, tracking_value_ids=tracking)
                    for body, tracking in specs
                )
            )
            entries = record._message_log_entries(
                [
                    {"res_id": record.id, "body": body, "tracking_value_ids": tracking}
                    for body, tracking in specs
                ]
            )

        self.assertFalse(self._new_mails)
        self.assertEqual(len(entries), len(specs))
        self.assertEqual(entries.ids, sorted(entries.ids))
        self.assertGreater(entries[0].id, singles[-1].id)
        for single, entry in zip(singles, entries, strict=True):
            self.assertEqual(
                self._logged_message_snapshot(entry),
                self._logged_message_snapshot(single),
            )
            self.assertEqual(len(entry.sudo().tracking_value_ids), 2)

    @users("employee")
    def test_message_log_entries_per_entry_values(self):
        records = self.test_records[:2].with_env(self.env)

        messages = records._message_log_entries(
            [
                {"res_id": records[0].id, "body": "first"},
                {
                    "res_id": records[1].id,
                    "body": "second",
                    "author_id": self.partner_employee_2.id,
                },
                {
                    "res_id": records[0].id,
                    "body": "third",
                    "subtype_xmlid": "mail.mt_comment",
                },
            ]
        )

        self.assertEqual(
            [message.res_id for message in messages],
            [records[0].id, records[1].id, records[0].id],
        )
        self.assertEqual(
            [str(message.body) for message in messages],
            ["<p>first</p>", "<p>second</p>", "<p>third</p>"],
        )
        self.assertEqual(
            [message.author_id for message in messages],
            [self.partner_employee, self.partner_employee_2, self.partner_employee],
        )
        self.assertEqual(
            messages[1].email_from, self.partner_employee_2.email_formatted
        )
        self.assertEqual(
            [message.subtype_id for message in messages],
            [
                self.env.ref("mail.mt_note"),
                self.env.ref("mail.mt_note"),
                self.env.ref("mail.mt_comment"),
            ],
        )
        self.assertTrue(all(messages.mapped("is_internal")))
        self.assertFalse(messages.notification_ids)

    @users("employee")
    def test_message_post_entries_post_each_entry_as_message_post_would(self):
        records = self.test_records[:2].with_env(self.env)
        records[0].message_subscribe(
            self.partner_employee_2.ids,
            subtype_ids=self.env.ref("mail.mt_note").ids,
        )
        single = records[0].message_post(body="single")

        with self.capturedQueries() as queries:
            messages = records._message_post_entries(
                [
                    {"res_id": records[0].id, "body": "first"},
                    {"res_id": records[1].id, "body": "second"},
                    {"res_id": records[0].id, "body": "third"},
                ]
            )

        self.assertEqual(
            sum(1 for query in queries if 'INSERT INTO "mail_message"' in query), 2
        )
        self.assertEqual(
            [(message.res_id, str(message.body)) for message in messages],
            [
                (records[0].id, "<p>first</p>"),
                (records[1].id, "<p>second</p>"),
                (records[0].id, "<p>third</p>"),
            ],
        )
        self.assertEqual(messages.subtype_id, single.subtype_id)
        self.assertEqual(set(messages.mapped("message_type")), {single.message_type})
        self.assertEqual(
            [message.notification_ids.res_partner_id for message in messages],
            [
                single.notification_ids.res_partner_id,
                self.env["res.partner"],
                single.notification_ids.res_partner_id,
            ],
        )
        with self.assertRaisesRegex(ValueError, "outside the posted set"):
            records[0]._message_post_entries([{"res_id": records[1].id, "body": "x"}])

    def test_message_log_entries_rejects_malformed_batches(self):
        record, other = self.test_records[:2]
        attachment = self.env["ir.attachment"].create(
            {"name": "log.txt", "raw": b"log", "res_model": record._name}
        )

        self.assertFalse(record._message_log_entries([]))
        with self.assertRaisesRegex(ValueError, "outside the logged set"):
            record._message_log_entries([{"res_id": other.id}])
        with self.assertRaisesRegex(ValueError, "Unsupported log entry keys"):
            record._message_log_entries([{"res_id": record.id, "subject": "x"}])
        with self.assertRaisesRegex(ValueError, "attachments on more than 1"):
            record._message_log_entries(
                [{"res_id": record.id}, {"res_id": record.id}],
                attachment_ids=attachment.ids,
            )

    @users("employee")
    def test_message_log_with_view(self):
        test_records = self.test_records.with_env(self.env)
        test_records.message_subscribe(self.partner_employee_2.ids)

        with self.mock_mail_gateway():
            new_notes = test_records._message_log_with_view(
                "test_mail.mail_template_simple_test",
                render_values={"partner": self.user_employee.partner_id},
            )
        for test_record, new_note in zip(test_records, new_notes, strict=True):
            self.assertMailNotifications(
                new_note,
                [
                    {
                        "content": f"<p>Hello {self.user_employee.name}, this comes from {test_record.name}.</p>",
                        "message_type": "notification",
                        "message_values": {
                            "author_id": self.partner_employee,
                            "body": f"<p>Hello {self.user_employee.name}, this comes from {test_record.name}.</p>",
                            "email_from": formataddr(
                                (
                                    self.partner_employee.name,
                                    self.partner_employee.email_normalized,
                                )
                            ),
                            "is_internal": True,
                            "model": test_record._name,
                            "notified_partner_ids": self.env["res.partner"],
                            "reply_to": formataddr(
                                (
                                    self.partner_employee.name,
                                    f"{self.alias_catchall}@{self.alias_domain}",
                                )
                            ),
                            "res_id": test_record.id,
                        },
                        "notif": [],
                        "subtype": "mail.mt_note",
                    }
                ],
            )


@tagged("mail_post", "post_install", "-at_install")
class TestMessagePost(TestMessagePostCommon, CronMixinCase):
    def test_assert_initial_values(self):
        self.assertFalse(self.test_record.message_ids)
        self.assertFalse(self.test_record.message_follower_ids)
        self.assertFalse(self.test_record.message_partner_ids)

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_manual_send_user_notification_email_from_queue(self):

        with self.mock_mail_gateway():
            new_notification = self.test_record.message_notify(
                subject="This should be a subject",
                body="<p>You have received a notification</p>",
                partner_ids=[self.partner_1.id],
                subtype_xmlid="mail.mt_note",
                force_send=False,
            )

        self.assertNotIn(
            self.user_admin.partner_id,
            new_notification.mail_ids.partner_ids,
            "Our admin user should not be within the partner_ids",
        )

        with self.mock_mail_gateway():
            new_notification.mail_ids.with_user(self.user_admin).send()

        self.assertEqual(len(self._mails), 1, "the email was handed to SMTP")
        self.assertEqual(
            new_notification.mail_ids.state,
            "sent",
            "the mail was delivered, so it is sent; a permission the sender "
            "lacks on someone else's message does not make the delivery untrue, "
            "and must not leave the record queued for a second attempt",
        )
        self.assertFalse(new_notification.mail_ids.failure_type)

    @mute_logger("odoo.addons.mail.models.mail_mail", "odoo.models.unlink")
    @users("employee")
    def test_message_post(self):
        self.user_employee_2.write({"notification_type": "inbox"})
        test_record = self.env["mail.test.simple"].browse(self.test_record.ids)
        additional_to = '"Michel Boitaclous" <michel@boitaclous.fr>'

        with self.assertSinglePostNotifications(
            [
                {"partner": self.partner_employee_2, "type": "inbox"},
            ],
            message_info={
                "content": "Body",
                "message_values": {
                    "author_id": self.partner_employee,
                    "body": "<p>Body</p>",
                    "email_from": formataddr(
                        (
                            self.partner_employee.name,
                            self.partner_employee.email_normalized,
                        )
                    ),
                    "incoming_email_cc": '"Leo Pol" <leo@test.example.com>, fab@test.example.com',
                    "incoming_email_to": '"Gaby Tlair" <gab@test.example.com>, ted@test.example.com',
                    "is_internal": False,
                    "message_type": "comment",
                    "model": test_record._name,
                    "notified_partner_ids": self.partner_employee_2,
                    "reply_to": formataddr(
                        (
                            self.partner_employee.name,
                            f"{self.alias_catchall}@{self.alias_domain}",
                        )
                    ),
                    "res_id": test_record.id,
                    "subtype_id": self.env.ref("mail.mt_comment"),
                },
            },
        ):
            _new_message = test_record.message_post(
                body="Body",
                incoming_email_cc='"Leo Pol" <leo@test.example.com>, fab@test.example.com',
                incoming_email_to='"Gaby Tlair" <gab@test.example.com>, ted@test.example.com',
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                partner_ids=[self.partner_employee_2.id],
            )
        self.assertEqual(test_record.message_partner_ids, self.partner_employee)

        test_record.message_subscribe(self.partner_1.ids)
        exp_headers = {
            "Return-Path": f"{self.alias_bounce}@{self.alias_domain}",
            "X-Custom": "Done",
            "X-Msg-To-Add": f"{additional_to},{self.partner_1.email_formatted}",
            "X-Odoo-Objects": f"{test_record._name}-{test_record.id}",
        }
        with self.assertSinglePostNotifications(
            [
                {"partner": self.partner_employee_2, "type": "inbox"},
                {"partner": self.partner_1, "type": "email"},
                {
                    "email_to": ["michel@boitaclous.fr"],
                    "partner": self.env["res.partner"],
                    "type": "email",
                },
            ],
            message_info={
                "content": "NewBody",
                "mail_mail_values": {
                    "headers": exp_headers,
                },
                "email_values": {
                    "headers": exp_headers,
                },
                "message_values": {
                    "notified_partner_ids": self.partner_1 + self.partner_employee_2,
                    "outgoing_email_to": additional_to,
                },
            },
            mail_unlink_sent=False,
        ):
            _new_message = test_record.message_post(
                body="NewBody",
                message_type="comment",
                outgoing_email_to=additional_to,
                subtype_xmlid="mail.mt_comment",
                partner_ids=[self.partner_employee_2.id],
            )

        with self.assertSinglePostNotifications(
            [
                {"partner": self.partner_1, "type": "email"},
                {"partner": self.partner_portal, "type": "email"},
            ],
            message_info={
                "content": "ToPortal",
            },
            mail_unlink_sent=True,
        ):
            last_message = test_record.message_post(
                body="ToPortal",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                partner_ids=self.partner_portal.ids,
            )
        self.assertFalse(
            self.env["mail.mail"]
            .sudo()
            .search_count([("mail_message_id", "=", last_message.id)])
        )

    @mute_logger(
        "odoo.addons.mail.models.mail_mail", "odoo.models.unlink", "odoo.tests"
    )
    @users("employee")
    def test_message_post_author(self):
        test_record = self.test_record.with_env(self.env)

        with self.assertSinglePostNotifications(
            [{"partner": self.partner_admin, "type": "email"}],
            message_info={
                "content": "Body",
                "mail_mail_values": {
                    "author_id": self.partner_employee_2,
                    "email_from": formataddr(
                        (
                            self.partner_employee_2.name,
                            self.partner_employee_2.email_normalized,
                        )
                    ),
                },
                "message_values": {
                    "author_id": self.partner_employee_2,
                    "email_from": formataddr(
                        (
                            self.partner_employee_2.name,
                            self.partner_employee_2.email_normalized,
                        )
                    ),
                    "message_type": "comment",
                    "notified_partner_ids": self.partner_admin,
                    "subtype_id": self.env.ref("mail.mt_comment"),
                },
            },
        ):
            _new_message = test_record.message_post(
                author_id=self.partner_employee_2.id,
                body="Body",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                partner_ids=[self.partner_admin.id],
            )
        self.assertEqual(
            test_record.message_partner_ids,
            self.partner_employee,
            "Real author is added in followers, not message author",
        )

        test_record.message_unsubscribe(partner_ids=self.partner_employee.ids)
        _new_message = test_record.message_post(
            author_id=self.partner_employee_2.id,
            body="Body",
            message_type="notification",
            subtype_xmlid="mail.mt_comment",
            partner_ids=[self.partner_admin.id],
        )
        self.assertFalse(
            test_record.message_partner_ids,
            "Notification should not add author in followers",
        )

        self.env.user.with_user(self.user_admin).active = False
        _new_message = test_record.message_post(
            author_id=self.partner_employee_2.id,
            body="Body",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            partner_ids=[self.partner_admin.id],
        )
        self.assertEqual(
            test_record.message_partner_ids,
            self.partner_employee_2,
            "Author is the message author when user is inactive, and shoud be added in followers",
        )

    @mute_logger(
        "odoo.addons.mail.models.mail_mail", "odoo.models.unlink", "odoo.tests"
    )
    @users("employee")
    def test_message_post_defaults(self):
        _original_compute_subject = MailTestSimple._message_compute_subject
        _original_notify_headers = MailTestSimple._notify_by_email_get_headers
        _original_notify_mailvals = (
            MailTestSimple._notify_by_email_get_final_mail_values
        )
        test_record = self.env["mail.test.simple"].create([{"name": "Defaults"}])
        creation_msg = test_record.message_ids
        self.assertEqual(len(creation_msg), 1)

        with (
            patch.object(
                MailTestSimple,
                "_message_compute_subject",
                autospec=True,
                side_effect=_original_compute_subject,
            ) as mock_compute_subject,
            patch.object(
                MailTestSimple,
                "_notify_by_email_get_headers",
                autospec=True,
                side_effect=_original_notify_headers,
            ) as mock_notify_headers,
            patch.object(
                MailTestSimple,
                "_notify_by_email_get_final_mail_values",
                autospec=True,
                side_effect=_original_notify_mailvals,
            ) as mock_notify_mailvals,
            self.mock_mail_gateway(),
            self.mock_mail_app(),
        ):
            new_message = test_record.message_post(
                body="Body",
                partner_ids=[self.partner_employee_2.id],
            )

        self.assertEqual(
            mock_compute_subject.call_count,
            1,
            "Should call model-based subject computation for outgoing emails",
        )
        self.assertEqual(
            mock_notify_headers.call_count,
            1,
            "Should call model-based headers computation for outgoing emails",
        )
        self.assertEqual(
            mock_notify_mailvals.call_count,
            1,
            "Should call model-based headers computation for outgoing emails",
        )
        self.assertMailNotifications(
            new_message,
            [
                {
                    "content": "<p>Body</p>",
                    "message_type": "notification",
                    "message_values": {
                        "author_id": self.partner_employee,
                        "body": "<p>Body</p>",
                        "email_from": formataddr(
                            (
                                self.partner_employee.name,
                                self.partner_employee.email_normalized,
                            )
                        ),
                        "is_internal": False,
                        "model": test_record._name,
                        "notified_partner_ids": self.partner_employee_2,
                        "parent_id": creation_msg,
                        "reply_to": formataddr(
                            (
                                self.partner_employee.name,
                                f"{self.alias_catchall}@{self.alias_domain}",
                            )
                        ),
                        "res_id": test_record.id,
                        "subject": test_record.name,
                    },
                    "notif": [
                        {
                            "partner": self.partner_employee_2,
                            "type": "email",
                        },
                    ],
                    "subtype": "mail.mt_note",
                }
            ],
        )

    @users("employee")
    @mute_logger("odoo.models.unlink")
    def test_message_post_inactive_follower(self):
        test_record = self.env["mail.test.simple"].browse(self.test_record.ids)
        test_record._message_subscribe(self.user_employee_2.partner_id.ids)
        self.user_employee_2.write({"active": False})
        self.partner_employee_2.write({"active": False})

        with self.assertPostNotifications([{"content": "Test", "notif": []}]):
            test_record.message_post(
                body="Test",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    @users("employee")
    def test_message_post_keep_emails(self):
        test_record = self.env["mail.test.simple"].browse(self.test_record.ids)
        test_record.message_subscribe(partner_ids=self.partner_employee_2.ids)

        with self.mock_mail_gateway(mail_unlink_sent=True):
            msg = test_record.message_post(
                body="Test",
                mail_auto_delete=False,
                message_type="comment",
                partner_ids=[self.partner_1.id, self.partner_2.id],
                subject="Test",
                subtype_xmlid="mail.mt_comment",
            )

        self.assertEqual(
            self.env["mail.mail"]
            .sudo()
            .search_count([("mail_message_id", "=", msg.id)]),
            2,
        )

    @mute_logger("odoo.addons.mail.models.mail_mail", "odoo.models.unlink")
    @users("erp_manager")
    def test_message_post_mc(self):
        records = self.env["mail.test.ticket.mc"].create(
            [
                {
                    "name": "No Specific Company",
                },
                {
                    "company_id": self.company_admin.id,
                    "name": "Company1",
                },
                {
                    "company_id": self.company_2.id,
                    "name": "Company2",
                },
            ]
        )
        expected_companies = [self.company_2, self.company_admin, self.company_2]
        expected_alias_domains = [
            self.mail_alias_domain_c2,
            self.mail_alias_domain,
            self.mail_alias_domain_c2,
        ]
        for record, expected_company, expected_alias_domain in zip(
            records, expected_companies, expected_alias_domains, strict=True
        ):
            with self.subTest(record=record):
                with self.assertSinglePostNotifications(
                    [{"partner": self.partner_employee_2, "type": "email"}],
                    message_info={
                        "content": "Body",
                        "email_values": {
                            "headers": {
                                "Return-Path": f"{expected_alias_domain.bounce_alias}@{expected_alias_domain.name}",
                            },
                        },
                        "mail_mail_values": {
                            "headers": {
                                "Return-Path": f"{expected_alias_domain.bounce_alias}@{expected_alias_domain.name}",
                                "X-Odoo-Objects": f"{record._name}-{record.id}",
                            },
                        },
                        "message_values": {
                            "author_id": self.user_erp_manager.partner_id,
                            "email_from": formataddr(
                                (
                                    self.user_erp_manager.name,
                                    self.user_erp_manager.email_normalized,
                                )
                            ),
                            "is_internal": False,
                            "notified_partner_ids": self.partner_employee_2,
                            "record_company_id": expected_company,
                            "reply_to": formataddr(
                                (
                                    self.user_erp_manager.name,
                                    f"{expected_alias_domain.catchall_alias}@{expected_alias_domain.name}",
                                )
                            ),
                        },
                    },
                ):
                    _new_message = record.message_post(
                        body="Body",
                        message_type="comment",
                        subtype_xmlid="mail.mt_comment",
                        partner_ids=[self.partner_employee_2.id],
                    )

    @mute_logger("odoo.addons.mail.models.mail_mail", "odoo.tests")
    def test_message_post_recipients_email_field(self):
        partner_emails = [
            "valid.lelitre@agrolait.com, valid.lelitre.cc@agrolait.com",
            '"Valid Lelitre" <valid.lelitre@agrolait.com>',
            "wrong",
            False,
            "",
            " ",
        ]
        expected_tos = [
            [
                f'"{self.partner_1.name}" <valid.lelitre@agrolait.com>',
                f'"{self.partner_1.name}" <valid.lelitre.cc@agrolait.com>',
            ],
            [
                f'"{self.partner_1.name}" <valid.lelitre@agrolait.com>',
            ],
            ["wrong"],
            [],
            [],
            [],
        ]

        for partner_email, expected_to in zip(
            partner_emails, expected_tos, strict=True
        ):
            with self.subTest(partner_email=partner_email, expected_to=expected_to):
                self.partner_1.write({"email": partner_email})
                with self.mock_mail_gateway():
                    self.test_record.with_user(self.user_employee).message_post(
                        body="Test multi email",
                        message_type="comment",
                        partner_ids=[self.partner_1.id],
                        subject="Exotic email",
                        subtype_xmlid="mt_comment",
                    )

                self.assertSentEmail(
                    self.user_employee.partner_id,
                    [self.partner_1],
                    email_to=expected_to,
                )

    @users("employee")
    def test_message_post_recipients_to_email_address(self):
        test_record = self.test_record.with_env(self.env)
        email_to_lst = [
            '"Dade" <das.deboulonneur@fleurus.example.com>',
            '"Dide" <die.deboulonneur@fleurus.example.com>',
        ]
        email_to_normalized_lst = [
            "das.deboulonneur@fleurus.example.com",
            "die.deboulonneur@fleurus.example.com",
        ]
        self.assertFalse(
            self.env["res.partner"].search(
                [("email_normalized", "in", email_to_normalized_lst)]
            )
        )

        for partner_ids, exp_partner_mail in [
            (self.partner_1.ids, self.partner_1),
            ([], self.env["res.partner"]),
        ]:
            with self.subTest(partner_ids=partner_ids):
                with self.mock_mail_gateway():
                    test_record.message_post(
                        body="Test with email recipients",
                        message_type="comment",
                        partner_ids=partner_ids,
                        outgoing_email_to=",".join(email_to_lst),
                        subject="Email recipients",
                        subtype_xmlid="mt_comment",
                    )
                for partner in exp_partner_mail:
                    self.assertMailMail(
                        partner,
                        "sent",
                        author=self.partner_employee,
                    )
                self.assertMailMail(
                    self.env["res.partner"],
                    "sent",
                    author=self.partner_employee,
                    email_to_all=email_to_normalized_lst,
                )

    @users("employee")
    @mute_logger(
        "odoo.addons.mail.models.mail_mail",
        "odoo.addons.mail.models.mail_message_schedule",
        "odoo.models.unlink",
    )
    def test_message_post_schedule(self):
        cron_id = self.env.ref("mail.ir_cron_send_scheduled_message").id
        now = datetime.now(UTC).replace(tzinfo=None, second=0, microsecond=0)
        scheduled_datetime = now + timedelta(days=5)
        self.user_admin.write({"notification_type": "inbox"})

        test_records = self.test_records_simple.with_env(self.env)
        test_records.message_subscribe((self.partner_1 | self.partner_admin).ids)

        deleted_record = test_records[2]
        remaining_records = test_records - deleted_record

        messages = self.env["mail.message"]
        with (
            self.mock_datetime_and_now(now),
            self.assertMsgWithoutNotifications(),
            self.capture_triggers(cron_id) as capt,
        ):
            for test_record in test_records:
                messages += test_record.message_post(
                    body=f"<p>Test on {test_record.name}</p>",
                    message_type="comment",
                    subject=f"Subject for {test_record.name}",
                    subtype_xmlid="mail.mt_comment",
                    scheduled_date=scheduled_datetime,
                )
        self.assertEqual(
            capt.records.mapped("call_at"),
            [scheduled_datetime] * 3,
            msg="Should have created a cron trigger / scheduled post",
        )
        self.assertFalse(self._new_mails)
        self.assertFalse(self._mails)

        schedules = (
            self.env["mail.message.schedule"]
            .sudo()
            .search([("mail_message_id", "in", messages.ids)])
        )
        self.assertEqual(
            len(schedules), 3, msg="Should have one scheduled record / message to post"
        )
        self.assertEqual(
            schedules.mapped("scheduled_datetime"), [scheduled_datetime] * 3
        )

        with self.mock_datetime_and_now(now):
            self.env["mail.message.schedule"].sudo()._send_notifications_cron()
        self.assertTrue(schedules.exists(), msg="Should not have sent the messages")

        test_record_names = test_records.mapped("name")
        self.env.cr.execute(
            f"DELETE FROM {test_records._table} WHERE id = %s", (deleted_record.id,)
        )
        test_records.invalidate_recordset()

        with (
            self.mock_datetime_and_now(now + timedelta(days=5)),
            self.mock_mail_gateway(mail_unlink_sent=True),
        ):
            self.env["mail.message.schedule"].sudo()._send_notifications_cron()
        self.assertFalse(schedules.exists(), msg="Should have sent the messages")

        for msg, test_record, test_record_name in zip(
            messages, test_records, test_record_names, strict=True
        ):
            with self.subTest(test_record_name=test_record_name):
                if test_record != deleted_record:
                    self.assertMailNotifications(
                        msg,
                        [
                            {
                                "content": f"Test on {test_record_name}",
                                "email_values": {
                                    "subject": f"Subject for {test_record_name}",
                                },
                                "notif": [
                                    {"partner": self.partner_admin, "type": "inbox"},
                                    {"partner": self.partner_1, "type": "email"},
                                ],
                            }
                        ],
                    )
        self.assertEqual(
            len(self._new_mails),
            len(remaining_records),
            "Should have skipped unlinked record",
        )

        self.env["mail.message.schedule"].sudo().create(
            {
                "mail_message_id": msg.id,
                "scheduled_datetime": scheduled_datetime,
            }
        )

        with (
            self.mock_datetime_and_now(now + timedelta(days=5)),
            self.assertNoNotifications(),
        ):
            self.env["mail.message.schedule"].sudo()._send_notifications_cron()

        with (
            self.mock_datetime_and_now(now),
            self.mock_mail_gateway(mail_unlink_sent=False),
            self.capture_triggers(cron_id) as capt,
        ):
            msg = test_records[0].message_post(
                body=Markup("<p>Test</p>"),
                message_type="comment",
                subject="Subject",
                subtype_xmlid="mail.mt_comment",
                scheduled_date=now,
            )
        self.assertFalse(capt.records)
        recipients_info = [
            {
                "content": "<p>Test</p>",
                "notif": [
                    {"partner": self.partner_admin, "type": "inbox"},
                    {"partner": self.partner_1, "type": "email"},
                ],
            }
        ]
        self.assertMailNotifications(msg, recipients_info)

    @users("employee")
    @mute_logger(
        "odoo.addons.mail.models.mail_mail",
        "odoo.addons.mail.models.mail_message_schedule",
        "odoo.models.unlink",
    )
    def test_message_post_schedule_update(self):
        cron = self.env.ref("mail.ir_cron_send_scheduled_message")
        now = datetime.now(UTC).replace(tzinfo=None, second=0, microsecond=0)
        scheduled_datetime = now + timedelta(days=5)
        self.user_admin.write({"notification_type": "inbox"})

        test_record = self.test_record.with_env(self.env)
        test_record.message_subscribe((self.partner_1 | self.partner_admin).ids)

        with freeze_time(now), self.assertMsgWithoutNotifications():
            msg = test_record.message_post(
                body=Markup("<p>Test</p>"),
                message_type="comment",
                subject="Subject",
                subtype_xmlid="mail.mt_comment",
                scheduled_date=scheduled_datetime,
            )
        schedules = (
            self.env["mail.message.schedule"]
            .sudo()
            .search([("mail_message_id", "=", msg.id)])
        )
        self.assertEqual(len(schedules), 1, msg="Should have scheduled the message")

        with (
            freeze_time(now),
            self.assertNoNotifications(),
            self.capture_triggers(cron.id) as capt,
        ):
            self.env["mail.message.schedule"].sudo()._update_message_scheduled_datetime(
                msg, now - timedelta(hours=1)
            )
        self.assertEqual(
            capt.records.call_at,
            now - timedelta(hours=1),
            msg="Should have created a new cron trigger for the new scheduled sending",
        )
        self.assertTrue(schedules.exists(), msg="Should not have sent the message")

        with freeze_time(now), self.mock_mail_gateway(mail_unlink_sent=False):
            schedules._send_notifications_cron()
        self.assertFalse(schedules.exists(), msg="Should have sent the message")
        recipients_info = [
            {
                "content": "<p>Test</p>",
                "notif": [
                    {"partner": self.partner_admin, "type": "inbox"},
                    {"partner": self.partner_1, "type": "email"},
                ],
            }
        ]
        self.assertMailNotifications(msg, recipients_info)

        self.assertFalse(
            self.env["mail.message.schedule"]
            .sudo()
            ._update_message_scheduled_datetime(msg, now - timedelta(hours=1)),
            "Mail scheduler: should return False when no schedule is found",
        )

    @mute_logger("odoo.addons.mail.models.mail_message_schedule")
    def test_message_schedule_cron_isolates_failures(self):
        Schedule = self.env["mail.message.schedule"].sudo()
        test_records = self.test_records_simple.with_env(self.env)
        test_records.message_subscribe((self.partner_1 | self.partner_admin).ids)
        good_msg = test_records[0].message_post(
            body="<p>good</p>", message_type="comment", subtype_xmlid="mail.mt_comment"
        )
        bad_msg = test_records[1].message_post(
            body="<p>bad</p>", message_type="comment", subtype_xmlid="mail.mt_comment"
        )
        past = datetime(2020, 1, 1, 0, 0, 0)
        Schedule.create(
            [
                {"mail_message_id": good_msg.id, "scheduled_datetime": past},
                {"mail_message_id": bad_msg.id, "scheduled_datetime": past},
            ]
        )

        record_cls = type(self.env["mail.test.simple"])
        origin = record_cls._notify_thread

        def _notify_thread(self, message, *args, **kwargs):
            if message.id == bad_msg.id:
                raise ValueError("boom")
            return origin(self, message, *args, **kwargs)

        with patch.object(record_cls, "_notify_thread", _notify_thread):
            Schedule._send_notifications_cron()

        self.assertFalse(
            Schedule.search([("mail_message_id", "in", (good_msg + bad_msg).ids)]),
            "both schedules consumed: the healthy one sent, the poison one dropped",
        )

    @mute_logger("odoo.addons.mail.models.mail_message_schedule")
    def test_message_schedule_cron_batches(self):
        cron = self.env.ref("mail.ir_cron_send_scheduled_message")
        Schedule = self.env["mail.message.schedule"].sudo()
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.scheduled_notification.batch.size", 1
        )
        test_records = self.test_records_simple.with_env(self.env)
        test_records.message_subscribe((self.partner_1 | self.partner_admin).ids)
        past = datetime(2020, 1, 1, 0, 0, 0)
        for test_record in test_records[:2]:
            msg = test_record.message_post(
                body="<p>batch</p>",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            Schedule.create({"mail_message_id": msg.id, "scheduled_datetime": past})

        remaining_before = Schedule.search_count([("scheduled_datetime", "<=", past)])
        self.assertEqual(remaining_before, 2)
        with self.capture_triggers(cron.id) as capt:
            Schedule._send_notifications_cron()
        self.assertEqual(Schedule.search_count([("scheduled_datetime", "<=", past)]), 1)
        self.assertTrue(capt.records, "a follow-up cron trigger must be created")

    @mute_logger(
        "odoo.addons.mail.models.mail_mail",
        "odoo.addons.mail.models.mail_message_schedule",
    )
    def test_message_post_w_attachments_filtering(self):
        xml_attachment, octet_attachment, pdf_attachment = (
            [("List1", b'<?xml version="1.0" ?><xml>My xml attachment</xml>')],
            [("List2", b"\x00\x01My octet-stream attachment\x03\x04")],
            [("List3", b"%PDF My pdf attachment")],
        )

        xml_attachment_data, octet_attachment_data, pdf_attachment_data = self.env[
            "ir.attachment"
        ].create(self._generate_attachments_data(3, "wizard.mail.message.send", 0))
        xml_attachment_data.write({"mimetype": "application/xml"})
        octet_attachment_data.write({"mimetype": "application/octet-stream"})
        pdf_attachment_data.write({"mimetype": "application/pdf"})

        test_record = (
            self.env["mail.test.simple.main.attachment"]
            .with_context(self._test_context)
            .create(
                {
                    "name": "Test",
                    "email_from": "ignasse@example.com",
                }
            )
        )
        self.assertFalse(test_record.message_main_attachment_id)

        with self.mock_mail_gateway():
            test_record.message_post(
                attachments=xml_attachment,
                attachment_ids=xml_attachment_data.ids,
                body="Post XML",
                message_type="comment",
                partner_ids=[self.partner_1.id],
                subject="Test",
                subtype_xmlid="mail.mt_comment",
            )
        self.assertFalse(
            test_record.message_main_attachment_id,
            "MixinMailThread: main attachment should not be set with an XML",
        )

        with self.mock_mail_gateway():
            test_record.message_post(
                attachments=octet_attachment,
                attachment_ids=octet_attachment_data.ids,
                body="Post Octet-Stream",
                message_type="comment",
                partner_ids=[self.partner_1.id],
                subject="Test",
                subtype_xmlid="mail.mt_comment",
            )
        self.assertFalse(
            test_record.message_main_attachment_id,
            "MixinMailThread: main attachment should not be set with an Octet-Stream",
        )
        with self.mock_mail_gateway():
            test_record.message_post(
                attachments=pdf_attachment,
                attachment_ids=pdf_attachment_data.ids,
                body="Post PDF",
                message_type="comment",
                partner_ids=[self.partner_1.id],
                subject="Test",
                subtype_xmlid="mail.mt_comment",
            )
        self.assertEqual(
            test_record.message_main_attachment_id,
            pdf_attachment_data,
            "MixinMailThread: main attachment should be set to application/pdf",
        )

    @mute_logger(
        "odoo.addons.mail.models.mail_mail",
        "odoo.addons.mail.models.mail_message_schedule",
    )
    def test_message_post_original_email_is_never_the_main_attachment(self):
        eml_attachment, pdf_attachment = self.env["ir.attachment"].create(
            self._generate_attachments_data(2, "wizard.mail.message.send", 0)
        )
        eml_attachment.write(
            {"mimetype": "message/rfc822", "name": "original_email.eml"}
        )
        pdf_attachment.write({"mimetype": "application/pdf"})
        test_record = (
            self.env["mail.test.simple.main.attachment"]
            .with_context(self._test_context)
            .create({"name": "Test", "email_from": "ignasse@example.com"})
        )
        with self.mock_mail_gateway():
            test_record.message_post(
                attachment_ids=eml_attachment.ids,
                body="Incoming mail kept as original",
                message_type="comment",
            )
        self.assertFalse(test_record.message_main_attachment_id)
        with self.mock_mail_gateway():
            test_record.message_post(
                attachment_ids=pdf_attachment.ids,
                body="Extracted PDF",
                message_type="comment",
            )
        self.assertEqual(test_record.message_main_attachment_id, pdf_attachment)

    @users("employee")
    @mute_logger(
        "odoo.addons.mail.models.mail_mail",
        "odoo.addons.mail.models.mail_message_schedule",
    )
    def test_message_post_w_attachments_on_main_attachment_model(self):
        _attachments = [
            ("List1", b"My first attachment"),
            ("List2", b"My second attachment"),
        ]
        _attachment_records = self.env["ir.attachment"].create(
            self._generate_attachments_data(3, "wizard.mail.message.send", 0)
        )
        _attachment_records[1].write(
            {"mimetype": "image/png"}
        )

        test_record = (
            self.env["mail.test.simple.main.attachment"]
            .with_context(self._test_context)
            .create(
                {
                    "name": "Test",
                    "email_from": "ignasse@example.com",
                }
            )
        )
        self._reset_mail_context(test_record)
        self.test_message.model = test_record._name
        self.assertFalse(test_record.message_main_attachment_id)

        with self.mock_mail_gateway():
            msg = test_record.message_post(
                attachments=_attachments,
                attachment_ids=_attachment_records.ids,
                body="Test",
                message_type="comment",
                partner_ids=[self.partner_1.id],
                subject="Test",
                subtype_xmlid="mail.mt_comment",
            )

        self.assertEqual(
            test_record.message_main_attachment_id,
            _attachment_records[1],
            "MixinMailThread: main attachment should be set to image/png",
        )

        self.assertEqual(len(msg.attachment_ids), 5)
        self.assertEqual(
            set(msg.attachment_ids.mapped("res_model")), {test_record._name}
        )
        self.assertEqual(set(msg.attachment_ids.mapped("res_id")), {test_record.id})
        self.assertEqual(
            {base64.b64decode(x) for x in msg.attachment_ids.mapped("datas")},
            {
                b"AttContent_00",
                b"AttContent_01",
                b"AttContent_02",
                _attachments[0][1],
                _attachments[1][1],
            },
        )
        self.assertTrue(
            set(_attachment_records.ids).issubset(msg.attachment_ids.ids),
            "message_post: mail.message attachments duplicated",
        )

        self.assertEqual(len(self._mails), 1)
        self.assertSentEmail(
            self.user_employee.partner_id,
            [self.partner_1],
            attachments=[
                ("List1", b"My first attachment", "text/plain"),
                ("List2", b"My second attachment", "text/plain"),
                ("AttFileName_00.txt", b"AttContent_00", "text/plain"),
                ("AttFileName_01.txt", b"AttContent_01", "image/png"),
                ("AttFileName_02.txt", b"AttContent_02", "text/plain"),
            ],
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_multiline_subject(self):
        with self.mock_mail_gateway():
            msg = self.test_record.with_user(self.user_employee).message_post(
                body="<p>Test Body</p>",
                partner_ids=[self.partner_1.id, self.partner_2.id],
                subject="1st line\n2nd line",
            )
        self.assertEqual(msg.subject, "1st line 2nd line")

    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.mail.models.mail_mail"
    )
    def test_portal_acls(self):
        self.test_record.message_subscribe(
            (self.partner_1 | self.user_employee.partner_id).ids
        )

        with (
            self.assertPostNotifications(
                [
                    {
                        "content": "<p>Test</p>",
                        "notif": [
                            {"partner": self.partner_employee, "type": "inbox"},
                            {"partner": self.partner_1, "type": "email"},
                        ],
                    }
                ]
            ),
            patch.object(MailTestSimple, "_check_access", return_value=None),
        ):
            new_msg = self.test_record.with_user(self.user_portal).message_post(
                body=Markup("<p>Test</p>"),
                message_type="comment",
                subject="Subject",
                subtype_xmlid="mail.mt_comment",
            )
        self.assertEqual(
            new_msg.sudo().notified_partner_ids,
            (self.partner_1 | self.user_employee.partner_id),
        )

        with self.assertRaises(AccessError):
            self.test_record.with_user(self.user_portal).message_post(
                body=Markup("<p>Test</p>"),
                message_type="comment",
                subject="Subject",
                subtype_xmlid="mail.mt_comment",
            )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    @users("employee")
    def test_post_answer(self):
        for subtype in (
            self.env.ref(
                "test_mail.st_mail_test_ticket_container_mc_upd"
            ),
            self.env.ref("mail.mt_note"),
            self.env[
                "mail.message.subtype"
            ],
            self.env.ref(
                "mail.mt_comment"
            ),
        ):
            with self.subTest(subtype_name=subtype.name if subtype else "None"):
                test_record = self.test_record_ticket.with_env(self.env).copy()
                self.assertEqual(len(test_record.message_ids), 1)
                initial_msg = test_record.message_ids
                self.assertEqual(
                    initial_msg.reply_to,
                    formataddr(
                        (
                            f"{self.user_employee.name}",
                            f"{self.alias_catchall}@{self.alias_domain}",
                        )
                    ),
                )
                self.assertEqual(
                    initial_msg.subtype_id,
                    self.env.ref("test_mail.st_mail_test_ticket_container_mc_upd"),
                )
                initial_msg.sudo().write({"subtype_id": subtype.id})

                with self.mock_mail_gateway():
                    log_msg = test_record._message_log(
                        body=Markup("<p>Blabla fake tracking</p>"),
                        message_type="notification",
                    )
                self.assertFalse(
                    log_msg.parent_id,
                    "FIXME: logs have no parent, strange but funny (somehow)",
                )
                self.assertNotSentEmail()

                with self.mock_mail_gateway():
                    internal_msg = test_record.message_post(
                        body=Markup("<p>Blabla internal</p>"),
                        message_type="notification",
                        subtype_id=self.env.ref(
                            "test_mail.st_mail_test_ticket_internal"
                        ).id,
                        partner_ids=self.user_admin.partner_id.ids,
                    )
                self.assertEqual(
                    internal_msg.parent_id,
                    log_msg,
                    "No email/comment, attached to last message",
                )
                if subtype:
                    references = f"{initial_msg.message_id} {log_msg.message_id} {internal_msg.message_id}"
                else:
                    references = f"{log_msg.message_id} {internal_msg.message_id}"
                self.assertSentEmail(
                    self.user_employee.partner_id,
                    [self.user_admin.partner_id],
                    body_content=Markup("<p>Blabla internal</p>"),
                    reply_to=initial_msg.reply_to,
                    subject=f"Ticket for {test_record.name} on {test_record.datetime.strftime('%m/%d/%Y, %H:%M:%S')}",
                    references=references,
                )

                with self.assertPostNotifications(
                    [
                        {
                            "content": "<p>Test Answer</p>",
                            "notif": [{"partner": self.partner_1, "type": "email"}],
                        }
                    ]
                ):
                    msg = test_record.message_post(
                        body=Markup("<p>Test Answer</p>"),
                        message_type="comment",
                        partner_ids=[self.partner_1.id],
                        subject="Welcome",
                        subtype_xmlid="mail.mt_comment",
                    )
                self.assertEqual(
                    msg.parent_id,
                    internal_msg,
                    "No email/comment, attached to last message",
                )
                self.assertEqual(msg.partner_ids, self.partner_1)
                self.assertFalse(initial_msg.partner_ids)
                if subtype:
                    references = f"{initial_msg.message_id} {log_msg.message_id} {internal_msg.message_id} {msg.message_id}"
                else:
                    references = f"{log_msg.message_id} {internal_msg.message_id} {msg.message_id}"
                self.assertSentEmail(
                    self.user_employee.partner_id,
                    [self.partner_1],
                    references=references,
                )

                if subtype in [
                    self.env.ref("test_mail.st_mail_test_ticket_container_mc_upd"),
                    self.env.ref("mail.mt_comment"),
                ]:
                    top_msg = initial_msg
                else:
                    top_msg = log_msg
                with self.mock_mail_gateway():
                    new_msg = test_record.message_post(
                        body=Markup("<p>Test Answer Bis</p>"),
                        message_type="comment",
                        parent_id=msg.id,
                        subtype_xmlid="mail.mt_comment",
                        partner_ids=[self.partner_2.id],
                    )
                self.assertEqual(new_msg.parent_id, msg)
                self.assertEqual(new_msg.partner_ids, self.partner_2)
                self.assertSentEmail(
                    self.user_employee.partner_id,
                    [self.partner_2],
                    body_content="<p>Test Answer Bis</p>",
                    reply_to=msg.reply_to,
                    subject=f"Ticket for {test_record.name} on {test_record.datetime.strftime('%m/%d/%Y, %H:%M:%S')}",
                    references=f"{top_msg.message_id} {internal_msg.message_id} {msg.message_id} {new_msg.message_id}",
                )

    @users("employee")
    def test_message_post_batch_with_an_email_from_and_no_author(self):
        records = self.env["mail.test.simple"].create([{"name": "S1"}, {"name": "S2"}])
        email_from = '"Unknown Sender" <unknown.sender@test.example.com>'

        messages = records._message_post_batch(
            {record.id: Markup("<p>Body</p>") for record in records},
            email_from=email_from,
            subtype_id=self.env.ref("mail.mt_note").id,
        )

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages.mapped("email_from"), [email_from, email_from])
        self.assertFalse(messages.author_id, "no partner holds that address")

    @users("employee")
    def test_message_post_values_have_the_same_keys_batched_or_not(self):
        record = self.test_record.with_env(self.env)
        common = {
            "message_type": "comment",
            "subject": "Same keys",
            "subtype_id": self.env.ref("mail.mt_comment").id,
            "author_id": self.partner_employee.id,
            "email_from": self.partner_employee.email_formatted,
        }
        single = record._message_post_values(
            Markup("<p>Body</p>"),
            {},
            author_guest_id=False,
            parent_id=False,
            partner_ids=[],
            outgoing_email_to=False,
            incoming_email_to=False,
            incoming_email_cc=False,
            attachments=None,
            attachment_ids=[],
            **common,
        )
        [batched] = record._message_post_batch_values(
            {record.id: Markup("<p>Body</p>")},
            {},
            subtype_ids={},
            authors={},
            tracking_values={},
            **common,
        )
        self.assertEqual(set(single), set(batched))
        self.assertFalse(single["tracking_value_ids"])
        self.assertFalse(batched["tracking_value_ids"])
        self.assertEqual(batched["partner_ids"], [])
        self.assertEqual(batched["attachment_ids"], [])

    @users("employee")
    def test_attachments_format_is_checked_the_same_for_post_and_notify(self):
        record = self.test_record.with_env(self.env)
        mixed = [("first.txt", b"first"), ["second.txt", b"second", {}]]
        message = record.message_post(body="Mixed", attachments=mixed)
        self.assertEqual(len(message.attachment_ids), 2)
        notification = record.message_notify(
            body="Mixed",
            partner_ids=self.partner_employee_2.ids,
            attachments=mixed,
        )
        self.assertEqual(len(notification.attachment_ids), 2)

        for post in (
            lambda attachments: record.message_post(
                body="Bad", attachments=attachments
            ),
            lambda attachments: record.message_notify(
                body="Bad",
                partner_ids=self.partner_employee_2.ids,
                attachments=attachments,
            ),
        ):
            with self.assertRaises(ValueError):
                post([("name-only.txt",)])
            with self.assertRaises(ValueError):
                post(["not-a-pair"])

    @users("employee")
    def test_an_unknown_notify_parameter_leaves_nothing_behind(self):
        record = self.env["mail.test.simple"].create({"name": "Typo"})
        record.message_unsubscribe(partner_ids=record.message_partner_ids.ids)
        messages_before = record.message_ids
        for post in (
            lambda: record.message_post(
                body="Lost", partner_ids=self.partner_employee_2.ids, force_sned=True
            ),
            lambda: record._message_post_batch({record.id: "Lost"}, force_sned=True),
            lambda: record.message_notify(
                body="Lost", partner_ids=self.partner_employee_2.ids, force_sned=True
            ),
        ):
            try:
                post()
            except ValueError:
                pass
            else:
                self.fail("an unknown parameter must be refused")
            self.assertEqual(record.message_ids, messages_before)
            self.assertFalse(record.message_partner_ids)

    @users("employee")
    def test_message_post_batch_can_be_scheduled(self):
        records = self.env["mail.test.simple"].create([{"name": "S1"}, {"name": "S2"}])
        records.message_subscribe(partner_ids=self.partner_1.ids)
        self.env.flush_all()
        when = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")

        records._message_post_batch(
            {record.id: "body" for record in records},
            subtype_id=self.env.ref("mail.mt_comment").id,
            message_type="comment",
            scheduled_date=when,
        )
        self.env.flush_all()

        schedules = (
            self.env["mail.message.schedule"]
            .sudo()
            .search([("mail_message_id.model", "=", records._name)])
        )
        self.assertEqual(len(schedules), 2, "both posts were queued")
        for schedule in schedules:
            params = json_loads(schedule.notification_parameters)
            self.assertNotIn("follower_data", params)
            self.assertNotIn("email_collector", params)
            self.assertNotIn("email_prefetch", params)

    @mute_logger(
        "odoo.addons.mail.models.mail_mail",
        "odoo.addons.mail.models.mixin_mail_thread",
        "odoo.addons.mail.models.mixin_mail_gateway",
    )
    @users("employee")
    def test_author_is_subscribed_the_same_batched_or_not(self):
        subtypes = {
            "comment": self.env.ref("mail.mt_comment"),
            "note": self.env.ref("mail.mt_note"),
        }
        author = self.env.user.partner_id
        Model = (
            self.env["mail.test.simple"]
            .with_context(
                mail_create_nosubscribe=True,
                mail_create_nolog=True,
                mail_post_autofollow_author_skip=False,
            )
            .sudo(False)
        )

        def followers_after(tag, batched, subtype, message_type):
            records = Model.create(
                [{"name": f"{tag} {idx}"} for idx in range(2)],
            )
            self.assertFalse(records.message_partner_ids, "precondition: unfollowed")
            if batched:
                records._message_post_batch(
                    {record.id: Markup("<p>Body</p>") for record in records},
                    message_type=message_type,
                    subtype_ids={record.id: subtype.id for record in records},
                )
            else:
                for record in records:
                    record.message_post(
                        body=Markup("<p>Body</p>"),
                        message_type=message_type,
                        subtype_id=subtype.id,
                    )
            self.env.flush_all()
            return [record.message_partner_ids for record in records]

        cases = [
            ("comment", subtypes["comment"], "comment"),
            ("note", subtypes["note"], "comment"),
            ("notification", subtypes["comment"], "notification"),
            ("auto_comment", subtypes["comment"], "auto_comment"),
        ]
        for label, subtype, message_type in cases:
            with self.subTest(case=label):
                looped = followers_after(f"L{label}", False, subtype, message_type)
                batched = followers_after(f"B{label}", True, subtype, message_type)
                self.assertEqual(
                    [followers.ids for followers in batched],
                    [followers.ids for followers in looped],
                    "the batch disagrees with message_post on who follows the "
                    "record after a %s/%s post" % (message_type, subtype.name),
                )

        looped = followers_after("NV", False, subtypes["comment"], "comment")
        self.assertEqual(
            [followers.ids for followers in looped],
            [author.ids, author.ids],
            "message_post no longer subscribes a comment's author, so every "
            "comparison above passed while comparing nothing",
        )

    @mute_logger(
        "odoo.addons.mail.models.mail_mail",
        "odoo.addons.mail.models.mixin_mail_thread",
        "odoo.addons.mail.models.mixin_mail_gateway",
    )
    @users("employee")
    def test_references_are_the_same_batched_or_not(self):
        limit = self.env["mail.test.simple"]._REFERENCES_ANCESTORS_LIMIT
        depths = [0, 1, 2, limit - 1, limit, limit + 1]
        records = self.env["mail.test.simple"].create(
            [{"name": f"Thread {depth}"} for depth in depths]
        )
        for record, depth in zip(records, depths, strict=True):
            for idx in range(depth):
                record.message_post(
                    body=Markup(f"<p>Prior {idx}</p>"),
                    message_type="comment" if idx % 2 else "email",
                    subtype_xmlid="mail.mt_comment" if idx % 3 else "mail.mt_note",
                )
            record._message_log(body=Markup("<p>Pure log</p>"))
        self.env.flush_all()

        MailMessage = self.env["mail.message"].sudo()
        newest = MailMessage.browse(
            [
                MailMessage.search(
                    [("model", "=", record._name), ("res_id", "=", record.id)],
                    order="id DESC",
                    limit=1,
                ).id
                for record in records
            ]
        )
        self.env.invalidate_all()
        batched = records._notify_by_email_get_ancestors(newest)

        for message in newest:
            per_thread = MailMessage.search(
                [
                    ("model", "=", message.model),
                    ("res_id", "=", message.res_id),
                    ("id", "!=", message.id),
                    ("subtype_id", "!=", False),
                    ("message_id", "!=", False),
                ],
                limit=limit,
                order="id DESC",
            )
            self.assertEqual(
                batched[message.id].ids,
                per_thread.ids,
                "batched ancestors disagree with the per-thread search for "
                "message %s (%s ancestors)" % (message.id, len(per_thread)),
            )

    @users("employee")
    def test_references_never_name_a_message_posted_after(self):
        record = self.env["mail.test.simple"].create({"name": "Later replies"})
        first, second, third = (
            record.message_post(
                body=Markup(f"<p>{body}</p>"),
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            for body in ("first", "second", "third")
        )
        ancestors = record._notify_by_email_get_ancestors(first | second | third)
        self.assertNotIn(second, ancestors[first.id])
        self.assertNotIn(third, ancestors[first.id])
        self.assertEqual(ancestors[second.id] & (first | third), first)
        self.assertEqual(ancestors[third.id] & (first | second), first | second)

    @users("employee")
    def test_a_message_without_parent_threads_under_the_last_human_message(self):
        record = self.env["mail.test.simple"].create({"name": "Chain"})
        creation = record.message_ids
        self.assertEqual(len(creation), 1)

        def post(body, **kwargs):
            kwargs.setdefault("message_type", "comment")
            kwargs.setdefault("subtype_xmlid", "mail.mt_comment")
            return record.message_post(body=body, **kwargs)

        first = post("A")
        note = post("note", subtype_xmlid="mail.mt_note")
        second = post("B")
        explicit = post("C", parent_id=first.id)
        record.message_notify(body="ping", partner_ids=self.partner_employee_2.ids)
        record._message_log(body="log")
        last = post("D")

        self.assertEqual(first.parent_id, creation, "only message so far")
        self.assertEqual(note.parent_id, first)
        self.assertEqual(second.parent_id, note, "a note is a comment too")
        self.assertEqual(explicit.parent_id, first, "an explicit parent is kept")
        self.assertEqual(
            last.parent_id,
            explicit,
            "neither the user notification nor the log outranks the newest comment",
        )

        channel = (
            self.env["discuss.channel"]
            .sudo()
            ._create_channel(name="Free", group_id=None)
        )
        free = channel.message_post(body="free", message_type="comment")
        self.assertFalse(free.parent_id, "a channel message without parent stays free")

    def test_a_batch_post_with_per_record_values_equals_single_posts(self):
        inbox_user = mail_new_test_user(
            self.env,
            login="pr_inbox",
            groups="base.group_user",
            name="Per Record Inbox",
            notification_type="inbox",
        )
        customers = self.env["res.partner"].create(
            [
                {"name": f"Customer {idx}", "email": f"c{idx}@example.com"}
                for idx in range(3)
            ]
        )
        batch = self.env["mail.test.simple"].create(
            [{"name": f"Batch {idx}"} for idx in range(3)]
        )
        single = self.env["mail.test.simple"].create(
            [{"name": f"Single {idx}"} for idx in range(3)]
        )
        (batch | single).message_subscribe(partner_ids=inbox_user.partner_id.ids)
        parents = {
            record.id: record.message_post(body="root", message_type="comment").id
            for record in batch | single
        }
        self.env.flush_all()

        def per_record(record, idx, parent_id):
            return {
                "subject": f"Subject {idx}",
                "partner_ids": customers[idx].ids,
                "attachments": [(f"file{idx}.txt", b"content")],
                "email_from": f"sender{idx}@example.com",
                "parent_id": parent_id,
                "email_layout_xmlid": "mail.mail_notification_light",
            }

        with self.mock_mail_gateway():
            batch_messages = batch._message_post_batch(
                {record.id: f"<p>Body {idx}</p>" for idx, record in enumerate(batch)},
                message_type="comment",
                subtype_id=self.env.ref("mail.mt_comment").id,
                values_per_record={
                    record.id: per_record(record, idx, parents[record.id])
                    for idx, record in enumerate(batch)
                },
                notify_per_record={batch[1].id: {"force_email_lang": "en_US"}},
            )
            single_messages = self.env["mail.message"]
            for idx, record in enumerate(single):
                values = per_record(record, idx, parents[record.id])
                single_messages += record.message_post(
                    body=f"<p>Body {idx}</p>",
                    message_type="comment",
                    subtype_id=self.env.ref("mail.mt_comment").id,
                    **values,
                )
        self.env.flush_all()

        def shape(message):
            return {
                "subject": message.subject,
                "body": message.body,
                "partners": sorted(message.partner_ids.mapped("name")),
                "attachments": sorted(message.attachment_ids.mapped("name")),
                "email_from": message.email_from,
                "layout": message.email_layout_xmlid,
                "parent_is_root": message.parent_id.body == "<p>root</p>",
                "author": message.author_id.name,
                "notifications": sorted(
                    (n.res_partner_id.name, n.notification_type)
                    for n in message.notification_ids
                ),
                "thread_followers": sorted(
                    self.env[message.model]
                    .browse(message.res_id)
                    .message_partner_ids.mapped("name")
                ),
            }

        self.assertEqual(
            [shape(m) for m in batch_messages], [shape(m) for m in single_messages]
        )
        for message in batch_messages:
            self.assertEqual(len(message.notification_ids), 2, "inbox user + customer")

    def test_a_batch_post_names_a_partner_only_on_the_record_that_names_it(self):
        partner = self.env["res.partner"].create(
            {"name": "Comment Follower", "email": "comment.follower@example.com"}
        )
        followed, naming = self.env["mail.test.simple"].create(
            [{"name": "Followed"}, {"name": "Naming"}]
        )
        followed.message_subscribe(
            partner_ids=partner.ids,
            subtype_ids=self.env.ref("mail.mt_comment").ids,
        )
        records = followed | naming
        for skip_followers in (False, True):
            with self.subTest(notify_skip_followers=skip_followers):
                with self.mock_mail_gateway():
                    messages = records._message_post_batch(
                        {record.id: "<p>Internal</p>" for record in records},
                        message_type="comment",
                        subtype_id=self.env.ref("mail.mt_note").id,
                        values_per_record={naming.id: {"partner_ids": partner.ids}},
                        notify_skip_followers=skip_followers,
                    )
                on_followed, on_naming = messages
                self.assertFalse(on_followed.notification_ids)
                self.assertEqual(on_naming.notification_ids.res_partner_id, partner)

    def test_a_batch_post_refuses_per_record_values_it_cannot_honour(self):
        record = self.env["mail.test.simple"].create({"name": "Refused"})
        with self.assertRaises(ValueError):
            record._message_post_batch(
                {record.id: "x"}, values_per_record={record.id: {"body": "y"}}
            )
        with self.assertRaises(ValueError):
            record._message_post_batch(
                {record.id: "x"}, values_per_record={record.id: {"partner_ids": "1"}}
            )
        with self.assertRaises(ValueError):
            record._message_post_batch(
                {record.id: "x"}, notify_per_record={record.id: {"not_a_flag": 1}}
            )

    def test_a_posted_message_keeps_its_body_and_thread_pointer_cached(self):
        record = self.env["mail.test.simple"].create({"name": "Cached"})
        message = record.message_post(
            body=Markup("<p>hello</p>"),
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        with self.assertQueryCount(0):
            self.assertEqual(message.body, "<p>hello</p>")
            self.assertEqual(message.res_id, record.id)
        self.assertEqual(record.message_ids[0], message)

    def test_inbox_notifications_are_flushed_once_per_batch(self):
        inbox_users = self.user_employee | mail_new_test_user(
            self.env,
            login="inbox_2",
            groups="base.group_user",
            name="Second Inbox",
            notification_type="inbox",
        )
        records = self.env["mail.test.simple"].create(
            [{"name": f"Inbox {idx}"} for idx in range(3)]
        )
        records.message_subscribe(partner_ids=inbox_users.partner_id.ids)
        self.env.flush_all()

        Notification = type(self.env["mail.notification"])
        create_origin = Notification.create
        create_sizes = []

        def _create(model, vals_list):
            create_sizes.append(len(vals_list))
            return create_origin(model, vals_list)

        with (
            patch.object(Notification, "create", autospec=True, side_effect=_create),
            self.mock_bus(),
        ):
            messages = records._message_post_batch(
                {record.id: f"Body {record.id}" for record in records},
                message_type="comment",
                subtype_id=self.env.ref("mail.mt_comment").id,
            )
            self.env.flush_all()

        inbox_notifs = (
            self.env["mail.notification"]
            .sudo()
            .search(
                [
                    ("mail_message_id", "in", messages.ids),
                    ("notification_type", "=", "inbox"),
                ]
            )
        )
        self.assertEqual(len(inbox_notifs), 6, "one per message and recipient")
        self.assertEqual(create_sizes, [6], "one create call for the whole batch")
        self.assertEqual(set(inbox_notifs.mapped("mail_message_id")), set(messages))
        self.assertEqual(
            set(inbox_notifs.mapped("res_partner_id")), set(inbox_users.partner_id)
        )
        for user in inbox_users:
            channel = [self.env.cr.dbname, "res.partner", user.partner_id.id]
            inbox_pushes = [
                payload["payload"]
                for payload in (
                    json_loads(notif.message)
                    for notif in self._new_bus_notifs
                    if json_loads(notif.channel) == channel
                )
                if payload["type"] == "mail.message/needaction"
            ]
            self.assertEqual(
                sorted(push["message_id"] for push in inbox_pushes),
                sorted(messages.ids),
                f"one inbox push per message for {user.login}",
            )
            for push in inbox_pushes:
                stored = next(
                    data
                    for data in push["store_data"]["mail.message"]
                    if data["id"] == push["message_id"]
                )
                self.assertTrue(stored["needaction"], "seen as unread by its recipient")
                self.assertIn("thread", stored)

    @mute_logger(
        "odoo.addons.mail.models.mail_mail",
        "odoo.addons.mail.models.mixin_mail_thread",
        "odoo.addons.mail.models.mixin_mail_gateway",
    )
    @users("employee")
    def test_post_internal(self):
        test_record = self.env["mail.test.simple"].browse(self.test_record.ids)

        test_record.message_subscribe([self.user_admin.partner_id.id])
        with self.mock_mail_gateway():
            msg = test_record.message_post(
                body="My Body",
                message_type="comment",
                subject="My Subject",
                subtype_xmlid="mail.mt_note",
            )
        self.assertFalse(
            msg.is_internal,
            'Notes are not "internal" but replies will be. Subtype being internal should be sufficient from ACLs point of view.',
        )
        self.assertFalse(msg.partner_ids)
        self.assertFalse(msg.notified_partner_ids)

        self.format_and_process(
            MAIL_TEMPLATE_PLAINTEXT,
            self.user_admin.email,
            "not_my_businesss@example.com",
            msg_id="<1198923581.41972151344608186800.JavaMail.diff1@agrolait.example.com>",
            extra=f"In-Reply-To:\r\n\t{msg.message_id}\n",
            target_model="mail.test.simple",
        )
        reply = test_record.message_ids - msg
        self.assertTrue(reply)
        self.assertTrue(reply.is_internal)
        self.assertEqual(reply.notified_partner_ids, self.user_employee.partner_id)
        self.assertEqual(reply.parent_id, msg)
        self.assertEqual(reply.subtype_id, self.env.ref("mail.mt_note"))

    def test_post_parameters(self):
        portal_record = self.env["mail.test.access"].create(
            {
                "access": "logged",
                "name": "Portal enabled",
            }
        )
        with self.mock_mail_gateway():
            with self.assertRaises(ValueError):
                _msg = portal_record.with_user(self.user_portal).message_post(
                    body="My Body",
                    mail_headers={
                        "X-Portal": "myself",
                    },
                    message_type="comment",
                    subject="My Subject",
                    subtype_xmlid="mail.mt_comment",
                )

    @users("employee")
    def test_out_of_office_step_is_free_when_nobody_configured_one(self):
        self.env["res.users"].sudo().search(
            [("out_of_office_from", "!=", False)]
        ).write({"out_of_office_from": False})
        test_record = self.env["mail.test.simple"].create({"name": "ooo cost"})
        message = test_record.message_post(
            body="warm up", message_type="comment", subtype_xmlid="mail.mt_comment"
        )
        recipients_data = list(
            self.env["mail.followers"]
            ._get_recipient_data(
                test_record, "comment", self.env.ref("mail.mt_comment").id
            )[test_record.id]
            .values()
        )
        test_record._notify_thread_with_out_of_office(message, recipients_data)
        self.env.invalidate_all()
        with self.assertQueryCount(__system__=0):
            self.assertFalse(
                test_record._notify_thread_with_out_of_office(message, recipients_data)
            )

    def test_post_with_out_of_office(self):
        test_record = self.env["mail.test.simple"].browse(self.test_record.ids)
        test_record.message_subscribe(self.user_employee_c2.partner_id.ids)
        with self.mock_datetime_and_now(datetime(2025, 6, 17, 11, 10, 0)):
            test_record.with_user(self.user_admin).message_post(
                body="Posting before leaving on holidays",
                message_type="comment",
                subtype_id=self.env.ref("mail.mt_comment").id,
            )
        test_record.message_unsubscribe(self.partner_admin.ids)

        self._setup_out_of_office(
            self.user_admin + self.user_employee_c2 + self.user_portal
        )
        self.user_employee.notification_type = (
            "email"
        )
        self.user_admin.notification_type = (
            "email"
        )

        for user in self.user_admin + self.user_employee_c2:
            self.assertTrue(user.is_out_of_office)
        for user in self.user_employee + self.user_employee_c3 + self.user_portal:
            self.assertFalse(user.is_out_of_office, "Unset or portal")

        for msg, post_dt, author_user, recipients, exp_ooo_authors in [
            (
                "partner_admin should not OOO himself when replying to its own message",
                datetime(2025, 6, 17, 14, 16, 5),
                self.user_admin,
                self.user_admin.partner_id,
                self.env["res.partner"],
            ),
            (
                "Portal user should not generate OOO messages, admin should as original message author",
                datetime(2025, 6, 17, 14, 15, 59),
                self.user_employee,
                self.user_portal.partner_id,
                self.partner_admin,
            ),
            (
                "partner_admin and user_employee_2 are in direct recipients and OOO, but admin already sent it",
                datetime(2025, 6, 17, 14, 15, 59),
                self.user_employee,
                (
                    self.user_admin
                    + self.user_employee_c2
                    + self.user_employee_c3
                    + self.user_portal
                ).partner_id,
                self.partner_employee_c2,
            ),
            (
                "Do not send multiple OOO with same author/recipient in a 4 days timeframe",
                datetime(2025, 6, 18, 14, 15, 59),
                self.user_employee,
                (
                    self.user_admin
                    + self.user_employee_c2
                    + self.user_employee_c3
                    + self.user_portal
                ).partner_id,
                self.env["res.partner"],
            ),
            (
                "multiple OOO, more than 4 days after last OOO -> done",
                datetime(2025, 6, 22, 14, 16, 0),
                self.user_employee,
                (
                    self.user_admin
                    + self.user_employee_c2
                    + self.user_employee_c3
                    + self.user_portal
                ).partner_id,
                self.partner_admin + self.partner_employee_c2,
            ),
        ]:
            with self.subTest(msg=msg, post_dt=post_dt, recipients=recipients):
                with (
                    self.mock_mail_gateway(),
                    self.mock_mail_app(),
                    self.mock_datetime_and_now(post_dt),
                ):
                    message = (
                        test_record.with_user(author_user)
                        .with_context(mail_post_autofollow_author_skip=True)
                        .message_post(
                            body="We need admin NOW !",
                            message_type="email",
                            partner_ids=recipients.ids,
                            subtype_id=self.env.ref("mail.mt_comment").id,
                        )
                    )
                self.assertEqual(
                    message.notified_partner_ids,
                    recipients
                    - author_user.partner_id
                    + self.user_employee_c2.partner_id,
                )
                self.assertEqual(
                    len(self._new_msgs),
                    1 + len(exp_ooo_authors),
                    "Posted message + OOO from expected authors",
                )
                ooo_messages = self._new_msgs[1:]
                self.assertEqual(ooo_messages.author_id, exp_ooo_authors)
                for ooo_author in exp_ooo_authors:
                    ooo_message = ooo_messages.filtered_domain(
                        [("author_id", "=", ooo_author.id)]
                    )
                    self.assertMailNotifications(
                        ooo_message,
                        [
                            {
                                "content": "<p>Le numéro que vous avez composé n'est plus attribué.</p>",
                                "email_values": {
                                    "headers": {
                                        "Auto-Submitted": "auto-replied",
                                        "X-Auto-Response-Suppress": "All",
                                    },
                                    "subject": f"Auto: {test_record.name}",
                                },
                                "message_type": "out_of_office",
                                "message_values": {
                                    "author_id": ooo_author,
                                    "email_from": ooo_author.email_formatted,
                                    "model": test_record._name,
                                    "partner_ids": author_user.partner_id,
                                    "notified_partner_ids": author_user.partner_id,
                                    "res_id": test_record.id,
                                    "subject": f"Auto: {test_record.name}",
                                },
                                "notif": [
                                    {
                                        "partner": author_user.partner_id,
                                        "type": "email",
                                    },
                                ],
                                "subtype": "mail.mt_comment",
                            }
                        ],
                    )

    def test_post_with_out_of_office_distinct_recipients(self):
        test_record = self.env["mail.test.simple"].browse(self.test_record.ids)
        self._setup_out_of_office(self.user_admin)
        self.user_admin.notification_type = "email"
        self.assertTrue(self.user_admin.is_out_of_office)

        def _post_as(author_user, post_dt):
            with (
                self.mock_mail_gateway(),
                self.mock_mail_app(),
                self.mock_datetime_and_now(post_dt),
            ):
                test_record.with_user(author_user).with_context(
                    mail_post_autofollow_author_skip=True,
                ).message_post(
                    body="ping",
                    message_type="email",
                    partner_ids=self.user_admin.partner_id.ids,
                    subtype_id=self.env.ref("mail.mt_comment").id,
                )
            return self._new_msgs[1:]

        ooo_a = _post_as(self.user_employee, datetime(2025, 6, 17, 10, 0, 0))
        self.assertEqual(ooo_a.author_id, self.user_admin.partner_id)
        self.assertEqual(ooo_a.partner_ids, self.partner_employee)

        ooo_b = _post_as(self.user_employee_c2, datetime(2025, 6, 18, 10, 0, 0))
        self.assertEqual(
            ooo_b.author_id,
            self.user_admin.partner_id,
            "OOO to a new recipient must not be suppressed by an earlier OOO "
            "to a different recipient",
        )
        self.assertEqual(ooo_b.partner_ids, self.partner_employee_c2)

    def test_post_with_out_of_office_share_author_no_crash(self):
        container = self.env["mail.test.container"].create({"name": "OOO share probe"})
        self.env["ir.access"].sudo().create(
            {
                "name": "portal read container (test)",
                "model_id": self.env["ir.model"]._get("mail.test.container").id,
                "group_id": self.env.ref("base.group_portal").id,
                "kind": "permission",
                "operation": "r",
            }
        )
        container.message_subscribe(self.user_portal.partner_id.ids)
        self._setup_out_of_office(self.user_employee_c2)
        self.assertTrue(self.user_portal.share)
        self.assertTrue(self.user_employee_c2.is_out_of_office)

        with self.mock_mail_gateway(), self.mock_mail_app():
            message = container.with_user(self.user_portal).message_post(
                body="portal ping to an out-of-office teammate",
                message_type="comment",
                partner_ids=self.user_employee_c2.partner_id.ids,
                subtype_id=self.env.ref("mail.mt_comment").id,
            )
        self.assertTrue(message, "the portal comment itself must succeed")
        ooo = (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", "mail.test.container"),
                    ("res_id", "=", container.id),
                    ("message_type", "=", "out_of_office"),
                ]
            )
        )
        self.assertEqual(
            ooo.author_id,
            self.user_employee_c2.partner_id,
            "the absent internal user's OOO auto-reply must still be generated",
        )


@tagged("mail_post")
class TestMessagePostBodyIsHtml(TestMessagePostCommon):
    def _post_as(self, user):
        record = self.env["mail.test.simple"].sudo().create({"name": "body_is_html"})
        return (
            record.sudo()
            .with_user(user)
            .sudo()
            .message_post(
                body="<p>bold <b>here</b></p>",
                body_is_html=True,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        )

    @mute_logger(
        "odoo.addons.mail.models.mixin_mail_thread",
        "odoo.addons.mail.models.mixin_mail_gateway",
    )
    def test_body_is_html_does_not_depend_on_the_author_being_internal(self):
        portal_user = mail_new_test_user(
            self.env,
            groups="base.group_portal",
            login="portal_body_is_html",
            name="Portal Body",
        )
        self.assertFalse(portal_user._is_internal())
        self.assertEqual(
            str(self._post_as(portal_user).body),
            str(self._post_as(self.user_employee).body),
            "a non-internal author must not get the body escaped into visible tags",
        )
        self.assertEqual(
            str(self._post_as(portal_user).body),
            "<p>bold <b>here</b></p>",
        )


@tagged("mail_post")
class TestMessagePostHelpers(TestMessagePostCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_records, cls.test_partners = cls._create_records_for_batch(
            "mail.test.ticket",
            10,
        )

        cls._attachments = cls._generate_attachments_data(2, "mail.template", 0)
        cls.email_1 = "test1@example.com"
        cls.email_2 = "test2@example.com"
        cls.test_template = cls._create_template(
            "mail.test.ticket",
            {
                "attachment_ids": [
                    (0, 0, attach_vals) for attach_vals in cls._attachments
                ],
                "auto_delete": True,
                "body_html": 'Body for: <t t-out="object.name" /><script>test</script><a href="javascript:alert(1)">link</a>',
                "email_cc": cls.partner_1.email,
                "email_to": f"{cls.email_1}, {cls.email_2}",
                "partner_to": "{{ object.customer_id.id }},%s" % cls.partner_2.id,
                "use_default_to": False,
            },
        )
        cls.test_template.attachment_ids.write({"res_id": cls.test_template.id})
        cls.test_template.invalidate_recordset(["attachment_ids"])

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_message_helpers_source_ref(self):
        test_records = self.test_records.with_env(self.env)
        template = self.test_template.with_env(self.env)
        view = self.env.ref("test_mail.mail_template_simple_test")

        for source_ref in (
            "test_mail.mail_test_ticket_tracking_tpl",
            template,
            "test_mail.mail_template_simple_test",
            view,
        ):
            with self.subTest(source_ref=source_ref), self.mock_mail_gateway():
                _new_mails = test_records.with_user(
                    self.user_employee
                ).message_mail_with_source(
                    source_ref,
                    render_values={"partner": self.user_employee.partner_id},
                    subtype_id=self.env["ir.model.data"]._xmlid_to_res_id(
                        "mail.mt_note"
                    ),
                )

                _new_messages = test_records.with_user(
                    self.user_employee
                ).message_post_with_source(
                    source_ref,
                    render_values={"partner": self.user_employee.partner_id},
                    subtype_id=self.env["ir.model.data"]._xmlid_to_res_id(
                        "mail.mt_note"
                    ),
                )

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_message_mail_with_template(self):
        test_records = self.test_records.with_env(self.env)
        template = self.test_template.with_env(self.env)
        with self.mock_mail_gateway():
            _new_mails = test_records.with_user(
                self.user_employee
            ).message_mail_with_source(
                template,
                subtype_id=self.env["ir.model.data"]._xmlid_to_res_id("mail.mt_note"),
            )

        new_partners = self.env["res.partner"].search(
            [("email", "in", (self.email_1, self.email_2))]
        )
        self.assertEqual(
            len(new_partners),
            2,
            "Post with template: should have created partners based on template emails",
        )

        for test_record in test_records:
            all_partners = (
                new_partners + self.partner_1 + self.partner_2 + test_record.customer_id
            )
            self.assertMailMail(
                all_partners,
                "sent",
                author=self.user_employee.partner_id,
                email_values={
                    "attachments": [
                        ("AttFileName_00.txt", b"AttContent_00", "text/plain"),
                        ("AttFileName_01.txt", b"AttContent_01", "text/plain"),
                    ],
                    "subject": f"About {test_record.name}",
                    "body_content": f"Body for: {test_record.name}",
                },
                fields_values={
                    "author_id": self.partner_employee,
                    "auto_delete": True,
                    "email_from": self.partner_employee.email_formatted,
                    "is_internal": False,
                    "is_notification": True,
                    "message_type": "email_outgoing",
                    "model": test_record._name,
                    "notified_partner_ids": all_partners,
                    "subtype_id": self.env["mail.message.subtype"],
                    "reply_to": formataddr(
                        (
                            self.partner_employee.name,
                            f"{self.alias_catchall}@{self.alias_domain}",
                        )
                    ),
                    "res_id": test_record.id,
                },
            )

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_message_mail_with_view(self):
        test_records = self.test_records.with_env(self.env)
        for test_record in test_records:
            test_record.message_subscribe(test_record.customer_id.ids)

        with self.mock_mail_gateway():
            new_mails = test_records.message_mail_with_source(
                "test_mail.mail_template_simple_test",
                render_values={"partner": self.user_employee.partner_id},
                subject="About mass mailing",
                subtype_id=self.env["ir.model.data"]._xmlid_to_res_id("mail.mt_note"),
            )
        self.assertEqual(len(new_mails), 10)
        self.assertEqual(len(self._new_mails), 10)

        for test_record in test_records:
            self.assertMailMail(
                [test_record.customer_id],
                "sent",
                author=self.user_employee.partner_id,
                email_values={
                    "body_content": f"<p>Hello {self.user_employee.partner_id.name}, this comes from {test_record.name}.</p>",
                    "subject": "About mass mailing",
                },
                fields_values={
                    "author_id": self.partner_employee,
                    "auto_delete": False,
                    "email_from": self.partner_employee.email_formatted,
                    "is_internal": False,
                    "is_notification": True,
                    "message_type": "email_outgoing",
                    "model": test_record._name,
                    "notified_partner_ids": test_record.customer_id,
                    "recipient_ids": test_record.customer_id,
                    "subtype_id": self.env["mail.message.subtype"],
                    "reply_to": formataddr(
                        (
                            self.partner_employee.name,
                            f"{self.alias_catchall}@{self.alias_domain}",
                        )
                    ),
                    "res_id": test_record.id,
                },
            )

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_message_post_with_source_subtype(self):
        test_record = self.test_records.with_env(self.env)[0]
        test_template = self.test_template.with_env(self.env)
        with self.mock_mail_gateway():
            new_message = test_record.with_user(
                self.user_employee
            ).message_post_with_source(
                test_template,
                subtype_xmlid="mail.mt_activities",
            )
        self.assertEqual(new_message.subtype_id, self.env.ref("mail.mt_activities"))

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_message_post_with_template(self):
        test_record = self.test_records.with_env(self.env)[0]
        test_record.message_subscribe(test_record.customer_id.ids)
        test_template = self.test_template.with_env(self.env)
        with self.mock_mail_gateway():
            new_message = test_record.with_user(
                self.user_employee
            ).message_post_with_source(
                test_template,
                message_type="comment",
                subtype_id=self.env["ir.model.data"]._xmlid_to_res_id(
                    "mail.mt_comment"
                ),
            )

        new_partners = self.env["res.partner"].search(
            [("email", "in", [self.email_1, self.email_2])]
        )
        self.assertEqual(
            len(new_partners),
            2,
            "Post with template: should have created partners based on template emails",
        )

        self.assertMailNotifications(
            new_message,
            [
                {
                    "content": f'<p>Body for: {test_record.name}<a href="">link</a></p>',
                    "message_type": "comment",
                    "message_values": {
                        "author_id": self.partner_employee,
                        "email_from": formataddr(
                            (
                                self.partner_employee.name,
                                self.partner_employee.email_normalized,
                            )
                        ),
                        "is_internal": False,
                        "model": test_record._name,
                        "reply_to": formataddr(
                            (
                                self.partner_employee.name,
                                f"{self.alias_catchall}@{self.alias_domain}",
                            )
                        ),
                        "res_id": test_record.id,
                    },
                    "notif": [
                        {"partner": self.partner_1, "type": "email"},
                        {"partner": self.partner_2, "type": "email"},
                        {"partner": new_partners[0], "type": "email"},
                        {"partner": new_partners[1], "type": "email"},
                        {"partner": test_record.customer_id, "type": "email"},
                    ],
                    "subtype": "mail.mt_comment",
                }
            ],
        )

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_message_post_with_template_defaults(self):
        test_record = self.test_records.with_env(self.env)[0]
        test_record.message_subscribe(test_record.customer_id.ids)
        test_template = self.test_template.with_env(self.env)
        with self.mock_mail_gateway():
            new_message = test_record.with_user(
                self.user_employee
            ).message_post_with_source(
                test_template,
            )

        new_partners = self.env["res.partner"].search(
            [("email", "in", [self.email_1, self.email_2])]
        )
        self.assertEqual(
            len(new_partners),
            2,
            "Post with template: should have created partners based on template emails",
        )

        self.assertMailNotifications(
            new_message,
            [
                {
                    "content": f'<p>Body for: {test_record.name}<a href="">link</a></p>',
                    "message_type": "notification",
                    "message_values": {
                        "author_id": self.partner_employee,
                        "email_from": formataddr(
                            (
                                self.partner_employee.name,
                                self.partner_employee.email_normalized,
                            )
                        ),
                        "is_internal": False,
                        "model": test_record._name,
                        "reply_to": formataddr(
                            (
                                self.partner_employee.name,
                                f"{self.alias_catchall}@{self.alias_domain}",
                            )
                        ),
                        "res_id": test_record.id,
                    },
                    "notif": [
                        {"partner": self.partner_1, "type": "email"},
                        {"partner": self.partner_2, "type": "email"},
                        {"partner": new_partners[0], "type": "email"},
                        {"partner": new_partners[1], "type": "email"},
                        {"partner": test_record.customer_id, "type": "email"},
                    ],
                    "subtype": "mail.mt_note",
                }
            ],
        )

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail", "odoo.tests")
    def test_message_post_with_view(self):
        test_record = self.test_records.with_env(self.env)[0]
        test_record.message_subscribe(test_record.customer_id.ids)

        with self.mock_mail_gateway():
            new_message = test_record.message_post_with_source(
                "test_mail.mail_template_simple_test",
                message_type="comment",
                render_values={"partner": self.user_employee.partner_id},
                subtype_id=self.env["ir.model.data"]._xmlid_to_res_id(
                    "mail.mt_comment"
                ),
            )

        self.assertMailNotifications(
            new_message,
            [
                {
                    "content": f"<p>Hello {self.user_employee.partner_id.name}, this comes from {test_record.name}.</p>",
                    "message_type": "comment",
                    "message_values": {
                        "author_id": self.partner_employee,
                        "email_from": formataddr(
                            (
                                self.partner_employee.name,
                                self.partner_employee.email_normalized,
                            )
                        ),
                        "is_internal": False,
                        "message_type": "comment",
                        "model": test_record._name,
                        "reply_to": formataddr(
                            (
                                self.partner_employee.name,
                                f"{self.alias_catchall}@{self.alias_domain}",
                            )
                        ),
                        "res_id": test_record.id,
                    },
                    "notif": [
                        {"partner": test_record.customer_id, "type": "email"},
                    ],
                    "subtype": "mail.mt_comment",
                }
            ],
        )

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail", "odoo.tests")
    def test_message_post_with_view_defaults(self):
        test_record = self.test_records.with_env(self.env)[0]
        test_record.message_subscribe(test_record.customer_id.ids)

        with self.mock_mail_gateway():
            new_message = test_record.message_post_with_source(
                "test_mail.mail_template_simple_test",
                render_values={"partner": self.user_employee.partner_id},
                partner_ids=test_record.customer_id.ids,
            )

        self.assertMailNotifications(
            new_message,
            [
                {
                    "content": f"<p>Hello {self.user_employee.partner_id.name}, this comes from {test_record.name}.</p>",
                    "message_type": "notification",
                    "message_values": {
                        "author_id": self.partner_employee,
                        "email_from": formataddr(
                            (
                                self.partner_employee.name,
                                self.partner_employee.email_normalized,
                            )
                        ),
                        "is_internal": False,
                        "message_type": "notification",
                        "model": test_record._name,
                        "reply_to": formataddr(
                            (
                                self.partner_employee.name,
                                f"{self.alias_catchall}@{self.alias_domain}",
                            )
                        ),
                        "res_id": test_record.id,
                    },
                    "notif": [
                        {"partner": test_record.customer_id, "type": "email"},
                    ],
                    "subtype": "mail.mt_note",
                }
            ],
        )


@tagged("mail_post", "post_install", "-at_install")
class TestMessagePostGlobal(TestMessagePostCommon):
    @users("employee")
    def test_message_post_return(self):
        test_record = self.env["mail.test.simple"].browse(self.test_record.ids)

        result = call_kw(
            self.env["mail.test.simple"],
            "message_post",
            [test_record.id],
            {"body": "test"},
        )
        self.assertTrue(tools.misc.has_list_types(result, (int,)))


@tagged("mail_post")
class TestMessageNotifyBatchRecipients(TestMessagePostCommon):

    def test_per_record_recipients_need_no_redundant_empty_list(self):
        records = self.env["mail.test.simple"].create(
            [{"name": "Notified A"}, {"name": "Notified B"}]
        )
        record_a, record_b = records
        messages = records._message_notify_batch(
            {record_a.id: "<p>for A</p>", record_b.id: "<p>for B</p>"},
            partner_ids_per_record={
                record_a.id: self.partner_1.ids,
                record_b.id: self.partner_2.ids,
            },
        )
        self.assertEqual(len(messages), 2)
        by_res_id = {message.res_id: message for message in messages}
        self.assertEqual(by_res_id[record_a.id].partner_ids, self.partner_1)
        self.assertEqual(by_res_id[record_b.id].partner_ids, self.partner_2)

    def test_per_record_recipients_match_the_explicit_empty_list_call(self):
        records = self.env["mail.test.simple"].create(
            [{"name": "Implicit"}, {"name": "Explicit"}]
        )
        implicit, explicit = records
        message_implicit = implicit._message_notify_batch(
            {implicit.id: "<p>body</p>"},
            partner_ids_per_record={implicit.id: self.partner_1.ids},
        )
        message_explicit = explicit._message_notify_batch(
            {explicit.id: "<p>body</p>"},
            partner_ids=[],
            partner_ids_per_record={explicit.id: self.partner_1.ids},
        )
        self.assertEqual(message_implicit.partner_ids, message_explicit.partner_ids)
        self.assertEqual(message_implicit.message_type, message_explicit.message_type)
        self.assertEqual(message_implicit.subtype_id, message_explicit.subtype_id)

    def test_no_recipients_at_all_still_skips(self):
        record = self.env["mail.test.simple"].create({"name": "Nobody"})
        with self.assertLogs("odoo.addons.mail.models.mixin_mail_thread", "WARNING"):
            messages = record._message_notify_batch(
                {record.id: "<p>body</p>"}, partner_ids_per_record={record.id: []}
            )
        self.assertFalse(messages)


@tagged("mail_post")
class TestMessageNotifyBatchCost(TestMessagePostCommon):

    def _notify_batch_of(self, count):
        records = self.env["mail.test.simple"].create(
            [{"name": f"Notified {index}"} for index in range(count)]
        )
        self.env.flush_all()
        self.env.invalidate_all()
        before = self.cr.sql_statement_count
        messages = records._message_notify_batch(
            {record.id: f"<p>body {record.id}</p>" for record in records},
            partner_ids=(self.partner_1 | self.partner_2).ids,
        )
        self.env.flush_all()
        return self.cr.sql_statement_count - before, messages

    def test_notifying_a_batch_costs_no_query_per_record(self):
        few_queries, _few = self._notify_batch_of(2)
        many_queries, messages = self._notify_batch_of(20)
        self.assertLessEqual(
            many_queries - few_queries,
            40,
            f"18 further notified records cost {many_queries - few_queries} extra "
            f"queries (2 records: {few_queries}, 20 records: {many_queries})",
        )
        self.assertEqual(len(messages), 20, "every record still gets its message")
        self.assertEqual(
            len(messages.notification_ids),
            40,
            "both recipients are still notified for each of the twenty records",
        )
        self.assertEqual(
            len(messages.mapped("notification_ids.mail_mail_id")),
            20,
            "the batch still writes one outgoing mail per message",
        )
        self.assertFalse(
            messages.filtered(lambda message: not message.reply_to),
            "every message still resolves its own reply-to",
        )


@tagged("mail_post")
class TestNotifyBatchEmailPrefetch(TestMessagePostCommon):
    def _prefetch_calls_posting_to(self, partner, **post_kwargs):
        records = self.env["mail.test.simple"].create(
            [{"name": f"Batch {index}"} for index in range(5)]
        )
        records.message_subscribe(partner_ids=partner.ids)
        self.env.flush_all()

        calls = []
        Thread = self.registry["mixin.mail.thread"]
        original = Thread._notify_by_email_prefetch

        def traced(records_self, messages):
            calls.append(len(messages))
            return original(records_self, messages)

        with (
            patch.object(Thread, "_notify_by_email_prefetch", traced),
            self.mock_mail_gateway(),
        ):
            records._message_post_batch(
                {record.id: f"<p>body {record.id}</p>" for record in records},
                subtype_id=self.env.ref("mail.mt_comment").id,
                message_type="comment",
                **post_kwargs,
            )
        self.env.flush_all()
        return calls

    def test_a_scheduled_batch_does_not_prefetch_email_data(self):
        when = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        self.assertEqual(
            self._prefetch_calls_posting_to(
                self.partner_employee_2, scheduled_date=when
            ),
            [],
            "a deferred notification sends no email now, so ancestors and "
            "tracking values are fetched when it is replayed, not here",
        )

    def test_an_inbox_only_batch_does_not_prefetch_email_data(self):
        self.assertEqual(
            self._prefetch_calls_posting_to(self.partner_employee),
            [],
            "nobody receives this batch by email, so nothing should be prefetched",
        )

    def test_a_batch_with_an_email_recipient_prefetches_once(self):
        self.assertEqual(
            self._prefetch_calls_posting_to(self.partner_employee_2),
            [5],
            "one prefetch for the whole batch, not one per record",
        )


@tagged("mail_post")
class TestMessagePostBatchPaths(TestMessagePostCommon):

    def _records(self, count=3):
        return self.env["mail.test.simple"].create(
            [{"name": f"Batch {index}"} for index in range(count)]
        )

    def _trace(self, model, method):
        calls = []
        original = getattr(model, method)

        def traced(records_self, *args, **kwargs):
            calls.append(records_self.ids)
            return original(records_self, *args, **kwargs)

        self.patch(model, method, traced)
        return calls

    def test_prepare_hook_runs_on_single_and_batch_posts(self):
        records = self._records()
        seen = []

        def _message_post_prepare_values(record, post_values):
            seen.append(record.id)
            post_values["body"] = Markup("<p>prepared %s</p>") % record.id

        self.patch(
            self.registry["mail.test.simple"],
            "_message_post_prepare_values",
            _message_post_prepare_values,
        )
        batches = self._trace(self.registry["mixin.mail.thread"], "_message_post_batch")
        with self.mock_mail_gateway():
            messages = records._message_post_values_all(
                {
                    record.id: {"body": "raw", "message_type": "comment"}
                    for record in records
                }
            )
            single = records[0].message_post(body="raw")
        self.assertEqual(batches, [records.ids], "posted as one batch")
        self.assertEqual(seen, [*records.ids, records[0].id])
        self.assertEqual(
            messages.mapped("body"),
            [f"<p>prepared {record.id}</p>" for record in records],
        )
        self.assertEqual(single.body, f"<p>prepared {records[0].id}</p>")

    def test_prepare_hook_check_blocks_the_batch(self):
        records = self._records(2)

        def _message_post_prepare_values(record, post_values):
            if post_values.get("message_type") == "comment":
                raise AccessError("no comment")

        self.patch(
            self.registry["mail.test.simple"],
            "_message_post_prepare_values",
            _message_post_prepare_values,
        )
        with self.assertRaises(AccessError):
            records._message_post_values_all(
                {
                    record.id: {"body": "x", "message_type": "comment"}
                    for record in records
                }
            )
        self.assertFalse(records.message_ids.filtered(lambda m: m.body == "<p>x</p>"))

    def test_batch_refuses_a_per_record_author(self):
        record = self._records(1)
        with self.assertRaises(ValueError):
            record._message_post_batch(
                {record.id: "x"},
                values_per_record={record.id: {"author_id": self.partner_1.id}},
            )

    def test_values_all_batches_per_record_authors_with_their_emails(self):
        records = self._records(2)
        authors = self.partner_1 | self.partner_2
        batches = self._trace(self.registry["mixin.mail.thread"], "_message_post_batch")
        with self.mock_mail_gateway():
            messages = records._message_post_values_all(
                {
                    record.id: {"body": "x", "author_id": author.id}
                    for record, author in zip(records, authors, strict=True)
                }
            )
        self.assertEqual(batches, [records.ids])
        self.assertEqual(messages.author_id, authors)
        for message in messages:
            self.assertEqual(message.email_from, message.author_id.email_formatted)

    def test_batch_subscribes_recipients_once_per_partner_set(self):
        records = self._records()
        calls = self._trace(self.registry["mixin.mail.thread"], "message_subscribe")
        with self.mock_mail_gateway():
            records.with_context(mail_post_autofollow=True)._message_post_batch(
                {record.id: "x" for record in records},
                values_per_record={
                    record.id: {"partner_ids": self.partner_1.ids} for record in records
                },
            )
        self.assertEqual(calls, [records.ids])
        for record in records:
            self.assertIn(self.partner_1, record.message_partner_ids)

    def test_batch_subscribes_the_real_author_once(self):
        records = self._records()
        calls = self._trace(self.registry["mixin.mail.thread"], "_message_subscribe")
        with self.mock_mail_gateway():
            records.with_user(self.user_employee)._message_post_batch(
                {record.id: "x" for record in records},
                message_type="comment",
                subtype_id=self.env.ref("mail.mt_comment").id,
                authors={
                    records[0].id: self.partner_1.id,
                    records[1].id: self.partner_2.id,
                },
            )
        self.assertEqual(calls, [records.ids], "one real author, one subscription")

    def test_notify_batch_skips_records_left_without_recipients(self):
        record_a, record_b = self._records(2)
        messages = (record_a | record_b)._message_notify_batch(
            {record_a.id: "<p>for A</p>", record_b.id: "<p>for B</p>"},
            partner_ids=[],
            partner_ids_per_record={record_a.id: self.partner_1.ids},
        )
        self.assertEqual(messages.res_id, record_a.id)
        self.assertEqual(messages.partner_ids, self.partner_1)

    def test_scheduled_notify_batch_does_not_prefetch_email_data(self):
        records = self._records(2)
        calls = self._trace(
            self.registry["mixin.mail.thread"], "_notify_by_email_prefetch"
        )
        when = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        with self.mock_mail_gateway():
            records._message_notify_batch(
                {record.id: "<p>later</p>" for record in records},
                partner_ids=self.partner_employee_2.ids,
                scheduled_date=when,
            )
        self.assertEqual(calls, [])

    def test_batch_web_push_resolves_devices_once(self):
        records = self._records()
        self._setup_push_devices_for_partners(self.partner_employee)
        records.message_subscribe(partner_ids=self.partner_employee.ids)
        lookups = self._trace(
            self.registry["mixin.mail.thread"], "_web_push_get_partners_parameters"
        )
        with (
            self.mock_mail_gateway(),
            patch(
                "odoo.addons.mail.models.mixin_mail_thread.push_to_end_point"
            ) as push,
        ):
            records._message_post_batch(
                {record.id: f"<p>body {record.id}</p>" for record in records},
                message_type="comment",
                subtype_id=self.env.ref("mail.mt_comment").id,
            )
        self.assertEqual(len(lookups), 1, "one device lookup for the batch")
        self.assertEqual(push.call_count, 3, "one push per message")
        pushed = [json_loads(call.kwargs["payload"]) for call in push.call_args_list]
        self.assertEqual(
            sorted(payload["options"]["data"]["res_id"] for payload in pushed),
            sorted(records.ids),
        )


@tagged("mail_post", "multi_lang")
class TestMessagePostLang(MailCommon, TestRecipients):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.test_records = cls.env["mail.test.lang"].create(
            [
                {
                    "customer_id": False,
                    "email_from": "test.record.1@test.customer.com",
                    "lang": "es_ES",
                    "name": "TestRecord1",
                },
                {
                    "customer_id": cls.partner_2.id,
                    "email_from": "valid.other@gmail.com",
                    "name": "TestRecord2",
                },
            ]
        )

        cls.test_template = cls.env["mail.template"].create(
            {
                "auto_delete": True,
                "body_html": '<p>EnglishBody for <t t-out="object.name"/></p>',
                "email_from": "{{ user.email_formatted }}",
                "email_to": '{{ (object.email_from if not object.customer_id else "") }}',
                "lang": "{{ object.customer_id.lang or object.lang }}",
                "model_id": cls.env["ir.model"]._get("mail.test.lang").id,
                "name": "TestTemplate",
                "partner_to": '{{ object.customer_id.id if object.customer_id else "" }}',
                "subject": "EnglishSubject for {{ object.name }}",
                "use_default_to": False,
            }
        )

        cls._activate_multi_lang(
            test_record=cls.test_records[0], test_template=cls.test_template
        )

        cls.partner_2.write({"lang": "es_ES"})

    def test_assert_initial_values(self):
        self.assertEqual(self.partner_1.lang, "en_US")
        self.assertEqual(self.partner_2.lang, "es_ES")

        self.assertEqual(self.test_records[0].lang, "es_ES")
        self.assertEqual(self.test_records[0].customer_id.lang, False)
        self.assertEqual(self.test_records[1].lang, False)
        self.assertEqual(self.test_records[1].customer_id.lang, "es_ES")

        self.assertFalse(self.test_records[0].message_follower_ids)
        self.assertFalse(self.test_records[1].message_follower_ids)

        self.assertEqual(self.user_employee.lang, "en_US")

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_composer_lang_template_comment(self):
        test_record = self.test_records[0].with_user(self.env.user)
        test_template = self.test_template.with_user(self.env.user)

        for partner in self.env["res.partner"] + self.partner_1 + self.partner_2:
            with self.subTest(partner=partner):
                test_record.write(
                    {
                        "customer_id": partner.id,
                    }
                )
                with self.mock_mail_gateway():
                    test_record.message_post_with_source(
                        test_template,
                        email_layout_xmlid="mail.test_layout",
                        message_type="comment",
                        subtype_id=self.env.ref("mail.mt_comment").id,
                    )

                exp_content_lang = partner.lang or "es_ES"
                exp_notif_lang = partner.lang or "en_US"

                if partner:
                    customer = partner
                else:
                    customer = self.env["res.partner"].search(
                        [("email_normalized", "=", "test.record.1@test.customer.com")],
                        limit=1,
                    )
                    self.assertTrue(
                        customer,
                        "Template usage should have created a contact based on record email",
                    )
                self.assertEqual(customer.lang, exp_notif_lang)

                customer_email = self._find_sent_email_wemail(customer.email_formatted)
                self.assertTrue(customer_email)
                body = customer_email["body"]
                if exp_content_lang == "en_US":
                    self.assertIn(
                        f"EnglishBody for {test_record.name}",
                        body,
                        "Body based on template should be translated",
                    )
                else:
                    self.assertIn(
                        f"SpanishBody for {test_record.name}",
                        body,
                        "Body based on template should be translated",
                    )
                if exp_content_lang == "en_US":
                    self.assertEqual(
                        f"EnglishSubject for {test_record.name}",
                        customer_email["subject"],
                        "Subject based on template should be translated",
                    )
                else:
                    self.assertEqual(
                        f"SpanishSubject for {test_record.name}",
                        customer_email["subject"],
                        "Subject based on template should be translated",
                    )
                if exp_notif_lang == "en_US":
                    self.assertNotIn(
                        "Spanish Layout para", body, "Layout translation failed"
                    )
                    self.assertIn(
                        "English Layout for Lang Chatter Model",
                        body,
                        "Layout / model translation failed",
                    )
                    self.assertNotIn(
                        "Spanish Model Description", body, "Model translation failed"
                    )
                    self.assertNotIn(
                        "SpanishView Spanish Model Description",
                        body,
                        '"View document" translation failed',
                    )
                    self.assertIn(
                        f"View {test_record._description}",
                        body,
                        '"View document" translation failed',
                    )
                else:
                    self.assertNotIn(
                        "English Layout for", body, "Layout translation failed"
                    )
                    self.assertIn(
                        "Spanish Layout para Spanish Model Description",
                        body,
                        "Layout / model translation failed",
                    )
                    self.assertNotIn(
                        "Lang Chatter Model", body, "Model translation failed"
                    )
                    self.assertIn(
                        "SpanishView Spanish Model Description",
                        body,
                        '"View document" translation failed',
                    )
                    self.assertNotIn(
                        f"View {test_record._description}",
                        body,
                        '"View document" translation failed',
                    )

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_composer_lang_template_mass(self):
        test_records = self.test_records.with_user(self.env.user)
        test_template = self.test_template.with_user(self.env.user)

        with self.mock_mail_gateway():
            test_records.message_mail_with_source(
                test_template,
                email_layout_xmlid="mail.test_layout",
                message_type="comment",
                subtype_id=self.env["ir.model.data"]._xmlid_to_res_id(
                    "mail.mt_comment"
                ),
            )

        record0_customer = self.env["res.partner"].search(
            [("email_normalized", "=", "test.record.1@test.customer.com")], limit=1
        )
        self.assertTrue(
            record0_customer,
            "Template usage should have created a contact based on record email",
        )

        for record, customer in zip(
            test_records, record0_customer + self.partner_2, strict=True
        ):
            customer_email = self._find_sent_email_wemail(customer.email_formatted)
            self.assertTrue(customer_email)
            body = customer_email["body"]
            self.assertIn(
                f"SpanishBody for {record.name}",
                body,
                "Body based on template should be translated",
            )
            self.assertEqual(
                f"SpanishSubject for {record.name}",
                customer_email["subject"],
                "Subject based on template should be translated",
            )

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_layout_email_lang_context(self):
        test_records = self.test_records.with_user(self.env.user).with_context(
            lang="es_ES"
        )
        test_records[1].message_subscribe(self.partner_2.ids)

        with self.mock_mail_gateway():
            test_records[1].message_post(
                body=Markup("<p>Hello</p>"),
                email_layout_xmlid="mail.test_layout",
                message_type="comment",
                subject="Subject",
                subtype_xmlid="mail.mt_comment",
            )

        customer_email = self._find_sent_email_wemail(self.partner_2.email_formatted)
        self.assertTrue(customer_email)
        body = customer_email["body"]
        self.assertIn("<p>Hello</p>", body, "Body of posted message should be present")
        self.assertIn(
            "Spanish Layout para", body, "Layout content should be translated"
        )
        self.assertNotIn("English Layout for", body)
        self.assertIn(
            "Spanish Layout para Spanish Model Description",
            body,
            "Model name should be translated",
        )
        self.assertIn(
            "SpanishView Spanish Model Description",
            body,
            '"View document" should be translated',
        )
        self.assertNotIn(
            f"View {test_records[1]._description}",
            body,
            '"View document" should be translated',
        )

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_layout_email_lang_template(self):
        test_records = self.test_records.with_user(self.env.user)
        test_template = self.test_template.with_user(self.env.user)

        with self.mock_mail_gateway():
            test_records.message_post_with_source(
                test_template,
                email_layout_xmlid="mail.test_layout",
                message_type="comment",
                subtype_id=self.env["ir.model.data"]._xmlid_to_res_id(
                    "mail.mt_comment"
                ),
            )

        record0_customer = self.env["res.partner"].search(
            [("email_normalized", "=", "test.record.1@test.customer.com")], limit=1
        )
        self.assertTrue(
            record0_customer,
            "Template usage should have created a contact based on record email",
        )

        for record, customer, exp_notif_lang in zip(
            test_records,
            record0_customer + self.partner_2,
            ("en_US", "es_ES"),
            strict=True,
        ):
            customer_email = self._find_sent_email_wemail(customer.email_formatted)
            self.assertTrue(customer_email)

            body = customer_email["body"]
            self.assertIn(
                f"SpanishBody for {record.name}",
                body,
                "Body based on template should be translated",
            )
            self.assertEqual(
                f"SpanishSubject for {record.name}",
                customer_email["subject"],
                "Subject based on template should be translated",
            )
            if exp_notif_lang == "en_US":
                self.assertNotIn(
                    "Spanish Layout para", body, "Layout content should be translated"
                )
                self.assertIn("English Layout for", body)
                self.assertNotIn(
                    "Spanish Layout para Spanish Model Description",
                    body,
                    "Model name should be translated",
                )
                self.assertNotIn(
                    "SpanishView Spanish Model Description",
                    body,
                    '"View document" should be translated',
                )
                self.assertIn(
                    f"View {test_records[1]._description}",
                    body,
                    '"View document" should be translated',
                )
            else:
                self.assertIn(
                    "Spanish Layout para", body, "Layout content should be translated"
                )
                self.assertNotIn("English Layout for", body)
                self.assertIn(
                    "Spanish Layout para Spanish Model Description",
                    body,
                    "Model name should be translated",
                )
                self.assertIn(
                    "SpanishView Spanish Model Description",
                    body,
                    '"View document" should be translated',
                )
                self.assertNotIn(
                    f"View {test_records[1]._description}",
                    body,
                    '"View document" should be translated',
                )

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_post_multi_lang_inactive(self):
        installed = self.env["res.lang"].get_installed()
        self.assertNotIn("fr_FR", [code for code, _name in installed])
        test_records = self.test_records.with_env(self.env)
        customer_inactive_lang = self.env["res.partner"].create(
            {
                "email": "test.partner.fr@test.example.com",
                "lang": "fr_FR",
                "name": "French Inactive Customer",
            }
        )
        test_records.message_subscribe(partner_ids=customer_inactive_lang.ids)

        for record in test_records:
            with self.subTest(record=record.name):
                with (
                    self.mock_mail_gateway(mail_unlink_sent=False),
                    self.mock_mail_app(),
                ):
                    record.message_post(
                        body=Markup("<p>Hi there</p>"),
                        email_layout_xmlid="mail.test_layout",
                        message_type="comment",
                        subject="TeDeum",
                        subtype_xmlid="mail.mt_comment",
                    )
                    message = record.message_ids[0]
                    self.assertEqual(
                        message.notified_partner_ids, customer_inactive_lang
                    )

                    email = self._find_sent_email(
                        self.partner_employee.email_formatted,
                        [customer_inactive_lang.email_formatted],
                    )
                    self.assertTrue(bool(email), "Email not found, check recipients")

                    exp_layout_content_en = "English Layout for Lang Chatter Model"
                    exp_button_en = "View Lang Chatter Model"
                    self.assertIn(exp_layout_content_en, email["body"])
                    self.assertIn(exp_button_en, email["body"])

    @users("employee")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_post_multi_lang_recipients(self):
        test_records = self.test_records.with_env(self.env)
        test_records.message_subscribe(
            partner_ids=(self.partner_1 + self.partner_2).ids
        )

        for employee_lang, email_layout_xmlid in product(
            ("en_US", "es_ES"),
            (False, "mail.test_layout"),
        ):
            with self.subTest(
                employee_lang=employee_lang, email_layout_xmlid=email_layout_xmlid
            ):
                self.user_employee.write(
                    {
                        "lang": employee_lang,
                    }
                )
                for record in test_records:
                    with (
                        self.mock_mail_gateway(mail_unlink_sent=False),
                        self.mock_mail_app(),
                    ):
                        record.message_post(
                            body=Markup("<p>Hi there</p>"),
                            email_layout_xmlid=email_layout_xmlid,
                            message_type="comment",
                            subject="TeDeum",
                            subtype_xmlid="mail.mt_comment",
                        )
                        message = record.message_ids[0]
                        self.assertEqual(
                            message.notified_partner_ids,
                            self.partner_1 + self.partner_2,
                        )

                        for partner in self.partner_1 + self.partner_2:
                            _mail = self.assertMailMail(
                                partner,
                                "sent",
                                mail_message=message,
                                author=self.partner_employee,
                                email_values={
                                    "body_content": "<p>Hi there</p>",
                                    "email_from": self.partner_employee.email_formatted,
                                    "subject": "TeDeum",
                                },
                            )

                        for partner, exp_lang in zip(
                            self.partner_1 + self.partner_2,
                            ("en_US", "es_ES"),
                            strict=True,
                        ):
                            email = self._find_sent_email(
                                self.partner_employee.email_formatted,
                                [partner.email_formatted],
                            )
                            self.assertTrue(
                                bool(email), "Email not found, check recipients"
                            )
                            self.assertEqual(
                                partner.lang, exp_lang, "Test misconfiguration"
                            )

                            exp_layout_content_en = (
                                "English Layout for Lang Chatter Model"
                            )
                            exp_layout_content_es = (
                                "Spanish Layout para Spanish Model Description"
                            )
                            exp_button_en = "View Lang Chatter Model"
                            exp_button_es = "SpanishView Spanish Model Description"
                            if email_layout_xmlid:
                                if exp_lang == "es_ES":
                                    self.assertIn(exp_layout_content_es, email["body"])
                                    self.assertIn(exp_button_es, email["body"])
                                else:
                                    self.assertIn(exp_layout_content_en, email["body"])
                                    self.assertIn(exp_button_en, email["body"])
                            elif exp_lang == "es_ES":
                                self.assertIn('html lang="es_ES"', email["body"])
                            else:
                                self.assertIn('html lang="en_US"', email["body"])
