import werkzeug.exceptions

from odoo.exceptions import ValidationError
from odoo.tests import common, tagged

from odoo.addons.website import uninstall_hook


@tagged("-at_install", "post_install")
class TestTheme(common.TransactionCase):
    def test_theme_upgrade_upstream_rejects_non_theme(self):
        editor = self.env.ref("base.user_admin")
        non_theme = self.env["ir.module.module"].search([("name", "=", "base")])
        self.assertTrue(non_theme)
        with self.assertRaises(werkzeug.exceptions.Forbidden):
            non_theme.with_user(editor)._theme_upgrade_upstream()

    def test_theme_remove_working(self):
        theme_common_module = self.env["ir.module.module"].search(
            [("name", "=", "theme_default")]
        )
        website = self.env["website"].get_current_website()
        website.theme_id = theme_common_module.id
        self.env["ir.module.module"]._theme_remove(website)
        self.assertFalse(
            website.theme_id,
            "The website's theme_id should be cleared after _theme_remove.",
        )

    def test_02_disable_view(self):
        website_id = self.env["website"].browse(1)
        ThemeUtils = self.env["theme.utils"].with_context(website_id=website_id.id)

        ThemeUtils._reset_default_config()

        def _get_header_template_key():
            return (
                self.env["ir.ui.view"]
                .search(
                    [
                        ("key", "in", ThemeUtils._header_templates),
                        ("website_id", "=", website_id.id),
                    ]
                )
                .key
            )

        self.assertEqual(
            _get_header_template_key(),
            "website.template_header_default",
            "Only the default template should be active.",
        )

        key = "website.template_header_vertical"
        ThemeUtils.enable_view(key)
        self.assertEqual(
            _get_header_template_key(),
            key,
            "Only one template can be active at a time.",
        )

        key = "website.template_header_hamburger"
        ThemeUtils.enable_view(key)
        self.assertEqual(
            _get_header_template_key(),
            key,
            "Ensuring it works also for non default template.",
        )


