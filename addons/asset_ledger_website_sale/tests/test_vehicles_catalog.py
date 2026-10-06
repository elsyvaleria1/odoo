import re

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestVehiclesCatalogTagLeak(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public_tag = cls.env["product.tag"].create(
            {"name": "SUV", "visible_to_customers": True}
        )
        cls.internal_tag = cls.env["product.tag"].create(
            {"name": "REVISAR-COSTO-ALTO", "visible_to_customers": False}
        )
        cls.product = cls.env["product.template"].create(
            {
                "name": "Test Vehicle",
                "is_published": True,
                "product_tag_ids": [(6, 0, [cls.public_tag.id, cls.internal_tag.id])],
            }
        )

    def _render_catalog(self, products, tags):
        return self.env["ir.qweb"]._render(
            "asset_ledger_website_sale.vehicles_catalog_grid",
            {"products": products, "vehicle_tags": tags},
        )

    def test_internal_tag_not_in_badge_or_data_attribute(self):
        html = self._render_catalog(self.product, self.public_tag)

        self.assertIn(
            self.public_tag.name,
            html,
            "the visible_to_customers tag should still render as the badge",
        )
        self.assertNotIn(
            self.internal_tag.name,
            html,
            "an internal tag's name leaked into the public catalog badge",
        )
        self.assertNotIn(
            f'data-m-tags="{self.internal_tag.id}"',
            html,
            "an internal tag's id leaked into data-m-tags",
        )
        match = re.search(r'data-m-tags="([^"]*)"', html)
        self.assertIsNotNone(match, "data-m-tags attribute not found in output")
        rendered_ids = match.group(1).split()
        self.assertNotIn(str(self.internal_tag.id), rendered_ids)
        self.assertIn(str(self.public_tag.id), rendered_ids)

    def test_product_with_only_internal_tags_shows_no_badge(self):
        internal_only_product = self.env["product.template"].create(
            {
                "name": "Test Vehicle Internal Only",
                "is_published": True,
                "product_tag_ids": [(6, 0, [self.internal_tag.id])],
            }
        )
        html = self._render_catalog(internal_only_product, self.env["product.tag"])
        self.assertNotIn("m-vehicle-card__badge", html)
        self.assertNotIn(self.internal_tag.name, html)
