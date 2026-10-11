from lxml import etree

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.product.tests.common import ProductCommon


@tagged("post_install", "-at_install")
class TestProductFavorite(ProductCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal = [Command.link(cls.env.ref("base.group_user").id)]
        cls.alice, cls.bob = cls.env["res.users"].create(
            [
                {"name": "Alice", "login": "product_fav_alice", "group_ids": internal},
                {"name": "Bob", "login": "product_fav_bob", "group_ids": internal},
            ]
        )
        cls.template = cls.env["product.template"].create({"name": "Starrable"})

    def _arch_nodes(self, model, view_type, xpath, view_xmlid=False):
        view_id = view_xmlid and self.env.ref(view_xmlid).id
        views = self.env[model].get_views([(view_id, view_type)])
        return etree.fromstring(views["views"][view_type]["arch"]).xpath(xpath)

    def test_is_featured_is_the_same_for_everyone(self):
        self.template.is_featured = True

        self.assertTrue(self.template.with_user(self.alice).is_featured)
        self.assertTrue(self.template.with_user(self.bob).is_featured)

    def test_is_user_favorite_is_per_user_and_leaves_featured_alone(self):
        self.template.is_featured = True

        self.template.with_user(self.alice).is_user_favorite = True

        self.assertTrue(self.template.with_user(self.alice).is_user_favorite)
        self.assertFalse(self.template.with_user(self.bob).is_user_favorite)
        self.assertTrue(self.template.is_featured)

    def test_a_featured_product_is_listed_first(self):
        plain, featured = self.env["product.template"].create(
            [{"name": "AAA plain"}, {"name": "ZZZ featured", "is_featured": True}]
        )
        templates = self.env["product.template"].search(
            [("id", "in", (plain | featured).ids)]
        )

        self.assertEqual(templates, featured | plain)
        self.assertTrue(featured.product_variant_ids.is_featured)

    def test_the_star_stars_for_oneself(self):
        for model, view_type, view_xmlid in (
            ("product.template", "kanban", False),
            ("product.template", "list", False),
            ("product.template", "form", False),
            ("product.product", "kanban", False),
            ("product.product", "list", False),
            ("product.product", "form", False),
            (
                "product.product",
                "kanban",
                "product.view_product_product_kanban_catalog",
            ),
        ):
            with self.subTest(model=model, view=view_xmlid or view_type):
                stars = self._arch_nodes(
                    model,
                    view_type,
                    "//field[@widget='boolean_favorite']/@name",
                    view_xmlid,
                )
                self.assertTrue(stars)
                self.assertEqual(set(stars), {"is_user_favorite"})

    def test_the_search_offers_featured_and_my_favorites(self):
        for model in ("product.template", "product.product"):
            with self.subTest(model=model):
                filters = {
                    node.get("name"): node.get("domain")
                    for node in self._arch_nodes(model, "search", "//filter")
                }
                self.assertEqual(
                    filters.get("featured"), "[('is_featured', '=', True)]"
                )
                self.assertEqual(
                    filters.get("my_favorites"), "[('is_user_favorite', '=', True)]"
                )

    def test_featured_and_favorite_read_differently(self):
        for model in ("product.template", "product.product"):
            with self.subTest(model=model):
                labels = self.env[model].fields_get(
                    ["is_featured", "is_user_favorite"], ["string"]
                )
                self.assertEqual(labels["is_featured"]["string"], "Featured")
                self.assertNotEqual(labels["is_user_favorite"]["string"], "Featured")

    def test_a_variant_stars_its_template_without_write_access(self):
        variant = self.template.product_variant_ids[:1]
        as_alice = variant.with_user(self.alice)
        with self.assertRaises(AccessError):
            as_alice.write({"default_code": "nope"})

        as_alice.write({"is_user_favorite": True})

        self.assertTrue(self.template.with_user(self.alice).is_user_favorite)
        self.assertTrue(as_alice.is_user_favorite)
        self.assertFalse(variant.with_user(self.bob).is_user_favorite)
