from odoo import Command
from odoo.tests import tagged, users

from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.mail.controllers.thread import ThreadController
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.test_whatsapp.tests.common import WhatsAppFullCase
from odoo.addons.whatsapp.tests.common import MockIncomingWhatsApp


@tagged("whatsapp", "post_install", "-at_install", "wa_webhook")
class WhatsAppWebhookCase(WhatsAppFullCase, MockIncomingWhatsApp):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user_salesperson = mail_new_test_user(
            cls.env,
            groups="base.group_user",
            login="user_salesperson",
        )

        cls.user_salesperson_2 = mail_new_test_user(
            cls.env,
            groups="base.group_user",
            login="user_salesperson_2",
        )

        cls.user_salesperson_3 = mail_new_test_user(
            cls.env,
            groups="base.group_user",
            login="user_salesperson_3",
        )

    @users("user_wa_admin")
    def test_blocklist_message(self):
        MailThreadController = ThreadController()
        test_record = self.test_base_record_nopartner.with_env(self.env)
        whatsapp_template = self.whatsapp_template.with_env(self.env)

        with self.mockWhatsappGateway():
            self._receive_whatsapp_message(
                self.whatsapp_account,
                "Hello, how can remove my number from your WhatsApp listing?",
                "32499123456",
            )
        discuss_channel = self.assertWhatsAppDiscussChannel(
            "32499123456",
            wa_account=self.whatsapp_account,
            wa_message_fields_values={
                "state": "received",
            },
        )

        with self.mockWhatsappGateway():
            discuss_channel.message_post(
                body="Hello, you can just send 'stop' to this number.",
                message_type="whatsapp_message",
            )

        discuss_channel = self.assertWhatsAppDiscussChannel(
            "32499123456",
            wa_account=self.whatsapp_account,
            wa_msg_count=2,
            msg_count=2,
            wa_message_fields_values={
                "state": "sent",
            },
        )

        with self.mockWhatsappGateway():
            self._receive_whatsapp_message(self.whatsapp_account, "Stop", "32499123456")
        discuss_channel = self.assertWhatsAppDiscussChannel(
            "32499123456",
            wa_account=self.whatsapp_account,
            wa_msg_count=3,
            msg_count=3,
            wa_message_fields_values={
                "state": "received",
            },
        )

        blacklist_record = (
            self.env["phone.blacklist"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("number", "=", "+32499123456"),
                    ("active", "=", True),
                ]
            )
        )
        self.assertTrue(bool(blacklist_record))

        with self.mockWhatsappGateway(), MockRequest(self.env):
            data = MailThreadController.mail_message_post(
                "discuss.channel",
                discuss_channel.id,
                {"body": "Hello, Did it work?", "message_type": "whatsapp_message"},
            )
            not_sent_message = self.env["mail.message"].browse(
                data["store_data"]["mail.message"][0]["id"]
            )
        self.assertWAMessage(
            "error",
            fields_values={
                "failure_type": "blacklisted",
                "mail_message_id": not_sent_message,
                "mobile_number": "+32499123456",
            },
        )

        composer = self._instanciate_wa_composer_from_records(
            whatsapp_template, test_record
        )
        with self.mockWhatsappGateway():
            composer.action_send_whatsapp_template()
        self.assertWAMessage(
            "error",
            fields_values={
                "failure_type": "blacklisted",
                "mobile_number": "+32499123456",
            },
        )

        self._receive_whatsapp_message(
            self.whatsapp_account,
            "Hello, I would like to receive messages again.",
            "32499123456",
        )
        blacklist_record = (
            self.env["phone.blacklist"]
            .sudo()
            .with_context(active_test=False)
            .search([("number", "=", "+32499123456")])
        )
        self.assertEqual(len(blacklist_record), 1)
        self.assertEqual(blacklist_record.active, False)

        with self.mockWhatsappGateway(), MockRequest(self.env):
            data = MailThreadController.mail_message_post(
                "discuss.channel",
                discuss_channel.id,
                {
                    "body": "Welcome back!",
                    "message_type": "whatsapp_message",
                },
            )
            message_id = data["message_id"]
            self.assertIn(
                message_id, [m["id"] for m in data["store_data"]["mail.message"]]
            )
            sent_message = self.env["mail.message"].browse(message_id)
        self.assertWAMessage(
            "sent",
            fields_values={
                "failure_type": False,
                "mail_message_id": sent_message,
                "mobile_number": "+32499123456",
            },
        )

    @users("user_wa_admin")
    def test_conversation_name(self):
        with self.mockWhatsappGateway():
            self._receive_whatsapp_message(
                self.whatsapp_account, "Hello! I have no name.", "32476012987"
            )
        discuss_channel = self.assertWhatsAppDiscussChannel("32476012987")
        self.assertEqual(discuss_channel.name, "32476012987")
        self.assertEqual(discuss_channel.display_name, "32476012987")

        discuss_channel.whatsapp_partner_id.name = "Bob"
        discuss_channel.invalidate_recordset(["display_name"])
        self.assertEqual(
            discuss_channel.display_name,
            "Bob (32476012987)",
            "Channel display name should match current name of the partner",
        )

        with self.mockWhatsappGateway():
            self._receive_whatsapp_message(
                self.whatsapp_account,
                "Hello! I'm Sarah Croche. So don't call, because I won't pickup. lolilol",
                "32476012654",
                sender_name="Sarah Croche",
            )
        discuss_channel = self.assertWhatsAppDiscussChannel("32476012654")
        self.assertEqual(discuss_channel.name, "%s (32476012654)" % "Sarah Croche")

    @users("user_wa_admin")
    def test_conversation_match(self):
        test_record = self.test_base_record_nopartner.with_env(self.env)
        whatsapp_template = self.whatsapp_template.with_env(self.env)

        with self.mockWhatsappGateway():
            self._receive_whatsapp_message(
                self.whatsapp_account, "Hey there", "32499123456"
            )
        no_document_discuss_channel = self.assertWhatsAppDiscussChannel(
            "32499123456",
        )

        with self.mockWhatsappGateway():
            operator_message = no_document_discuss_channel.message_post(
                body="Hello, feel free to ask any questions you may have!",
                message_type="whatsapp_message",
            )
        self.assertEqual(len(no_document_discuss_channel.message_ids), 2)
        self.assertWAMessage(
            "sent",
            fields_values={
                "mail_message_id": operator_message,
            },
        )

        composer = self._instanciate_wa_composer_from_records(
            whatsapp_template, test_record
        )
        with self.mockWhatsappGateway():
            composer.action_send_whatsapp_template()
        with self.mockWhatsappGateway():
            self._receive_whatsapp_message(
                self.whatsapp_account,
                "Hello, why are you sending me this?",
                "32499123456",
            )

        document_discuss_channel = self.assertWhatsAppDiscussChannel(
            "32499123456",
            channel_domain=[("id", "=", no_document_discuss_channel.id)],
            msg_count=4,
            wa_msg_count=3,
        )

        with self.mockWhatsappGateway():
            document_discuss_channel.message_post(
                body="Hello, sorry it was a mistake.", message_type="whatsapp_message"
            )

        self.assertEqual(len(document_discuss_channel.message_ids), 5)

    @users("admin")
    def test_conversation_match_multi_user(self):
        test_record_1 = self.test_base_record_nopartner.with_env(self.env)
        test_record_2 = self.env["whatsapp.test.nothread"].create(
            {
                "name": "Test Record 2",
                "phone_ids": [
                    Command.create({"number": "+32 499 12 34 56", "type": "mobile"})
                ],
            }
        )
        whatsapp_template_1 = self.whatsapp_template.with_env(self.env)
        whatsapp_template_2 = whatsapp_template_1.copy(
            {
                "model_id": self.env["ir.model"]._get_id("whatsapp.test.nothread"),
                "name": "No Responsible Template",
                "status": "approved",
                "template_name": "no_responsible_template",
            }
        )

        discuss_channel = self.simulate_conversation(
            whatsapp_template_1,
            test_record_1,
            "32499123456",
            exp_msg_count=2,
            exp_wa_msg_count=1,
        )
        template_1_wa_msg = self._new_wa_msg

        self.simulate_conversation(
            whatsapp_template_2,
            test_record_2,
            "32499123456",
            exp_channel_domain=[("id", "=", discuss_channel.id)],
            exp_msg_count=4,
            exp_wa_msg_count=2,
        )

        self.simulate_conversation(
            False,
            test_record_1,
            "32499123456",
            exp_channel_domain=[("id", "=", discuss_channel.id)],
            exp_msg_count=5,
            exp_wa_msg_count=3,
            receive_message_values={"context": {"id": template_1_wa_msg.msg_uid}},
        )

        new_discuss_channel = self.simulate_conversation(
            whatsapp_template_1,
            test_record_1,
            "32499123456",
            template_with_user=self.user_salesperson_2,
            exp_channel_domain=[("id", "!=", discuss_channel.id)],
            exp_msg_count=2,
            exp_wa_msg_count=1,
        )

        self.simulate_conversation(
            False,
            test_record_1,
            "32499123456",
            exp_channel_domain=[("id", "=", discuss_channel.id)],
            exp_msg_count=7,
            exp_wa_msg_count=4,
            receive_message_values={"context": {"id": template_1_wa_msg.msg_uid}},
        )

        new_discuss_channel = self.simulate_conversation(
            whatsapp_template_1,
            test_record_1,
            "32499123456",
            exp_channel_domain=[
                ("id", "not in", [discuss_channel.id, new_discuss_channel.id])
            ],
            exp_msg_count=2,
            exp_wa_msg_count=1,
        )

    @users("user_wa_admin")
    def test_conversation_match_multi_account(self):
        test_record = self.test_base_record_nopartner.with_env(self.env)
        whatsapp_template = self.whatsapp_template.with_env(self.env)

        composer = self._instanciate_wa_composer_from_records(
            whatsapp_template, test_record
        )
        with self.mockWhatsappGateway():
            composer.action_send_whatsapp_template()

        with self.mockWhatsappGateway():
            self._receive_whatsapp_message(
                self.whatsapp_account,
                "Hello,can you help me?",
                "32499123456",
            )
        channel_1 = self.assertWhatsAppDiscussChannel(
            "32499123456",
            wa_account=self.whatsapp_account,
            msg_count=2,
        )

        with self.mockWhatsappGateway():
            self._receive_whatsapp_message(
                self.whatsapp_account_2,
                "Hello,can you help me?",
                "32499123456",
            )
        channel_2 = self.assertWhatsAppDiscussChannel(
            "32499123456",
            wa_account=self.whatsapp_account_2,
            msg_count=1,
        )
        self.assertNotEqual(channel_1, channel_2)
        self.assertEqual(len(channel_1.message_ids), 2)

    def test_receive_no_document(self):
        existing_partners = self.env["res.partner"].search([])
        with self.mockWhatsappGateway():
            self._receive_whatsapp_message(
                self.whatsapp_account, "Hello, I have a question please.", "32499123456"
            )
        discuss_channel = self.assertWhatsAppDiscussChannel(
            "32499123456",
            wa_mail_message_values={
                "body": "<p>Hello, I have a question please.</p>",
            },
        )
        new_partner = self.env["res.partner"].search(
            [("id", "not in", existing_partners.ids)]
        )
        self.assertEqual(len(new_partner), 1)
        self.assertEqual(
            discuss_channel.channel_partner_ids,
            self.user_wa_admin.partner_id + new_partner,
        )
        self.assertEqual(new_partner.name, "+32499123456")
        self.assertEqual(new_partner._phone_get_number().sanitized, "+32499123456")

    def test_responsible_with_template(self):
        test_template = self.whatsapp_template.copy()
        test_template.write(
            {
                "model_id": self.env["ir.model"]._get_id("whatsapp.test.responsible"),
                "name": "Responsible Template",
                "template_name": "responsible_template",
                "status": "approved",
            }
        )
        test_template_no_record = test_template.copy()
        test_template_no_record.write(
            {
                "model_id": self.env["ir.model"]._get_id("whatsapp.test.nothread"),
                "name": "No Responsible Template",
                "template_name": "no_responsible_template",
                "status": "approved",
            }
        )

        test_record = self.env["whatsapp.test.responsible"].create(
            {
                "name": "Test Record",
                "phone_ids": [
                    Command.create({"number": "+32 497 99 99 99", "type": "landline"})
                ],
            }
        )
        test_record_no_responsible = self.env["whatsapp.test.nothread"].create(
            {
                "name": "Test Record No Responsible",
                "phone_ids": [
                    Command.create({"number": "+32 497 11 11 11", "type": "landline"})
                ],
            }
        )

        expected_responsible = self.user_wa_admin
        with self.subTest(expected_responsible=expected_responsible):
            self._test_responsible_with_template(
                test_record_no_responsible,
                "+32497111111",
                expected_responsible,
                test_template_no_record,
            )
        self.env["discuss.channel"].search(
            [("channel_type", "=", "whatsapp")]
        ).unlink()

        expected_responsible = self.user_wa_admin
        with self.subTest(expected_responsible=expected_responsible):
            self._test_responsible_with_template(
                test_record, "+32497999999", expected_responsible, test_template
            )
        self.env["discuss.channel"].search(
            [("channel_type", "=", "whatsapp")]
        ).unlink()

        test_record.with_user(self.user_salesperson).write({"name": "Edited name"})
        expected_responsible = self.user_salesperson
        with self.subTest(expected_responsible=expected_responsible):
            self._test_responsible_with_template(
                test_record, "+32497999999", expected_responsible, test_template
            )
        self.env["discuss.channel"].search(
            [("channel_type", "=", "whatsapp")]
        ).unlink()

        expected_responsible = self.user_salesperson_2
        with self.subTest(expected_responsible=expected_responsible):
            self._test_responsible_with_template(
                test_record,
                "+32497999999",
                expected_responsible,
                test_template,
                context_user=self.user_salesperson_2,
            )
        self.env["discuss.channel"].search(
            [("channel_type", "=", "whatsapp")]
        ).unlink()

        expected_responsible = self.user_salesperson_3
        test_record.write({"user_id": self.user_salesperson_3.id})
        with self.subTest(expected_responsible=expected_responsible):
            self._test_responsible_with_template(
                test_record, "+32497999999", expected_responsible, test_template
            )
        self.env["discuss.channel"].search(
            [("channel_type", "=", "whatsapp")]
        ).unlink()

        expected_responsible = self.user_salesperson_2 | self.user_salesperson_3
        test_record.write({"user_id": self.user_salesperson_3.id})
        with self.subTest(expected_responsible=expected_responsible):
            self._test_responsible_with_template(
                test_record,
                "+32497999999",
                expected_responsible,
                test_template,
                context_user=self.user_salesperson_2,
            )
        self.env["discuss.channel"].search(
            [("channel_type", "=", "whatsapp")]
        ).unlink()
        test_record.user_id = False

        expected_responsible = (
            self.user_salesperson | self.user_salesperson_2 | self.user_salesperson_3
        )
        test_record.write(
            {"user_ids": (self.user_salesperson | self.user_salesperson_3).ids}
        )
        with self.subTest(expected_responsible=expected_responsible):
            self._test_responsible_with_template(
                test_record,
                "+32497999999",
                expected_responsible,
                test_template,
                context_user=self.user_salesperson_2,
            )

    def _test_responsible_with_template(
        self,
        test_record,
        exp_phone,
        expected_responsible,
        template_id,
        context_user=False,
    ):
        customer_phone_number = (
            test_record._phone_get_number().number.lstrip("+").replace(" ", "")
        )

        with self.mockWhatsappGateway():
            composer = self._instanciate_wa_composer_from_records(
                template_id, test_record, with_user=context_user
            )
            composer._send_whatsapp_template()

            self._receive_whatsapp_message(
                self.whatsapp_account,
                "Hello, I have already paid this.",
                customer_phone_number,
            )

        discuss_channel = self.env["discuss.channel"].search(
            [("whatsapp_number", "=", customer_phone_number)]
        )
        self.assertTrue(bool(discuss_channel))
        self.assertEqual(len(discuss_channel.message_ids), 2)
        channel_messages = discuss_channel.message_ids.sorted(
            lambda message: message.id
        )
        context_message = channel_messages[0]
        self.assertIn(
            f"Related {self.env['ir.model']._get(test_record._name).display_name}:",
            context_message.body,
        )
        self.assertIn(test_record.name, context_message.body)
        self.assertIn(
            f"/odoo/{test_record._name}/{test_record.id}",
            context_message.body,
            "Should contain a link to the context record",
        )

        customer_message = channel_messages[1]
        self.assertEqual(
            customer_message.body, "<p>Hello, I have already paid this.</p>"
        )

        for user in expected_responsible:
            self.assertIn(user.partner_id, discuss_channel.channel_partner_ids)
        customer_partner = (
            discuss_channel.channel_partner_ids - expected_responsible.partner_id
        )
        self.assertEqual(len(customer_partner), 1)
        self.assertEqual(customer_partner.name, exp_phone)
