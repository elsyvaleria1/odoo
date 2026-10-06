from unittest.mock import patch

from odoo.tests import tagged

from .common import MockRequest, WebsiteSaleCommon


@tagged("post_install", "-at_install")
class TestQuickAddVisibility(WebsiteSaleCommon):
    def test_price_policy_returns_boolean_for_both_product_models(self):
        template = self.env["product.template"].create(
            {"name": "Quick add price fixture", "sale_ok": True}
        )
        with MockRequest(self.env, website=self.website):
            for product in (template, template.product_variant_id):
                for prevent_zero in (False, True):
                    self.website.prevent_zero_price_sale = prevent_zero
                    for price in (0.0, 19.5, -2.0):
                        with (
                            self.subTest(
                                model=product._name,
                                prevent_zero=prevent_zero,
                                price=price,
                            ),
                            patch.object(
                                type(product),
                                "_get_contextual_price",
                                return_value=price,
                            ) as get_price,
                        ):
                            result = product._can_show_website_quick_add()
                            self.assertIs(result, not prevent_zero or bool(price))
                            self.assertEqual(get_price.call_count, int(prevent_zero))

    def test_not_for_sale_skips_price_lookup(self):
        template = self.env["product.template"].create(
            {"name": "Quick add ineligible fixture", "sale_ok": False}
        )
        self.website.prevent_zero_price_sale = True
        with MockRequest(self.env, website=self.website):
            for product in (template, template.product_variant_id):
                with patch.object(type(product), "_get_contextual_price") as get_price:
                    self.assertIs(product._can_show_website_quick_add(), False)
                    get_price.assert_not_called()

    def test_extension_restrictions_remain_effective(self):
        template = self.env["product.template"].create(
            {"name": "Quick add extension fixture", "sale_ok": True}
        )
        self.website.prevent_zero_price_sale = False
        with MockRequest(self.env, website=self.website):
            for product in (template, template.product_variant_id):
                self.assertIs(product._can_show_website_quick_add(), True)
                for name, value in (
                    ("_is_sold_out", True),
                    ("_website_can_be_added", False),
                    ("_can_be_added_to_current_cart", False),
                ):
                    target = product
                    if name == "_can_be_added_to_current_cart":
                        target = template.product_variant_id
                    if not hasattr(target, name):
                        continue
                    with (
                        self.subTest(model=product._name, restriction=name),
                        patch.object(type(target), name, return_value=value),
                    ):
                        self.assertIs(product._can_show_website_quick_add(), False)

    def test_stored_templates_use_the_predicate(self):
        for xmlid in ("website_sale.shop_product_buttons",):
            view = self.env.ref(xmlid)
            arch = view.arch_db
            self.assertIn("_can_show_website_quick_add", arch)
            self.assertNotIn("_website_show_quick_add", arch)
