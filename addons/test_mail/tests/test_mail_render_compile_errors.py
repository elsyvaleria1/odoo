"""A template QWeb cannot compile is refused by the file's error policy.

`_has_unsafe_expression_template_qweb` runs `ir.qweb._generate_code` to find out
whether a template holds anything an evaluator would have to run. It caught
`PermissionError` -- the answer "yes, unsafe" -- and nothing else, so any *other*
failure of the compiler escaped the predicate. It escapes it from outside the
`try` in `_render_template_qweb`, which means it also escapes `_check_render_error`,
the single error policy the module owns: the caller saw a bare `ValueError` where
every other broken template yields a `UserError` naming the template and the model.

The trigger is a parser mismatch, not a contrived input: `html.fragment_fromstring`
is the permissive HTML parser and accepts attribute names `etree.Element` rejects,
so `<p t-out="object.name" a&#34;b="1"/>` parses here and dies in QWeb's codegen
with `ValueError: Invalid attribute name 'a&#34;b'`.

`mail.template._compile_dynamic_fields` reports every failure of the same
`_generate_code` call as a compile error, so an administrator saving such a
body got the friendly `ValidationError` all along. The mixin's copy did not, which
is why the outcome depended on who was saving: a member of the template-editor
group short-circuits `_check_access_right_dynamic_template` and reached that
`ValidationError`; everyone else reached the predicate and got the traceback.
"""

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
