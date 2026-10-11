import hashlib
import hmac
from itertools import product

from odoo import Command, exceptions
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests import tagged, users
from odoo.tools import mute_logger

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.whatsapp.tests.common import MockIncomingWhatsApp, WhatsAppCommon


class WhatsAppSecurityCase(WhatsAppCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_employee2 = mail_new_test_user(
            cls.env,
            company_id=cls.company_admin.id,
            email="user.employee.2@test.mycompany.com",
            groups="base.group_user",
            login="company_1_test_employee_2",
        )

        cls.template_protected_fields = cls.env["whatsapp.template"].create(
            {
                "body": "Signup link: {{1}}",
                "model_id": cls.env["ir.model"]._get_id("res.partner"),
                "name": "Test Template with Protected Fields",
                "status": "approved",
                "variable_ids": [
                    (
                        0,
                        0,
                        {
                            "demo_value": "Customer",
                            "field_name": "signup_type",
                            "field_type": "field",
                            "line_type": "body",
                            "name": "{{1}}",
                        },
                    ),
                ],
                "wa_account_id": cls.whatsapp_account.id,
            }
        )


@tagged("wa_account", "security")
class WhatsAppAccountSecurity(WhatsAppSecurityCase):
    @mute_logger("odoo.addons.base.models.ir_access")
    def test_account_access(self):
        self.assertTrue(self.whatsapp_account.with_user(self.user_admin).name)
        self.assertTrue(self.whatsapp_account.with_user(self.user_employee).name)
        with self.assertRaises(exceptions.AccessError):
            self.assertTrue(self.whatsapp_account.with_user(self.user_employee_c2).name)

        account_admin = self.whatsapp_account.with_user(self.user_admin)
        account_admin.write(
            {
                "allowed_company_ids": [(4, self.company_2.id)],
            }
        )
        self.assertTrue(self.whatsapp_account.with_user(self.user_employee_c2).name)

    @users("admin")
    def test_account_defaults(self):
        account = self.env["whatsapp.account"].create(
            {
                "account_uid": "azerty",
                "app_secret": "azerty",
                "app_uid": "contact",
                "name": "Test Account",
                "phone_uid": "987987",
                "token": "TestToken",
            }
        )
        self.assertEqual(account.allowed_company_ids, self.env.user.company_id)
        self.assertEqual(account.notify_user_ids, self.env.user)


@tagged("wa_account", "security", "post_install", "-at_install")
class WhatsAppControllerSecurity(MockIncomingWhatsApp, WhatsAppSecurityCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.whatsapp_account.app_secret = "1234567890abcdef"

    @mute_logger("odoo.addons.whatsapp.controller.main")
    def test_signature_verification(self):
        body = json_dumps_bytes({"entry": [{"id": self.whatsapp_account.account_uid}]})
        sig = hmac.new(
            self.whatsapp_account.app_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        response = self._make_webhook_request(
            self.whatsapp_account,
            message_data=body,
            headers={"X-Hub-Signature-256": f"sha256={sig}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.content)

        for signature in [
            False,
            "sha256=",
            sig,
            f"sha256={sig[:-1]}{'1' if sig[-1] == '0' else '0'}",
        ]:
            with self.subTest(signature=signature):
                headers = {"X-Hub-Signature-256": signature} if signature else None
                response = self._make_webhook_request(
                    self.whatsapp_account, headers=headers
                )
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["error"], "authentication_failed")

    def test_a_business_account_with_two_phones_is_verified_by_either(self):
        for second_secret in ("1234567890abcdef", "a-second-app-secret"):
            with self.subTest(same_app=second_secret == "1234567890abcdef"):
                second_phone = self.env["whatsapp.account"].create(
                    {
                        "account_uid": self.whatsapp_account.account_uid,
                        "app_secret": second_secret,
                        "app_uid": "contact",
                        "name": f"odoo account, phone of {second_secret}",
                        "notify_user_ids": self.whatsapp_account.notify_user_ids.ids,
                        "phone_uid": f"second-{second_secret}",
                        "token": "team leader",
                    }
                )
                body = json_dumps_bytes(
                    {"entry": [{"id": self.whatsapp_account.account_uid}]}
                )
                for account in (self.whatsapp_account, second_phone):
                    sig = hmac.new(
                        account.app_secret.encode(), body, hashlib.sha256
                    ).hexdigest()
                    response = self._make_webhook_request(
                        account,
                        message_data=body,
                        headers={"X-Hub-Signature-256": f"sha256={sig}"},
                    )
                    self.assertEqual(response.status_code, 200)
                forged = hmac.new(b"not-a-secret", body, hashlib.sha256).hexdigest()
                response = self._make_webhook_request(
                    second_phone,
                    message_data=body,
                    headers={"X-Hub-Signature-256": f"sha256={forged}"},
                )
                self.assertEqual(response.status_code, 401)
                second_phone.unlink()

    def test_an_unknown_account_is_refused_and_recorded(self):
        response = self._make_webhook_request(
            self.whatsapp_account,
            message_data=json_dumps_bytes({"entry": [{"id": "nobody"}]}),
        )
        self.assertEqual(response.status_code, 404)
        row = self.env["integration.exchange"].search(
            [
                ("state", "=", "refused"),
                ("refusal_reason", "=", "endpoint_not_found"),
                ("channel_name", "like", "whatsapp.account:%"),
            ]
        )
        self.assertEqual(len(row), 1)
        self.assertIn("nobody", row.channel_name)

    def test_the_verification_handshake_echoes_the_challenge(self):
        self.whatsapp_account.webhook_verify_token = "verify-me"
        self.env.flush_all()
        good = self.url_open(
            "/whatsapp/webhook/?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=4242"
        )
        self.assertEqual((good.status_code, good.text), (200, "4242"))
        bad = self.url_open(
            "/whatsapp/webhook/?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=4242"
        )
        self.assertEqual(bad.status_code, 404)
        self.assertNotIn("4242", bad.text)


@tagged("wa_message", "security")
class WhatsAppDiscussSecurity(WhatsAppSecurityCase):
    @users("admin")
    @mute_logger("odoo.addons.base.models.ir_access")
    def test_member_creation(self):
        channel_wa = self.env["discuss.channel"].create(
            {
                "channel_type": "whatsapp",
                "name": "Test",
                "whatsapp_number": "+32456001122",
            }
        )
        with self.assertRaises(exceptions.AccessError):
            channel_wa.with_user(self.user_employee)._add_members(
                users=self.user_employee
            )

        employee_channel = (
            self.env["discuss.channel"]
            .with_user(self.user_employee)
            .create(
                {
                    "channel_type": "whatsapp",
                    "name": "employee channel",
                    "whatsapp_number": "+32456001122",
                }
            )
        )
        employee_channel.with_user(self.user_admin)._add_members(users=self.user_admin)


@tagged("wa_message", "security")
class WhatsAppMessageSecurity(WhatsAppSecurityCase):
    @mute_logger(
        "odoo.addons.auth_signup.models.res_users",
        "odoo.addons.base.models.ir_cron",
        "odoo.addons.base.models.ir_model",
    )
    def test_message_signup_token(self):

        env = self.env(user=self.user_admin)
        whatsapp_template_signup = env["whatsapp.template"].create(
            {
                "body": "Signup link: {{1}}",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "name": "Template with Signup Url",
                "status": "approved",
                "variable_ids": [
                    (
                        0,
                        0,
                        {
                            "demo_value": "Customer",
                            "field_type": "field",
                            "field_name": "signup_type",
                            "line_type": "body",
                            "name": "{{1}}",
                        },
                    ),
                ],
                "wa_account_id": self.whatsapp_account.id,
            }
        )

        env["res.users"].sudo().reset_password(self.user_admin.login)

        env = self.env(user=self.user_wa_admin)
        with self.assertRaises(exceptions.AccessError):
            env.ref("base.user_admin").partner_id._get_signup_url()

        mail_message = self.user_admin.partner_id.message_post(body="foo")
        whatsapp_message = env["whatsapp.message"].create(
            {
                "mail_message_id": mail_message.id,
                "mobile_number": "+32478000000",
                "wa_account_id": whatsapp_template_signup.wa_account_id.id,
                "wa_template_id": whatsapp_template_signup.id,
            }
        )

        env.flush_all()

        with (
            self.sync_env_with_side_cursors(),
            self.mockWhatsappGateway(),
            env.registry.cursor() as cr,
        ):
            env(cr=cr).ref(
                "whatsapp.ir_cron_send_whatsapp_queue"
            ).sudo().method_direct_trigger()

        whatsapp_message.invalidate_recordset()
        self.assertEqual(whatsapp_message.state, "error")
        self.assertIn("signup_type", whatsapp_message.failure_reason)
        self.assertIn("do not have enough rights", whatsapp_message.failure_reason)


@tagged("wa_template", "security")
class WhatsAppTemplateSecurity(WhatsAppSecurityCase):
    @mute_logger("odoo.addons.base.models.ir_model")
    def test_tpl_create(self):
        template = (
            self.env["whatsapp.template"]
            .with_user(self.user_wa_admin)
            .create(
                {
                    "body": "Hello",
                    "name": "Test",
                }
            )
        )
        self.assertEqual(template.body, "Hello")

        with self.assertRaises(exceptions.AccessError):
            template = (
                self.env["whatsapp.template"]
                .with_user(self.user_employee)
                .create(
                    {
                        "body": "Hello",
                        "name": "Test 2",
                    }
                )
            )

    @mute_logger("odoo.addons.base.models.ir_access")
    def test_tpl_read_allowed_users(self):
        template = (
            self.env["whatsapp.template"]
            .with_user(self.user_wa_admin)
            .create({"body": "Hello", "name": "Test"})
        )
        self.assertEqual(template.with_user(self.user_employee).name, "Test")
        self.assertEqual(template.with_user(self.user_employee2).name, "Test")

        template.write(
            {
                "allowed_user_ids": [
                    (4, self.user_wa_admin.id),
                    (4, self.user_employee.id),
                ]
            }
        )
        self.assertEqual(template.with_user(self.user_employee).name, "Test")
        with self.assertRaises(exceptions.AccessError):
            self.assertEqual(template.with_user(self.user_employee2).name, "Test")

    @mute_logger("odoo.addons.base.models.ir_model")
    def test_tpl_phone_field_update(self):
        template = self.env["whatsapp.template"].create(
            {
                "body": "Hello Phone Field Chain",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "name": "WhatsApp Template",
                "template_name": "Phone Field Chain",
                "status": "approved",
                "wa_account_id": self.whatsapp_account.id,
            }
        )
        test_partner = self.env["res.partner"].create(
            {
                "country_id": self.env.ref("base.be").id,
                "name": "Test Partner",
                "phone_ids": [
                    Command.create({"number": "0455334455", "type": "landline"}),
                    Command.create({"number": "0455334456", "type": "mobile"}),
                ],
            }
        )

        field_paths_allowed = ["phone_ids", "phone_sanitized"]
        field_paths_allowed_ko = ["x_studio_phone_ids"]
        field_paths_disallowed = ["name"]
        field_paths_disallowed_ko = [
            "my_custom_phone_field"
        ]
        for field_paths, invalid, admin_only in [
            (field_paths_allowed, False, False),
            (field_paths_allowed_ko, True, False),
            (field_paths_disallowed, False, True),
            (field_paths_disallowed_ko, True, True),
        ]:
            for field_path, test_user in product(
                field_paths, (self.user_employee, self.user_wa_admin, self.user_admin)
            ):
                with self.subTest(field_path=field_path, test_user_name=test_user.name):
                    template.sudo().write({"phone_field": "phone_ids"})
                    template = template.with_user(test_user)
                    if test_user == self.user_employee or (
                        admin_only and test_user == self.user_wa_admin
                    ):
                        with self.assertRaises(exceptions.AccessError):
                            template.write({"phone_field": field_path})
                        continue
                    if invalid:
                        with self.assertRaises(exceptions.ValidationError):
                            template.write({"phone_field": field_path})
                        continue
                    template.write({"phone_field": field_path})
                    test_partner = test_partner.with_user(test_user)
                    composer = self._instanciate_wa_composer_from_records(
                        template, test_partner, with_user=test_user
                    )
                    with self.mockWhatsappGateway():
                        if field_path == "name":
                            with self.assertRaises(exceptions.UserError):
                                composer.action_send_whatsapp_template()
                        else:
                            composer.action_send_whatsapp_template()

    def test_tpl_safe_field_access(self):
        template = self.env["whatsapp.template"].create(
            {
                "body": "hello, I am from '{{1}}'.",
                "model_id": self.env["ir.model"]._get_id("res.users"),
                "name": "Test Template",
                "status": "approved",
            }
        )

        template.with_user(self.user_admin).variable_ids = [
            (5, 0, 0),
            (
                0,
                0,
                {
                    "demo_value": "pwned",
                    "field_name": "password",
                    "field_type": "field",
                    "line_type": "body",
                    "name": "{{1}}",
                },
            ),
        ]

        with self.assertRaises(exceptions.ValidationError):
            template.with_user(self.user_wa_admin).variable_ids = [
                (5, 0, 0),
                (
                    0,
                    0,
                    {
                        "demo_value": "pwned",
                        "field_name": "password",
                        "field_type": "field",
                        "line_type": "body",
                        "name": "{{1}}",
                    },
                ),
            ]

        with self.assertRaises(exceptions.ValidationError):
            template.with_user(self.user_wa_admin).model_id = self.env[
                "ir.model"
            ]._get_id("res.partner")

        with self.assertRaises(exceptions.ValidationError):
            self.env["whatsapp.template"].with_user(self.user_wa_admin).create(
                {
                    "body": "hello, I am from '{{1}}'.",
                    "model_id": self.env["ir.model"]._get_id("res.partner"),
                    "name": "Test Template",
                    "status": "approved",
                    "variable_ids": [(4, template.variable_ids.id)],
                }
            )

    @users("user_wa_admin")
    def test_tpl_update_wa_admin(self):
        template = self.template_protected_fields.with_env(self.env)

        template.write({"name": "Can Update"})
        self.assertEqual(template.name, "Can Update")


class WhatsAppTemplateCompanyAnchor(WhatsAppCommon):
    def test_a_template_belongs_to_the_companies_of_its_account(self):
        self.assertEqual(
            {
                model: self.env[model]._access_company_anchor()
                for model in (
                    "whatsapp.template",
                    "whatsapp.template.button",
                    "whatsapp.template.variable",
                )
            },
            {
                "whatsapp.template": "wa_account_id.allowed_company_ids",
                "whatsapp.template.button": (
                    "wa_template_id.wa_account_id.allowed_company_ids"
                ),
                "whatsapp.template.variable": (
                    "wa_template_id.wa_account_id.allowed_company_ids"
                ),
            },
        )
