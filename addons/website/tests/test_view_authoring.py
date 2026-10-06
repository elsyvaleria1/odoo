from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestDesignerViewAuthoring(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.designer = new_test_user(
            cls.env,
            login="authoring_designer",
            groups="base.group_user,website.group_website_designer",
        )
        cls.website = cls.env["website"].get_current_website()
        cls.generic = cls.env["ir.ui.view"].create(
            {
                "name": "authoring page",
                "type": "qweb",
                "key": "website.test_authoring_page",
                "arch": '<t t-name="website.test_authoring_page"><div>'
                "<p t-out=\"request.env['res.users'].sudo().search([]).login\"/>"
                "<span>text</span></div></t>",
            }
        )

    def test_the_designer_is_below_settings(self):
        self.assertFalse(self.designer.has_group("base.group_system"))

    def test_a_designer_cannot_add_an_expression_reaching_the_environment(self):
        view = self.generic.with_user(self.designer)
        with self.assertRaisesRegex(AccessError, "the name 'request'"):
            view.write(
                {
                    "arch": '<t t-name="website.test_authoring_page"><div>'
                    "<p t-out=\"request.env['ir.config_parameter'].sudo()"
                    ".get_param('database.secret')\"/></div></t>"
                }
            )

    def test_a_designer_edit_keeps_the_module_expressions(self):
        view = self.generic.with_user(self.designer).with_context(
            website_id=self.website.id
        )
        view.write(
            {
                "arch": '<t t-name="website.test_authoring_page"><div>'
                "<p t-out=\"request.env['res.users'].sudo().search([]).login\"/>"
                '<span>edited</span><p t-out="website.name"/></div></t>'
            }
        )
        copy = self.env["ir.ui.view"].search(
            [
                ("key", "=", "website.test_authoring_page"),
                ("website_id", "=", self.website.id),
            ]
        )
        self.assertEqual(len(copy), 1, "the edit went to a website-specific copy")
        self.assertIn("edited", copy.arch_db)

    def test_a_designer_cannot_create_a_privileged_view(self):
        with self.assertRaises(AccessError):
            self.env["ir.ui.view"].with_user(self.designer).create(
                {
                    "name": "mine",
                    "type": "qweb",
                    "key": "website.test_authoring_mine",
                    "arch": '<t t-name="website.test_authoring_mine">'
                    '<p t-out="env.user.password"/></t>',
                }
            )

    def test_a_designer_duplicates_a_page_the_module_ships(self):
        contactus = self.env.ref("website.contactus_page")
        with self.assertRaisesRegex(AccessError, "the name 'request'"):
            self.env["ir.ui.view"].with_user(self.designer).create(
                {
                    "name": "contact us by hand",
                    "type": "qweb",
                    "key": "website.test_authoring_contactus",
                    "arch": contactus.view_id.arch_db,
                }
            )
        url = (
            self.env["website.page"]
            .with_user(self.designer)
            .with_context(website_id=self.website.id)
            .clone_page(contactus.id, page_name="Contact us again")
        )
        clone = self.env["website.page"].search([("url", "=", url)])
        self.assertNotEqual(clone.view_id, contactus.view_id)
        self.assertEqual(clone.view_id.arch_db, contactus.view_id.arch_db)

    def test_a_designer_copy_carries_only_what_its_original_holds(self):
        view = self.generic.with_user(self.designer)
        copy = view.copy()
        self.assertEqual(copy.arch_db, self.generic.arch_db)
        with self.assertRaisesRegex(AccessError, "the name 'env'"):
            view.copy(
                {
                    "arch": '<t t-name="website.test_authoring_page"><div>'
                    "<p t-out=\"request.env['res.users'].sudo().search([]).login\"/>"
                    '<p t-out="env.user.password"/></div></t>'
                }
            )
