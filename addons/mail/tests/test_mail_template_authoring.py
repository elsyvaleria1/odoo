from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import convert_file
from odoo.tools.misc import file_path

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
        convert_file(
            cls.env,
            module="mail",
            filename="tests/test_mail_template_authoring.xml",
            idref={},
            mode="init",
            noupdate=False,
        )
        cls.shipped = cls.env.ref("mail.mail_template_authoring_shipped")

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
            {"body_html": "<t t-set=\"{'x': object.env.cr.dbname}\"/>"},
            {
                "body_html": '<t t-set="x" '
                't-valuef.translate="{{ object.env.cr.dbname }}"/>'
            },
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

    def editor_copy(self):
        return self.shipped.with_user(self.editor).copy({"name": "My copy"})

    def test_what_the_template_already_held_vouches_for_nothing(self):
        template = self.admin_template.with_user(self.editor)
        template.email_to = "{{ object.email }}"
        for values in (
            {"body_html": '<p t-out="object.env.company.name"/><p>Edited</p>'},
            {"subject": "{{ object.env.user.name }}!"},
        ):
            with (
                self.subTest(values=values),
                self.assertRaisesRegex(AccessError, "the attribute 'env'"),
            ):
                template.write(values)

    def test_a_template_a_module_ships_is_trusted(self):
        shipped = self.shipped.with_user(self.editor)
        shipped._check_template_authoring()
        shipped.body_html = shipped.body_html.replace("Dear", "Hello")
        shipped.subject = "{{ object.env.company.name }} writes to {{ object.name }}"

    def test_a_copy_keeps_the_trust_of_its_text(self):
        copy = self.editor_copy()
        copy.body_html = copy.body_html.replace("Kind regards", "Best wishes")
        copy.subject = "{{ object.name }}, from {{ object.env.company.name }}"
        copy.email_to = "{{ object.email }}"
        copy.body_html = copy.body_html.replace("Dear", "Hi")

    def test_a_copy_edited_where_it_evaluates_is_authored(self):
        copy = self.editor_copy()
        for values in (
            {
                "body_html": str(copy.body_html).replace(
                    "</div>", '<p t-out="object.email"/></div>'
                )
            },
            {"body_html": copy.body_html.replace("object.name", "object.email")},
            {"subject": "{{ object.env.company.name }}: {{ object.email }}"},
        ):
            with (
                self.subTest(values=values),
                self.assertRaisesRegex(AccessError, "the attribute 'env'"),
            ):
                copy.write(values)

    def test_a_shipped_expression_lends_no_trust_to_another_text(self):
        for values in (
            {"body_html": '<p t-out="object.env.company.name"/>'},
            {"subject": "{{ object.env.company.name }}"},
        ):
            with (
                self.subTest(values=values),
                self.assertRaisesRegex(AccessError, "the attribute 'env'"),
            ):
                self.create_as_editor(**values)

    def test_a_shipped_text_vouches_for_its_model_only(self):
        with self.assertRaisesRegex(AccessError, "the attribute 'env'"):
            self.create_as_editor(
                body_html=self.shipped.body_html,
                model_id=self.env["ir.model"]._get_id("res.company"),
            )

    def test_a_translation_keeps_the_trust_of_its_text(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        copy = self.editor_copy()
        copy.update_field_translations(
            "subject",
            {
                "fr_FR": "Nouvelles pour {{ object.name }} de {{ object.env.company.name }}"
            },
        )
        copy.update_field_translations(
            "body_html",
            {
                "fr_FR": copy.body_html.replace(
                    "Thank you for your trust.", "Merci de votre confiance."
                )
            },
        )
        self.assertIn("Merci", copy.with_context(lang="fr_FR").body_html)
        with self.assertRaisesRegex(AccessError, "the attribute 'env'"):
            copy.update_field_translations(
                "subject",
                {"fr_FR": "{{ object.env.company.name }}: {{ object.email }}"},
            )

    def test_the_loader_records_the_digest_of_what_it_loads(self):
        digests = self.shipped.sudo().shipped_digests
        self.assertEqual(
            set(digests), {"subject", "email_to", "body_html"}, "one per field it loads"
        )
        self.assertFalse(self.editor_copy().sudo().shipped_digests)
        self.assertFalse(self.admin_template.shipped_digests)

    def test_a_context_key_does_not_make_a_write_the_loaders(self):
        forged = (
            self.env["mail.template"]
            .sudo()
            .with_context(
                install_mode=True,
                install_module="mail",
                install_filename=file_path(
                    "mail/tests/test_mail_template_authoring.xml"
                ),
                install_xmlid="mail_template_forged",
            )
        )
        body = '<p t-out="object.env.user.password"/>'
        created = forged.create(
            {"name": "Forged", "model_id": self.partner_model, "body_html": body}
        )
        forged.browse(self.admin_template.id).subject = "{{ object.env.user.login }}"
        self.assertFalse(created.shipped_digests)
        self.assertFalse(self.admin_template.shipped_digests)
        for values in ({"body_html": body}, {"subject": "{{ object.env.user.login }}"}):
            with (
                self.subTest(values=values),
                self.assertRaisesRegex(AccessError, "the attribute 'env'"),
            ):
                self.create_as_editor(**values)

    def test_an_editor_cannot_vouch_for_a_text(self):
        with self.assertRaisesRegex(AccessError, 'the field "shipped_digests"'):
            self.create_as_editor(
                body_html='<p t-out="object.env.company.name"/>',
                shipped_digests=self.shipped.sudo().shipped_digests,
            )
        with self.assertRaisesRegex(AccessError, 'the field "shipped_digests"'):
            self.admin_template.with_user(self.editor).write(
                {"shipped_digests": self.shipped.sudo().shipped_digests}
            )
        with self.assertRaisesRegex(AccessError, 'the field "shipped_digests"'):
            self.shipped.with_user(self.editor).read(["shipped_digests"])

    def test_an_editor_resets_a_template_to_what_its_module_ships(self):
        self.shipped.body_html = '<p t-out="object.env.user.password"/>'
        self.env["wizard.mail.template.reset"].with_user(self.editor).with_context(
            default_template_ids=self.shipped.ids
        ).create({}).reset_template()
        self.assertIn("Kind regards", self.shipped.body_html)

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

    def test_a_composer_trusts_the_text_of_the_template_it_was_loaded_from(self):
        composer = (
            self.env["wizard.mail.message.send"]
            .with_user(self.editor)
            .with_context(
                default_model="res.partner",
                default_res_ids=self.partner_employee.ids,
            )
            .create({"template_id": self.admin_template.id})
        )
        composer.body = '<p t-out="object.env.company.name">Company</p>'
        composer._render_field("body", self.partner_employee.ids)
        composer.body = '<p t-out="object.env.company.name"/><p t-out="object.name"/>'
        with self.assertRaisesRegex(AccessError, "the attribute 'env'"):
            composer._render_field("body", self.partner_employee.ids)

    def test_the_audit_lists_templates_no_module_ships(self):
        edited = self.editor_copy()
        edited.body_html = edited.body_html.replace("Dear", "Hello")
        findings = self.env["mail.template"]._audit_template_authoring()
        entry = f"{self.admin_template.display_name} ({self.admin_template.id})"
        self.assertIn(entry, findings)
        self.assertTrue(
            any("the attribute 'env'" in error for error in findings[entry])
        )
        self.assertNotIn(f"{self.shipped.display_name} ({self.shipped.id})", findings)
        self.assertNotIn(f"{edited.display_name} ({edited.id})", findings)
