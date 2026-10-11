from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import convert_file
from odoo.tools.misc import file_path

from odoo.addons.base.models.ir_qweb import template_trust_digest

LEAD = "Contact us about anything related to our company or services."


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
        cls.contactus = cls.env.ref("website.contactus_page").view_id
        convert_file(
            cls.env,
            module="website",
            filename="tests/test_view_authoring.xml",
            idref={},
            mode="init",
            noupdate=False,
        )
        cls.guarded_page = cls.env.ref("website.test_guarded_page")

    def designer_edit(self, view, old, new):
        self.assertIn(old, view.arch_db)
        view.with_user(self.designer).with_context(website_id=self.website.id).write(
            {"arch": view.arch_db.replace(old, new)}
        )
        return self.env["ir.ui.view"].search(
            [("key", "=", view.key), ("website_id", "=", self.website.id)]
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

    def test_a_designer_edits_the_text_of_a_page_the_module_ships(self):
        copy = self.designer_edit(self.contactus, LEAD, "Write to us.")
        self.assertEqual(len(copy), 1, "the edit went to a website-specific copy")
        self.assertIn("Write to us.", copy.arch_db)
        self.assertIn(LEAD, self.contactus.arch_db)
        copy = self.designer_edit(copy, 'class="lead"', 'class="lead text-center"')
        self.assertIn("text-center", copy.arch_db)

    def test_a_designer_saves_text_through_the_editor(self):
        self.contactus.with_user(self.designer).with_context(
            website_id=self.website.id
        ).save(value='<p class="lead">Write to us.</p>', xpath="//p[hasclass('lead')]")
        copy = self.env["ir.ui.view"].search(
            [("key", "=", self.contactus.key), ("website_id", "=", self.website.id)]
        )
        self.assertIn("Write to us.", copy.arch_db)
        self.assertNotIn(LEAD, copy.arch_db)

    def test_a_website_copy_lends_its_trust_to_no_expression(self):
        for old, new in (
            (
                "<h1>Contact us</h1>",
                (
                    "<h1 t-out=\"request.env['website.visitor']"
                    '._get_visitor_from_request().partner_id"/>'
                ),
            ),
            ("<h1>Contact us</h1>", '<h1 t-out="logged_partner.email"/>'),
        ):
            with (
                self.subTest(edit=new),
                self.assertRaisesRegex(AccessError, "the name 'request'"),
                self.env.cr.savepoint(),
            ):
                self.designer_edit(self.contactus, old, new)

    def test_an_unedited_website_copy_is_trusted(self):
        copy = (
            self.contactus.with_user(self.designer)
            .with_context(website_id=self.website.id)
            .copy({"key": self.contactus.key, "website_id": self.website.id})
        )
        self.assertEqual(copy.arch_db, self.contactus.arch_db)

    def test_a_designer_edit_of_a_privileged_authored_page_is_refused(self):
        with self.assertRaisesRegex(AccessError, "the name 'request'"):
            self.designer_edit(self.generic, "<span>text</span>", "<span>edited</span>")

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
        def create(key, arch):
            return (
                self.env["ir.ui.view"]
                .with_user(self.designer)
                .create(
                    {
                        "name": "contact us by hand",
                        "type": "qweb",
                        "key": key,
                        "arch": arch,
                    }
                )
            )

        create(
            "website.test_authoring_contactus",
            self.contactus.arch_db.replace(LEAD, "Write to us."),
        )
        with self.assertRaisesRegex(AccessError, "the name 'request'"):
            create(
                "website.test_authoring_contactus_if",
                self.contactus.arch_db.replace("<h1>", '<h1 t-if="user">'),
            )
        contactus = self.env.ref("website.contactus_page")
        url = (
            self.env["website.page"]
            .with_user(self.designer)
            .with_context(website_id=self.website.id)
            .clone_page(contactus.id, page_name="Contact us again")
        )
        clone = self.env["website.page"].search([("url", "=", url)])
        self.assertNotEqual(clone.view_id, contactus.view_id)
        self.assertEqual(clone.view_id.arch_db, contactus.view_id.arch_db)

    def test_a_copy_inherits_no_trust_from_its_original(self):
        with self.assertRaisesRegex(AccessError, "the name 'request'"):
            self.generic.with_user(self.designer).copy()

    def test_a_theme_template_is_trusted_as_its_module_ships_it(self):
        def converted(theme_views):
            theme_view = theme_views.create(
                {
                    "name": "theme view",
                    "key": "website.test_theme_view",
                    "type": "qweb",
                    "arch": '<t t-name="website.test_theme_view">'
                    '<p t-out="request.env.cr.dbname"/></t>',
                }
            )
            vals = theme_view._convert_to_base_model(self.website)
            return self.env["ir.ui.view"].create(vals).with_user(self.designer)

        theme_views = self.env["theme.ir.ui.view"]
        loading = theme_views.with_context(
            install_filename=file_path("website/data/website_data.xml")
        )
        with self.assertRaisesRegex(AccessError, "the name 'request'"):
            converted(theme_views)._check_template_authoring()
        converted(loading)._check_template_authoring()

    def designer_extends(self, view, arch):
        return (
            self.env["ir.ui.view"]
            .with_user(self.designer)
            .with_context(website_id=self.website.id)
            .create(
                {
                    "name": "designer extension",
                    "type": "qweb",
                    "inherit_id": view.id,
                    "arch": arch,
                }
            )
        )

    def test_a_designer_cannot_change_how_a_shipped_page_evaluates(self):
        for arch in (
            (
                '<xpath expr="//t[@t-set=\'logged_partner\']" position="attributes">'
                '<attribute name="t-value">user.partner_id</attribute></xpath>'
            ),
            (
                '<xpath expr="//t[@t-set=\'contactus_form_values\']" position="before">'
                '<t t-set="res_company" t-value="user.company_id"/></xpath>'
            ),
        ):
            with (
                self.subTest(arch=arch),
                self.assertRaisesRegex(
                    AccessError,
                    "Only administrators may change how a template a module ships evaluates",
                ),
                self.env.cr.savepoint(),
            ):
                self.designer_extends(self.contactus, arch)

    def test_a_website_extension_is_checked_in_its_website(self):
        arch = (
            '<xpath expr="//t[@t-set=\'logged_partner\']" position="attributes">'
            '<attribute name="t-value">user.partner_id</attribute></xpath>'
        )
        with self.assertRaisesRegex(
            AccessError,
            "Only administrators may change how a template a module ships evaluates",
        ):
            self.env["ir.ui.view"].with_user(self.designer).create(
                {
                    "name": "designer extension",
                    "type": "qweb",
                    "inherit_id": self.contactus.id,
                    "website_id": self.website.id,
                    "arch": arch,
                }
            )
        extension = self.env["ir.ui.view"].create(
            {
                "name": "designer extension",
                "type": "qweb",
                "inherit_id": self.contactus.id,
                "website_id": self.website.id,
                "arch": arch,
            }
        )
        findings = self.env["ir.ui.view"]._audit_template_authoring()
        self.assertIn(f"{self.contactus.key} ({self.contactus.id})", findings)
        self.assertNotIn(f"designer extension ({extension.id})", findings)

    def test_a_designer_view_cannot_shadow_a_module_extension(self):
        page_arch = (
            '<t t-name="website.test_guarded_page"><t t-call="website.layout">'
            '<div id="wrap"><p class="secret" t-out="request.env.user.login"/></div>'
            "</t></t>"
        )
        guard_arch = (
            '<xpath expr="//p[hasclass(\'secret\')]" position="attributes">'
            "<attribute name=\"t-if\">user.has_group('base.group_system')</attribute>"
            "</xpath>"
        )
        page = self.env["ir.ui.view"].create(
            {
                "name": "guarded page",
                "type": "qweb",
                "key": "website.test_guarded_page",
                "arch": page_arch,
                "shipped_digests": {
                    "arch_db": template_trust_digest(etree.fromstring(page_arch))
                },
            }
        )
        guard = self.env["ir.ui.view"].create(
            {
                "name": "guard",
                "type": "qweb",
                "key": "website.test_guarded_page_guard",
                "inherit_id": page.id,
                "arch": guard_arch,
                "shipped_digests": {
                    "arch_db": template_trust_digest(etree.fromstring(guard_arch))
                },
            }
        )
        harmless = (
            '<xpath expr="//p[hasclass(\'secret\')]" position="attributes">'
            '<attribute name="style">color: red</attribute></xpath>'
        )
        refusal = (
            "Only administrators may change how a template a module ships evaluates"
        )
        with self.assertRaisesRegex(AccessError, refusal), self.env.cr.savepoint():
            self.designer_extends(page, harmless).with_context(
                website_id=self.website.id
            ).write({"key": guard.key})
        with self.assertRaisesRegex(AccessError, refusal), self.env.cr.savepoint():
            self.env["ir.ui.view"].with_user(self.designer).create(
                {
                    "name": "shadow",
                    "type": "qweb",
                    "key": guard.key,
                    "inherit_id": page.id,
                    "website_id": self.website.id,
                    "arch": harmless,
                }
            )
        self.designer_extends(page, harmless)

    def test_a_designer_extends_a_shipped_page_around_what_it_evaluates(self):
        extension = self.designer_extends(
            self.contactus,
            '<data><xpath expr="//h1" position="replace"><h1>Write to us</h1></xpath>'
            '<xpath expr="//div[@id=\'wrap\']" position="inside">'
            '<section class="s_text_block"><p t-if="True">Open on Sundays</p></section>'
            "</xpath></data>",
        )
        self.assertEqual(extension.website_id, self.website)

    def test_a_designer_saves_a_structure_a_module_extension_follows(self):
        def shipped(values):
            return self.env["ir.ui.view"].create(
                {
                    **values,
                    "type": "qweb",
                    "shipped_digests": {
                        "arch_db": template_trust_digest(
                            etree.fromstring(values["arch"])
                        )
                    },
                }
            )

        page = shipped(
            {
                "name": "structured page",
                "key": "website.test_structured_page",
                "arch": '<t t-name="website.test_structured_page">'
                '<t t-call="website.layout"><div id="wrap">'
                '<div class="oe_structure" id="oe_structure_test_structured">'
                "<p>Shipped</p></div>"
                '<p class="visit" t-out="request.website.name"/>'
                "</div></t></t>",
            }
        )
        shipped(
            {
                "name": "structured page module extension",
                "key": "website.test_structured_page_module",
                "inherit_id": page.id,
                "arch": "<xpath expr=\"//div[@id='oe_structure_test_structured']\" "
                'position="after"><p class="module" t-out="request.env.user.name"/>'
                "</xpath>",
            }
        )
        page.with_user(self.designer).with_context(website_id=self.website.id).save(
            value='<div class="oe_structure" id="oe_structure_test_structured">'
            "<section><p>Mine</p></section></div>",
            xpath="//div[@id='oe_structure_test_structured']",
        )
        structure = self.env["ir.ui.view"].search(
            [("key", "=", "website.test_structured_page_oe_structure_test_structured")]
        )
        self.assertEqual(structure.website_id, self.website)
        combined = (
            self.env["ir.ui.view"]
            .with_context(website_id=self.website.id)
            .search(
                [
                    ("key", "=", page.key),
                    ("website_id", "in", (False, self.website.id)),
                ],
                order="website_id",
                limit=1,
            )
            .get_combined_arch()
        )
        self.assertIn("<p>Mine</p>", combined)
        self.assertIn('class="module"', combined)

    def test_a_designer_text_edit_cannot_lend_an_anchor_to_a_module_extension(self):
        impostor = '<div id="wrap"><div class="slot"/>'
        refusal = (
            "Only administrators may change how a template a module ships evaluates"
        )
        with self.assertRaisesRegex(AccessError, refusal), self.env.cr.savepoint():
            self.designer_edit(self.guarded_page, '<div id="wrap">', impostor)
        with self.assertRaisesRegex(AccessError, refusal), self.env.cr.savepoint():
            self.guarded_page.with_user(self.designer).write(
                {"arch": self.guarded_page.arch_db.replace('<div id="wrap">', impostor)}
            )
        copy = self.designer_edit(self.guarded_page, "Plain text", "Edited text")
        self.assertIn("Edited text", copy.arch_db)

    def test_a_designer_template_cannot_take_a_shipped_key(self):
        called = self.env.ref("website.test_called")
        refusal = "website.test_called: it takes the key of a template"
        with self.assertRaisesRegex(AccessError, refusal), self.env.cr.savepoint():
            self.env["ir.ui.view"].with_user(self.designer).with_context(
                website_id=self.website.id
            ).create(
                {
                    "name": "called by me",
                    "type": "qweb",
                    "key": called.key,
                    "arch": '<t t-name="website.test_called"><p t-out="secret"/></t>',
                }
            )
        with self.assertRaisesRegex(AccessError, refusal), self.env.cr.savepoint():
            self.designer_edit(
                called,
                '<p class="called">Called</p>',
                '<p class="called" t-out="secret"/>',
            )
        copy = self.designer_edit(called, "Called", "Called for you")
        self.assertIn("Called for you", copy.arch_db)

    def test_a_designer_cannot_remove_a_module_guard(self):
        guard = self.env.ref("website.test_guarded_page_guard")
        refusal = "Only administrators may remove a template a module ships"
        for remove in (
            lambda view: view.unlink(),
            lambda view: view.write({"active": False}),
            lambda view: view.with_context(website_id=self.website.id).write(
                {"active": False}
            ),
        ):
            with self.assertRaisesRegex(AccessError, refusal), self.env.cr.savepoint():
                remove(guard.with_user(self.designer))
        option = self.env.ref("website.test_guarded_page_option")
        option.active = True
        option.with_user(self.designer).with_context(website_id=self.website.id).write(
            {"active": False}
        )
        self.env.ref("website.test_guarded_page_secret").with_user(
            self.designer
        ).unlink()
