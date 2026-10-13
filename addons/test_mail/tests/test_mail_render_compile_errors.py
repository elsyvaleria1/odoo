
from markupsafe import Markup

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged, users

from odoo.addons.mail.tests import common

UNCOMPILABLE = '<p t-out="object.name" a&#34;b="1"/>'


@tagged("mail_render", "post_install", "-at_install")
class TestUncompilableTemplate(common.MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = "mail.test.track"
        cls.record = cls.env[cls.model].create(
            {"name": "Rec", "email_from": "rec@test.example.com"}
        )
        cls.plain_user = cls.env["res.users"].create(
            {
                "name": "Plain",
                "login": "render_compile_plain",
                "email": "plain@test.example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def test_the_predicate_answers_unsafe_rather_than_raising(self):
        self.assertTrue(
            self.env["mixin.mail.render"]._has_unsafe_expression_template_qweb(
                UNCOMPILABLE, self.model
            )
        )

    def test_rendering_one_reports_it_as_a_render_failure(self):
        with self.assertRaises(UserError):
            self.env["mixin.mail.render"]._render_template(
                UNCOMPILABLE, self.model, [self.record.id], engine="qweb"
            )

    def test_an_editor_may_not_save_one(self):
        with self.assertRaises(ValidationError):
            self.env["mail.template"].create(
                {
                    "name": "uncompilable",
                    "model_id": self.env["ir.model"]._get(self.model).id,
                    "body_html": Markup(UNCOMPILABLE),
                }
            )

    @users("render_compile_plain")
    def test_a_non_editor_may_not_save_one_either(self):
        with self.assertRaises((AccessError, ValidationError)):
            self.env["mail.template"].create(
                {
                    "name": "uncompilable",
                    "model_id": self.env["ir.model"]._get(self.model).id,
                    "body_html": Markup(UNCOMPILABLE),
                }
            )
