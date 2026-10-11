from odoo import Command
from odoo.tests import tagged
from odoo.tools.mail import formataddr

from odoo.addons.mail.tests.common import MailCommon, mail_new_test_user
from odoo.addons.test_mail.data.test_mail_data import MAIL_TEMPLATE, MAIL_TEMPLATE_SHORT
from odoo.addons.test_mail.tests.common import TestRecipients


@tagged("mail_gateway", "mail_flow", "post_install", "-at_install")
class TestMailFlow(MailCommon, TestRecipients):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user_employee_2 = mail_new_test_user(
            cls.env,
            company_id=cls.user_employee.company_id.id,
            email="eglantine@example.com",
            groups="base.group_user,base.group_partner_manager",
            login="employee2",
            name="Eglantine Employee",
            notification_type="email",
            signature="--\nEglantine",
        )
        cls.partner_employee_2 = cls.user_employee_2.partner_id
        cls.user_employee_3 = mail_new_test_user(
            cls.env,
            company_id=cls.user_employee.company_id.id,
            email="emmanuel@example.com",
            groups="base.group_user,base.group_partner_manager",
            login="employee3",
            name="Emmanuel Employee",
            notification_type="email",
            signature="--\nEmmanuel",
        )
        cls.partner_employee_3 = cls.user_employee_3.partner_id
        cls.user_portal = cls._create_portal_user()
        cls.partner_portal = cls.user_portal.partner_id

        cls.test_emails = [
            '"Sylvie Lelitre" <sylvie.lelitre@zboing.com>',
            '"Josiane Quichopoils" <accounting@zboing.com>',
            "pay@zboing.com",
            "invoicing@zboing.com",
            '"Robert Brutijus" <robert@zboing.com>',
            '"Portal Zboing" <portal@zboing.com>',
        ]
        cls.test_emails_normalized = [
            "sylvie.lelitre@zboing.com",
            "accounting@zboing.com",
            "invoicing@zboing.com",
            "pay@zboing.com",
            "robert@zboing.com",
            "portal@zboing.com",
        ]
        cls.customer_zboing = cls.env["res.partner"].create(
            {
                "email": cls.test_emails[4],
                "name": "Robert Brutijus",
                "phone_ids": [
                    Command.create({"number": "+32455335577", "type": "landline"})
                ],
            }
        )
        cls.user_portal_zboing = mail_new_test_user(
            cls.env,
            email=cls.test_emails[5],
            groups="base.group_portal",
            login="portal_zboing",
            name="Portal Zboing",
        )
        cls.customer_portal_zboing = cls.user_portal_zboing.partner_id

        cls.mail_test_lead_model = cls.env["ir.model"]._get("mail.test.lead")
        cls.alias = cls.env["mail.alias"].create(
            {
                "alias_domain_id": cls.mail_alias_domain.id,
                "alias_contact": "everyone",
                "alias_model_id": cls.mail_test_lead_model.id,
                "alias_name": "lead",
            }
        )
        cls.ticket_template = cls.env["mail.template"].create(
            {
                "auto_delete": True,
                "body_html": '<p>Received <t t-out="object.name"/></p>',
                "email_from": "{{ object.user_id.email_formatted or user.email_formatted }}",
                "lang": "{{ object.customer_id.lang }}",
                "model_id": cls.env["ir.model"]._get_id("mail.test.ticket.partner"),
                "name": "Received",
                "subject": "Received {{ object.name }}",
                "use_default_to": True,
            }
        )
        cls.container = cls.env["mail.test.container.mc"].create(
            {
                "alias_defaults": {
                    "state": "new",
                    "state_template_id": cls.ticket_template.id,
                },
                "alias_model_id": cls.env["ir.model"]._get_id(
                    "mail.test.ticket.partner"
                ),
                "alias_name": "help",
                "company_id": cls.user_employee.company_id.id,
                "name": "help",
            }
        )

    def test_assert_initial_values(self):
        self.assertEqual(
            self.env["res.partner"].search(
                [("email_normalized", "in", self.test_emails_normalized)]
            ),
            self.customer_zboing + self.customer_portal_zboing,
        )

    def test_lead_email_to_email(self):
        self.user_employee.notification_type = "email"
        lead = (
            self.env["mail.test.lead"]
            .with_user(self.user_employee)
            .create(
                {
                    "partner_id": self.customer_zboing.id,
                }
            )
        )
        recipients = lead._message_get_suggested_recipients(
            reply_discussion=True,
            no_create=False,
        )
        self.assertEqual(
            recipients,
            [
                {
                    "create_values": {},
                    "email": self.customer_zboing.email_normalized,
                    "name": self.customer_zboing.name,
                    "partner_id": self.customer_zboing.id,
                }
            ],
        )
        with self.mock_mail_gateway(), self.mock_mail_app():
            emp_msg = lead.message_post(
                body="Hello @customer",
                message_type="comment",
                partner_ids=[recipients[0]["partner_id"]],
                subtype_xmlid="mail.mt_comment",
            )
        reply_to_emp = emp_msg.reply_to
        self.assertEqual(
            reply_to_emp,
            formataddr(
                (self.user_employee.name, f"{self.alias_catchall}@{self.alias_domain}")
            ),
        )
        self.assertSMTPEmailsSent(
            mail_server=self.mail_server_notification,
            msg_from=formataddr(
                (self.partner_employee.name, f"{self.default_from}@{self.alias_domain}")
            ),
            smtp_from=self.mail_server_notification.from_filter,
            smtp_to_list=[self.customer_zboing.email_normalized],
            msg_to_lst=[self.customer_zboing.email_formatted],
        )

        cust_reply = self.gateway_mail_reply_from_smtp_email(
            MAIL_TEMPLATE_SHORT,
            [self.customer_zboing.email_normalized],
            reply_all=True,
            add_to_lst=[self.test_emails[0]],
            cc=self.test_emails[1],
        )
        self.assertMailNotifications(
            cust_reply,
            [
                {
                    "content": "Eli alla à l'eau",
                    "message_type": "email",
                    "message_values": {
                        "author_id": self.customer_zboing,
                        "email_from": self.customer_zboing.email_formatted,
                        "incoming_email_cc": self.test_emails[1],
                        "incoming_email_to": self.test_emails[0],
                        "notified_partner_ids": self.user_employee.partner_id,
                        "partner_ids": self.env["res.partner"],
                        "reply_to": formataddr(
                            (
                                self.customer_zboing.name,
                                f"{self.alias_catchall}@{self.alias_domain}",
                            )
                        ),
                        "subject": "Re: False",
                        "subtype_id": self.env.ref("mail.mt_comment"),
                    },
                    "notif": [
                        {"partner": self.user_employee.partner_id, "type": "email"}
                    ],
                },
            ],
        )
        self.assertSMTPEmailsSent(
            mail_server=self.mail_server_notification,
            msg_from=formataddr(
                (self.customer_zboing.name, f"{self.default_from}@{self.alias_domain}")
            ),
            smtp_from=self.mail_server_notification.from_filter,
            smtp_to_list=[self.user_employee.email_normalized],
            msg_to_lst=[
                self.user_employee.email_formatted,
                self.test_emails[0],
                self.test_emails[1],
            ],
            msg_cc_lst=[],
        )

        emp_reply = self.gateway_mail_reply_from_smtp_email(
            MAIL_TEMPLATE_SHORT,
            [self.user_employee.email_normalized],
            reply_all=True,
            cc=self.partner_employee_2.email_formatted,
        )
        self.assertMailNotifications(
            emp_reply,
            [
                {
                    "content": "Eli alla à l'eau",
                    "message_type": "email",
                    "message_values": {
                        "author_id": self.partner_employee,
                        "email_from": self.partner_employee.email_formatted,
                        "incoming_email_cc": self.partner_employee_2.email_formatted,
                        "incoming_email_to": f"{self.test_emails[0]}, {self.test_emails[1]}",
                        "notified_partner_ids": self.customer_zboing,
                        "partner_ids": self.customer_zboing + self.partner_employee_2,
                        "subject": "Re: Re: False",
                        "subtype_id": self.env.ref("mail.mt_comment"),
                    },
                    "notif": [{"partner": self.customer_zboing, "type": "email"}],
                },
            ],
        )
        self.assertSMTPEmailsSent(
            mail_server=self.mail_server_notification,
            msg_from=formataddr(
                (self.partner_employee.name, f"{self.default_from}@{self.alias_domain}")
            ),
            smtp_from=self.mail_server_notification.from_filter,
            smtp_to_list=[self.customer_zboing.email_normalized],
            msg_to_lst=[
                self.customer_zboing.email_formatted,
                self.partner_employee_2.email_formatted,
                self.test_emails[0],
                self.test_emails[1],
            ],
            msg_cc_lst=[],
        )

    def test_lead_mailgateway(self):
        email_to = f"lead@{self.alias_domain}, {self.test_emails[1]}, {self.partner_employee.email_formatted}"
        email_to_filtered = (
            f"{self.test_emails[1]}, {self.partner_employee.email_formatted}"
        )
        email_cc = f"{self.test_emails[2]}, {self.test_emails[5]}"
        with self.mock_mail_gateway(), self.mock_mail_app():
            lead = self.format_and_process(
                MAIL_TEMPLATE,
                self.test_emails[0],
                email_to,
                cc=email_cc,
                subject="Inquiry",
                target_model="mail.test.lead",
            )
        self.assertEqual(
            lead.email_cc, email_cc, "Filled by mixin.mail.thread.cc mixin"
        )
        self.assertEqual(lead.email_from, self.test_emails[0])
        self.assertEqual(lead.name, "Inquiry")
        self.assertFalse(lead.partner_id)
        self.assertFalse(lead.message_partner_ids)
        self.assertEqual(
            len(lead.message_ids),
            1,
            "Incoming email should be only message, no creation message",
        )
        incoming_email = lead.message_ids
        self.assertMailNotifications(
            incoming_email,
            [
                {
                    "content": "Please call me as soon as possible",
                    "message_type": "email",
                    "message_values": {
                        "author_id": self.env["res.partner"],
                        "email_from": self.test_emails[0],
                        "incoming_email_cc": email_cc,
                        "incoming_email_to": email_to_filtered,
                        "mail_server_id": self.env["ir.mail_server"],
                        "parent_id": self.env["mail.message"],
                        "notified_partner_ids": self.env["res.partner"],
                        "partner_ids": self.partner_employee
                        + self.customer_portal_zboing,
                        "subject": "Inquiry",
                        "subtype_id": self.env.ref("mail.mt_comment"),
                    },
                    "notif": [],
                },
            ],
        )

        with self.mock_mail_gateway(), self.mock_mail_app():
            lead.write({"user_id": self.user_employee.id})
        lead_as_emp = lead.with_user(self.user_employee.id)
        self.assertEqual(lead_as_emp.message_partner_ids, self.partner_employee)

        lead_as_emp.message_subscribe(
            partner_ids=(self.partner_employee_2 + self.partner_portal).ids
        )
        self.assertEqual(
            lead_as_emp.message_partner_ids,
            self.partner_employee + self.partner_employee_2 + self.partner_portal,
        )
        lead_as_emp.write(
            {
                "customer_name": "Sylvie Lelitre (Zboing)",
                "phone_ids": [
                    Command.create({"number": "+32455001122", "type": "landline"})
                ],
                "lang_code": "fr_FR",
            }
        )

        suggested_all = lead_as_emp._message_get_suggested_recipients(
            reply_discussion=True,
            no_create=False,
        )
        partner_sylvie = self.env["res.partner"].search(
            [("email_normalized", "=", "sylvie.lelitre@zboing.com")]
        )
        partner_pay = self.env["res.partner"].search(
            [("email_normalized", "=", "pay@zboing.com")]
        )
        partner_accounting = self.env["res.partner"].search(
            [("email_normalized", "=", "accounting@zboing.com")]
        )
        expected_all = [
            {
                "create_values": {},
                "email": "portal@zboing.com",
                "name": "Portal Zboing",
                "partner_id": self.customer_portal_zboing.id,
            },
            {
                "create_values": {},
                "email": "sylvie.lelitre@zboing.com",
                "name": "Sylvie Lelitre (Zboing)",
                "partner_id": partner_sylvie.id,
            },
            {
                "create_values": {},
                "email": "pay@zboing.com",
                "name": "pay@zboing.com",
                "partner_id": partner_pay.id,
            },
            {
                "create_values": {},
                "email": "accounting@zboing.com",
                "name": "Josiane Quichopoils",
                "partner_id": partner_accounting.id,
            },
        ]
        for suggested, expected in zip(suggested_all, expected_all, strict=True):
            self.assertDictEqual(suggested, expected)

        with self.mock_mail_gateway():
            responsible_answer = lead_as_emp.message_post(
                body="<p>Well received !",
                partner_ids=(
                    partner_sylvie
                    + partner_pay
                    + partner_accounting
                    + self.customer_portal_zboing
                ).ids,
                message_type="comment",
                subject=f"Re: {lead.name}",
                subtype_id=self.env.ref("mail.mt_comment").id,
            )
        self.assertEqual(
            lead_as_emp.message_partner_ids,
            self.partner_employee + self.partner_employee_2 + self.partner_portal,
        )

        external_partners = (
            partner_sylvie
            + partner_pay
            + partner_accounting
            + self.customer_portal_zboing
            + self.partner_portal
        )
        internal_partners = self.partner_employee + self.partner_employee_2
        self.assertMailNotifications(
            responsible_answer,
            [
                {
                    "content": "Well received !",
                    "mail_mail_values": {
                        "mail_server_id": self.env[
                            "ir.mail_server"
                        ],
                    },
                    "message_type": "comment",
                    "message_values": {
                        "author_id": self.partner_employee,
                        "email_from": self.partner_employee.email_formatted,
                        "incoming_email_cc": False,
                        "incoming_email_to": False,
                        "mail_server_id": self.env["ir.mail_server"],
                        "notified_partner_ids": external_partners
                        + self.partner_employee_2,
                        "parent_id": incoming_email,
                        "partner_ids": partner_sylvie
                        + partner_pay
                        + partner_accounting
                        + self.customer_portal_zboing,
                        "reply_to": formataddr(
                            (
                                self.partner_employee.name,
                                f"{self.alias_catchall}@{self.alias_domain}",
                            )
                        ),
                        "subtype_id": self.env.ref("mail.mt_comment"),
                    },
                    "notif": [
                        {"partner": partner_sylvie, "type": "email"},
                        {"partner": partner_pay, "type": "email"},
                        {"partner": partner_accounting, "type": "email"},
                        {"partner": self.customer_portal_zboing, "type": "email"},
                        {"partner": self.partner_employee_2, "type": "email"},
                        {"partner": self.partner_portal, "type": "email"},
                    ],
                },
            ],
        )
        for partner in responsible_answer.notified_partner_ids:
            exp_msg_to_partners = partner | external_partners
            exp_msg_to = exp_msg_to_partners.mapped("email_formatted")
            with self.subTest(name=partner.name):
                self.assertSMTPEmailsSent(
                    mail_server=self.mail_server_notification,
                    msg_from=formataddr(
                        (
                            self.partner_employee.name,
                            f"{self.default_from}@{self.alias_domain}",
                        )
                    ),
                    smtp_from=self.mail_server_notification.from_filter,
                    smtp_to_list=[partner.email_normalized],
                    msg_to_lst=exp_msg_to,
                )

        self.gateway_mail_reply_from_smtp_email(
            MAIL_TEMPLATE,
            [partner_sylvie.email_normalized],
            reply_all=True,
            cc=f"{self.test_emails[3]}, {self.test_emails[4]}",
        )
        external_partners += self.customer_zboing
        self.assertEqual(
            len(lead.message_ids), 3, "Incoming email + chatter reply + customer reply"
        )
        self.assertEqual(
            lead.message_partner_ids,
            internal_partners + self.partner_portal,
            "Mail gateway: author (partner_sylvie) should not added in followers if external",
        )

        customer_reply = lead.message_ids[0]
        self.assertMailNotifications(
            customer_reply,
            [
                {
                    "content": "Please call me as soon as possible",
                    "message_type": "email",
                    "message_values": {
                        "author_id": partner_sylvie,
                        "email_from": partner_sylvie.email_formatted,
                        "incoming_email_cc": f"{self.test_emails[3]}, {self.test_emails[4]}",
                        "incoming_email_to": ", ".join(
                            (
                                external_partners
                                - partner_sylvie
                                - self.customer_zboing
                            ).mapped("email_formatted")
                        ),
                        "mail_server_id": self.env["ir.mail_server"],
                        "notified_partner_ids": internal_partners,
                        "parent_id": responsible_answer,
                        "partner_ids": external_partners - partner_sylvie,
                        "reply_to": formataddr(
                            (
                                partner_sylvie.name,
                                f"{self.alias_catchall}@{self.alias_domain}",
                            )
                        ),
                        "subject": f"Re: Re: {lead.name}",
                        "subtype_id": self.env.ref("mail.mt_comment"),
                    },
                    "notif": [
                        {"partner": self.partner_employee, "type": "inbox"},
                        {"partner": self.partner_employee_2, "type": "email"},
                    ],
                },
            ],
        )

    def test_ticket_mailgateway(self):
        email_to = f"help@{self.alias_domain}, {self.test_emails[1]}, {self.partner_employee.email_formatted}"
        email_to_filtered = (
            f"{self.test_emails[1]}, {self.partner_employee.email_formatted}"
        )
        email_cc = f"{self.test_emails[2]}, {self.test_emails[5]}"
        with self.mock_mail_gateway(), self.mock_mail_app():
            ticket = self.format_and_process(
                MAIL_TEMPLATE,
                self.test_emails[0],
                email_to,
                cc=email_cc,
                subject="Inquiry",
                target_model="mail.test.ticket.partner",
            )
            self.flush_tracking()

        partner_sylvie = self.env["res.partner"].search(
            [("email_normalized", "=", "sylvie.lelitre@zboing.com")]
        )
        self.assertTrue(
            partner_sylvie,
            "Acknowledgement template should create a partner for incoming email",
        )
        self.assertEqual(
            partner_sylvie.email,
            "sylvie.lelitre@zboing.com",
            "Should parse name/email correctly",
        )
        self.assertEqual(
            partner_sylvie.name,
            "sylvie.lelitre@zboing.com",
            "TDE FIXME: should parse name/email correctly",
        )
        self.assertEqual(ticket.container_id, self.container)
        self.assertEqual(
            ticket.customer_id,
            partner_sylvie,
            "Should put partner as customer, due to after hook",
        )
        self.assertEqual(ticket.email_from, self.test_emails[0])
        self.assertEqual(ticket.name, "Inquiry")
        self.assertEqual(ticket.state, "new", "Should come from alias defaults")
        self.assertEqual(
            ticket.state_template_id,
            self.ticket_template,
            "Should come from alias defaults",
        )
        self.assertFalse(ticket.message_partner_ids)
        self.assertEqual(
            len(ticket.message_ids), 3, "Incoming email + Acknowledgement + Tracking"
        )

        incoming_email = ticket.message_ids[2]
        self.assertMailNotifications(
            incoming_email,
            [
                {
                    "content": "Please call me as soon as possible",
                    "message_type": "email",
                    "message_values": {
                        "author_id": self.env["res.partner"],
                        "email_from": self.test_emails[0],
                        "incoming_email_cc": email_cc,
                        "incoming_email_to": email_to_filtered,
                        "mail_server_id": self.env["ir.mail_server"],
                        "parent_id": self.env["mail.message"],
                        "notified_partner_ids": self.env["res.partner"],
                        "partner_ids": self.partner_employee
                        + self.customer_portal_zboing,
                        "subject": "Inquiry",
                        "subtype_id": self.env.ref(
                            "test_mail.st_mail_test_ticket_partner_new"
                        ),
                    },
                    "notif": [],
                },
            ],
        )

        acknowledgement = ticket.message_ids[1]
        self.assertMailNotifications(
            acknowledgement,
            [
                {
                    "content": f"Received {ticket.name}",
                    "message_type": "auto_comment",
                    "message_values": {
                        "author_id": self.partner_root,
                        "email_from": self.partner_root.email_formatted,
                        "incoming_email_cc": False,
                        "incoming_email_to": False,
                        "mail_server_id": self.env["ir.mail_server"],
                        "notified_partner_ids": partner_sylvie,
                        "parent_id": incoming_email,
                        "partner_ids": partner_sylvie,
                        "subject": f"Received {ticket.name}",
                        "subtype_id": self.env.ref("mail.mt_note"),
                    },
                    "notif": [
                        {
                            "partner": partner_sylvie,
                            "type": "email",
                        },
                    ],
                },
            ],
        )