@tagged("-at_install", "post_install")
class TestThemeLoadOrder(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        View = cls.env["ir.ui.view"]
        cls.snippet = View.create(
            {
                "name": "snippet",
                "type": "qweb",
                "key": "website.test_theme_order_snippet",
                "arch": '<t><section><div class="container"/></section></t>',
            }
        )
        cls.variant = View.create(
            {
                "name": "variant",
                "type": "qweb",
                "mode": "primary",
                "key": "website.test_theme_order_variant",
                "inherit_id": cls.snippet.id,
                "arch": "<t/>",
            }
        )
        cls.theme = cls.env["ir.module.module"].create(
            {"name": "test_theme_order", "state": "installed"}
        )
        ThemeView = cls.env["theme.ir.ui.view"]
        variant_extension = ThemeView.create(
            {
                "name": "variant extension",
                "key": "test_theme_order.a_variant",
                "inherit_id": f"ir.ui.view,{cls.variant.id}",
                "arch": '<xpath expr="//div[hasclass(\'o_we_shape\')]" position="replace"/>',
            }
        )
        snippet_extension = ThemeView.create(
            {
                "name": "snippet extension",
                "key": "test_theme_order.b_snippet",
                "inherit_id": f"ir.ui.view,{cls.snippet.id}",
                "arch": '<xpath expr="//div[hasclass(\'container\')]" position="before">'
                '<div class="o_we_shape"/></xpath>',
            }
        )
        cls.env["ir.model.data"].create(
            [
                {
                    "module": "test_theme_order",
                    "name": "a_variant",
                    "model": "theme.ir.ui.view",
                    "res_id": variant_extension.id,
                },
                {
                    "module": "test_theme_order",
                    "name": "b_snippet",
                    "model": "theme.ir.ui.view",
                    "res_id": snippet_extension.id,
                },
            ]
        )
        cls.website = cls.env["website"].create({"name": "theme order"})

    def test_extension_of_an_ancestor_is_copied_first(self):
        self.theme._theme_load(self.website)
        copies = self.env["ir.ui.view"].search(
            [("website_id", "=", self.website.id), ("key", "like", "test_theme_order.")]
        )
        self.assertEqual(
            copies.sorted("id").mapped("key"),
            ["test_theme_order.b_snippet", "test_theme_order.a_variant"],
        )
        arch = self.variant.with_context(
            website_id=self.website.id
        )._get_combined_arch()
        self.assertFalse(arch.xpath("//div[hasclass('o_we_shape')]"))
        arch = self.snippet.with_context(
            website_id=self.website.id
        )._get_combined_arch()
        self.assertTrue(arch.xpath("//div[hasclass('o_we_shape')]"))

    def test_a_menu_listed_before_its_parent_keeps_the_parent(self):
        ThemeMenu = self.env["theme.website.menu"]
        parent = ThemeMenu.create({"name": "Theme parent", "url": "/theme-parent"})
        child = ThemeMenu.create(
            {"name": "Theme child", "url": "/theme-child", "parent_id": parent.id}
        )
        self.env["ir.model.data"].create(
            [
                {
                    "module": "test_theme_order",
                    "name": "a_menu_child",
                    "model": "theme.website.menu",
                    "res_id": child.id,
                },
                {
                    "module": "test_theme_order",
                    "name": "b_menu_parent",
                    "model": "theme.website.menu",
                    "res_id": parent.id,
                },
            ]
        )
        self.theme._theme_load(self.website)
        child_copy = child.copy_ids.filtered(lambda m: m.website_id == self.website)
        parent_copy = parent.copy_ids.filtered(lambda m: m.website_id == self.website)
        self.assertTrue(parent_copy)
        self.assertEqual(child_copy.parent_id, parent_copy)

    def test_theme_copy_is_loaded_with_its_theme(self):
        template = self.env.ref("test_theme_order.b_snippet")
        copy = self.env["ir.ui.view"].create(
            template._convert_to_base_model(self.website)
        )
        View = self.env["ir.ui.view"].with_context(website_id=self.website.id)
        self.assertEqual(
            View._get_loaded_view_ids(copy.ids, ["test_theme_order"]), set(copy.ids)
        )
        self.assertFalse(View._get_loaded_view_ids(copy.ids, ["website"]))


@tagged("-at_install", "post_install")
class TestWebsiteUnlink(common.TransactionCase):
    def test_unlink_website_whose_inactive_view_inherits_another(self):
        website = self.env["website"].create({"name": "to delete"})
        View = self.env["ir.ui.view"]
        parent = View.create(
            {
                "name": "parent",
                "type": "qweb",
                "website_id": website.id,
                "arch": '<div><p class="a"/></div>',
            }
        )
        child = View.create(
            {
                "name": "child",
                "type": "qweb",
                "active": False,
                "website_id": website.id,
                "inherit_id": parent.id,
                "arch": '<xpath expr="//p" position="after"><p class="b"/></xpath>',
            }
        )
        website.unlink()
        self.assertFalse(website.exists())
        self.assertFalse((parent | child).exists())


@tagged("post_install", "-at_install")
class TestThemeEngineBookkeeping(common.TransactionCase):
    def test_a_missing_theme_image_is_restored_without_duplicating_the_others(self):
        Attachment = self.env["ir.attachment"]
        domain = [("res_model", "=", "ir.module.module"), ("type", "=", "url")]
        self.env["ir.module.module"].update_theme_images()
        images = Attachment.search(domain)
        if not images:
            self.skipTest("no theme module with images on the addons path")
        missing = images[0].url
        images[0].unlink()

        self.env["ir.module.module"].update_theme_images()

        urls = Attachment.search(domain).mapped("url")
        self.assertIn(missing, urls)
        self.assertEqual(len(urls), len(set(urls)))

    def test_features_created_together_are_checked_one_by_one(self):
        Feature = self.env["website.configurator.feature"]
        Feature.create(
            [
                {
                    "name": "Page feature",
                    "page_view_id": self.env.ref("website.homepage").id,
                },
                {
                    "name": "Module feature",
                    "module_id": self.env.ref("base.module_website").id,
                },
            ]
        )
        with self.assertRaises(ValidationError):
            Feature.create(
                [
                    {
                        "name": "Fine",
                        "page_view_id": self.env.ref("website.homepage").id,
                    },
                    {"name": "Neither"},
                ]
            )

    def test_the_uninstall_hook_removes_archived_website_records(self):
        View = self.env["ir.ui.view"].with_context(active_test=False)
        Asset = self.env["ir.asset"].with_context(active_test=False)
        view = View.create(
            {
                "name": "Archived specific",
                "type": "qweb",
                "key": "website.archived_specific_probe",
                "arch": "<div/>",
                "website_id": 1,
                "active": False,
            }
        )
        asset = Asset.create(
            {
                "name": "Archived specific asset",
                "bundle": "web.assets_frontend",
                "path": "website/static/src/probe.scss",
                "website_id": 1,
                "active": False,
            }
        )

        uninstall_hook(self.env)

        self.assertFalse(view.exists())
        self.assertFalse(asset.exists())

    def test_an_archived_page_template_is_not_created_again(self):
        View = self.env["ir.ui.view"].with_context(active_test=False)
        website = self.env.ref("base.module_website")
        website._create_primary_page_templates()
        templates = View.search(
            [
                ("key", "like", "website.new_page_template_sections_%"),
                ("website_id", "=", False),
            ]
        )
        self.assertTrue(templates, "the premise: website declares page templates")
        templates[0].active = False

        website._create_primary_page_templates()

        self.assertEqual(
            View.search_count(
                [
                    ("key", "like", "website.new_page_template_sections_%"),
                    ("website_id", "=", False),
                ]
            ),
            len(templates),
        )
