from lxml import html

from odoo.tests import tagged

from odoo.addons.website_sale.tests.common import MockRequest
from odoo.addons.website_sale_collect.tests.common import ClickAndCollectCommon


@tagged("post_install", "-at_install")
class TestUnavailableProductsForm(ClickAndCollectCommon):
    def _render_warning(self, available_qty):
        order = self._create_in_store_delivery_order()
        with MockRequest(self.env, website=self.website) as req:
            if "product.wishlist" in self.env:
                req.wishlist = self.env["product.wishlist"]
            return html.fromstring(
                str(
                    self.env["ir.qweb"]._render(
                        "website_sale_collect.unavailable_products_warning",
                        {
                            "insufficient_stock_data": {order.line_ids: available_qty},
                            "wh_name": "Shop 1",
                            "is_selected": True,
                        },
                    )
                )
            ), order.line_ids

    def test_updating_to_the_available_stock_is_a_form_back_to_the_checkout(self):
        warning, line = self._render_warning(3)

        (form,) = warning.xpath("//form[contains(@class, 'o_wsc_update_qty_form')]")
        self.assertEqual(
            (form.get("method"), form.get("action")), ("post", "/shop/cart/line")
        )
        fields = {
            field.get("name"): field.get("value")
            for field in form.xpath(".//input[@type='hidden']")
        }
        self.assertEqual(
            {name: fields.get(name) for name in ("line_id", "quantity", "redirect")},
            {"line_id": str(line.id), "quantity": "3", "redirect": "/shop/checkout"},
        )
        self.assertTrue(form.xpath(".//button[@type='submit']"))

    def test_none_left_offers_removing_the_line(self):
        warning, _line = self._render_warning(0)

        (form,) = warning.xpath("//form[contains(@class, 'o_wsc_update_qty_form')]")
        self.assertEqual(form.xpath(".//input[@name='quantity']/@value"), ["0"])
        self.assertIn("Remove", form.xpath("string(.//button[@type='submit'][1])"))

    def test_the_delivery_form_holds_no_form_of_its_own(self):
        with MockRequest(self.env, website=self.website):
            rendered = html.fromstring(
                str(
                    self.env["ir.qweb"]._render(
                        "website_sale.delivery_form",
                        {
                            "delivery_methods": self.env["delivery.carrier"],
                            "order": self.env["sale.order"],
                        },
                    )
                )
            )

        self.assertTrue(rendered.xpath("//div[@id='o_delivery_form']"))
        self.assertFalse(rendered.xpath("//form[@id='o_delivery_form']"))
