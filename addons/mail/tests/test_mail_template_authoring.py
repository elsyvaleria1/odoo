from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.mail.tests.common import MailCommon


@tagged("mail_template", "-at_install", "post_install")
class TestMailTemplateAuthoring(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.editor = cls.user_employee
        cls.partner_model = cls.env["ir.model"]._get_id("res.partner")
        cls.admin_template = cls.env["mail.template"].create(
            {
                "name": "Written by an administrator",
                "model_id": cls.partner_model,
                "subject": "{{ object.env.user.name }}",
                "body_html": '<p t-out="object.env.company.name"/>',
            }
        )

    def create_as_editor(self, **values):
        return (
            self.env["mail.template"]
            .with_user(self.editor)
            .create({"name": "By an editor", "model_id": self.partner_model, **values})
        )

    def test_the_editor_is_an_editor_below_settings(self):
        self.assertTrue(self.editor.has_group("mail.group_mail_template_editor"))
        self.assertFalse(self.editor.has_group("base.group_system"))

    def test_an_editor_writes_data_and_formatters(self):
        template = self.create_as_editor(
            subject="{{ object.name }} - {{ format_date(object.create_date) }}",
            body_html="<p t-out=\"object.child_ids.mapped('name')\"/>"
            '<p t-if="object.email" t-out="object.email"/>',
        )
        template.body_html = "<p t-out=\"object.parent_id.name or ''\"/>"

    def test_an_editor_cannot_reach_the_environment(self):
        for values in (
            {"body_html": "<p t-out=\"object.env['res.users'].search([]).login\"/>"},
            {"subject": "{{ object.sudo().name }}"},
            {"email_to": "{{ object.write({'name': 'x'}) }}"},
            {"body_html": '<t t-set="slug" t-value="object.name"/>'},
        ):
            with self.subTest(values=values):
                with self.assertRaises(AccessError):
                    self.create_as_editor(**values)

    def test_an_editor_cannot_hand_a_method_to_a_recordset_helper(self):
        for values in (
            {
                "body_html": '<p t-out="object.child_ids.sorted(object.message_unsubscribe)"/>'
            },
            {
                "subject": "{{ object.child_ids.filtered(func=object.message_subscribe) }}"
            },
            {
                "email_to": "{{ object.child_ids.mapped(func=object.message_subscribe) }}"
            },
            {
                "body_html": '<p t-out="object.child_ids.sorted(**dict(key=object.message_unsubscribe))"/>'
            },
        ):
            with self.subTest(values=values):
                with self.assertRaises(AccessError):
                    self.create_as_editor(**values)

    def test_an_editor_cannot_hand_a_method_to_urlencode(self):
        with self.assertRaises(AccessError):
            self.create_as_editor(
                email_to="{{ urlencode({b'3': b''}, quote_via=object.message_subscribe) }}"
            )

    def test_an_editor_keeps_what_the_template_already_held(self):
        template = self.admin_template.with_user(self.editor)
        template.body_html = (
            '<p t-out="object.env.company.name"/><p t-out="object.name"/>'
        )
        template.subject = "{{ object.env.user.name }}!"
        with self.assertRaises(AccessError):
            template.body_html = '<p t-out="object.env.user.password"/>'

    def test_only_what_a_module_file_ships_is_trusted(self):
        spelled = (
            "int(int(object.env['ir.config_parameter'].sudo()"
            ".get_param('auth_signup.signup.validity.hours',144))/24)"
        )
        body = f'<p t-out="{spelled}"/>'
        shipped = self.env["mail.template"].create(
            {
                "name": "Shipped",
                "model_id": self.partner_model,
                "template_fs": "auth_signup/data/mail_template_data.xml",
                "body_html": body,
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": "mail",
                "name": "set_password_email",
                "model": "mail.template",
                "res_id": shipped.id,
            }
        )
        self.env.registry.clear_cache()
        self.create_as_editor(body_html=body)
        shipped.with_user(self.editor).copy({"name": "My copy"})
        with self.assertRaises(AccessError):
            self.create_as_editor(
                body_html=body, model_id=self.env["ir.model"]._get_id("res.company")
            )

        shipped.body_html = '<p t-out="object.env.company.name"/>'
        with self.assertRaises(AccessError):
            self.create_as_editor(body_html='<p t-out="object.env.company.name"/>')
        with self.assertRaises(AccessError):
            shipped.with_user(self.editor).body_html = '<p t-out="object.sudo().name"/>'

    def test_an_administrator_is_not_restricted(self):
        self.env["mail.template"].with_user(self.user_admin).create(
            {
                "name": "Admin",
                "model_id": self.partner_model,
                "body_html": "<p t-out=\"object.env['ir.config_parameter'].sudo()\"/>",
            }
        )

    def test_a_composer_body_is_held_to_the_grammar_at_render(self):
        composer = (
            self.env["wizard.mail.message.send"]
            .with_user(self.editor)
            .with_context(
                default_model="res.partner",
                default_res_ids=self.partner_employee.ids,
            )
            .create({"body": '<p t-out="object.env.company.name"/>'})
        )
        with self.assertRaises(AccessError):
            composer._render_field("body", self.partner_employee.ids)
        composer.body = '<p t-out="object.name"/>'
        rendered = composer._render_field("body", self.partner_employee.ids)
        self.assertIn(self.partner_employee.name, rendered[self.partner_employee.id])

    def test_a_composer_trusts_the_template_it_was_loaded_from(self):
        composer = (
            self.env["wizard.mail.message.send"]
            .with_user(self.editor)
            .with_context(
                default_model="res.partner",
                default_res_ids=self.partner_employee.ids,
            )
            .create({"template_id": self.admin_template.id})
        )
        composer.body = '<p t-out="object.env.company.name"/><p t-out="object.name"/>'
        composer._render_field("body", self.partner_employee.ids)

    def test_the_audit_lists_templates_no_module_ships(self):
        findings = self.env["mail.template"]._audit_template_authoring()
        entry = f"{self.admin_template.display_name} ({self.admin_template.id})"
        self.assertIn(entry, findings)
        self.assertTrue(
            any("the attribute 'env'" in error for error in findings[entry])
        )
