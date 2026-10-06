from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestIrUiViewAuthoring(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = new_test_user(
            cls.env, login="view_author", groups="base.group_user"
        )
        cls.env["ir.access"].create(
            {
                "name": "Probe: the author reads qweb views, like a website designer",
                "model_id": cls.env["ir.model"]._get_id("ir.ui.view"),
                "group_id": cls.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "r",
                "domain": "[('type', '=', 'qweb')]",
            }
        )
        cls.privileged = "env['res.users'].search([]).login"
        cls.view = cls.env["ir.ui.view"].create(
            {
                "name": "authoring",
                "type": "qweb",
                "key": "base.test_authoring",
                "arch": f'<t t-name="base.test_authoring"><p t-out="{cls.privileged}"/></t>',
            }
        )

    def check_as(self, user, arch, previous):
        self.view.write({"arch": arch})
        self.view.with_user(user)._check_template_authoring({self.view.id: previous})

    def test_a_new_expression_below_settings_must_obey_the_grammar(self):
        previous = self.view.arch_db
        with self.assertRaisesRegex(AccessError, "the name 'env' is not available"):
            self.check_as(
                self.author,
                '<t t-name="base.test_authoring"><p t-out="env.user.password"/></t>',
                previous,
            )

    def test_an_expression_the_view_already_held_is_kept(self):
        previous = self.view.arch_db
        self.check_as(
            self.author,
            f'<t t-name="base.test_authoring"><p t-out="{self.privileged}"/>'
            '<p t-out="user.name"/></t>',
            previous,
        )

    def test_a_website_copy_trusts_the_view_it_was_copied_from(self):
        copy = self.view.copy({"key": "base.test_authoring"})
        copy.with_user(self.author)._check_template_authoring({})

    def test_a_rebound_formatter_is_refused(self):
        with self.assertRaisesRegex(AccessError, "cannot be rebound"):
            self.check_as(
                self.author,
                '<t t-name="base.test_authoring">'
                '<t t-set="format_date" t-value="user.name"/></t>',
                self.view.arch_db,
            )

    def test_settings_users_are_not_restricted(self):
        self.check_as(
            self.env.ref("base.user_admin"),
            '<t t-name="base.test_authoring"><p t-out="env.user.password"/></t>',
            None,
        )

    def test_a_privileged_view_created_below_settings_is_refused(self):
        with self.assertRaises(AccessError):
            self.view.with_user(self.author).sudo(False)._check_template_authoring({})
        self.assertTrue(
            self.view.with_user(self.author)._is_restricted_template_author()
        )
        self.assertFalse(self.view.sudo()._is_restricted_template_author())

    def test_the_audit_lists_what_no_module_spells(self):
        findings = self.env["ir.ui.view"]._audit_template_authoring()
        entry = f"base.test_authoring ({self.view.id})"
        self.assertIn(entry, findings)
        self.assertIn("the name 'env' is not available", findings[entry][0])
        copy = self.view.copy({"key": "base.test_authoring"})
        findings = self.env["ir.ui.view"]._audit_template_authoring()
        self.assertIn(entry, findings, "two stored copies do not vouch for each other")
        self.assertIn(f"base.test_authoring ({copy.id})", findings)
