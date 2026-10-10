from lxml import html

from odoo.tests import tagged

from odoo.addons.website_sale.tests.common import MockRequest
from odoo.addons.website_sale_collect.tests.common import ClickAndCollectCommon


@tagged("post_install", "-at_install")
class TestSaveUnavailableForLater(ClickAndCollectCommon):
    def test_none_left_offers_saving_the_line_to_the_wishlist_from_the_same_form(self):
        order = self._create_in_store_delivery_order()
        with MockRequest(self.env, website=self.website) as req:
            req.wishlist = self.env["product.wishlist"]
            warning = html.fromstring(
                str(
                    self.env["ir.qweb"]._render(
                        "website_sale_collect.unavailable_products_warning",
                        {
                            "insufficient_stock_data": {order.line_ids: 0},
                            "wh_name": "Shop 1",
                            "is_selected": True,
                        },
                    )
                )
            )

        (form,) = warning.xpath("//form[contains(@class, 'o_wsc_update_qty_form')]")
        (save,) = form.xpath(".//button[contains(@class, 'o_wsc_save_for_later')]")
        self.assertEqual(save.get("formaction"), "/shop/wishlist/save_for_later")
        self.assertEqual(save.get("type"), "submit")
        self.assertEqual(
            form.xpath(".//input[@name='line_id']/@value"), [str(order.line_ids.id)]
        )
