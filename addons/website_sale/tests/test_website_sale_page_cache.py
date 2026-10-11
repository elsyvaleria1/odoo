from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCartStaysOutOfThePageCache(HttpCase):
    def test_an_expired_page_refilled_by_a_cart_holder_is_not_served_to_others(self):
        page = self.env["website.page"].create(
            {
                "name": "Cart cache probe",
                "url": "/cart-cache-probe",
                "is_published": True,
                "type": "qweb",
                "key": "website_sale.cart_cache_probe",
                "arch": '<t t-name="website_sale.cart_cache_probe">'
                '<t t-call="website.layout">CARTCACHEBODY</t></t>',
            }
        )
        product = self.env["product.template"].create(
            {"name": "Cart cache product", "is_published": True, "sale_ok": True}
        )
        self.env.flush_all()
        self.env.registry.clear_cache()
        WebsitePage = type(self.env["website.page"])

        self.assertIn("CARTCACHEBODY", self.url_open(page.url).text)
        visitor_cookies = self.opener.cookies.copy()

        self.opener.cookies.clear()
        response = self.url_open(
            "/shop/cart/add",
            json={
                "params": {
                    "product_template_id": product.id,
                    "product_id": product.product_variant_id.id,
                    "quantity": 1,
                }
            },
        )
        self.assertNotIn("error", response.json())
        order = self.env["sale.order"].search([], order="id desc", limit=1)
        with patch.object(WebsitePage, "_CACHE_DURATION", -1):
            holder_page = self.url_open(page.url).text
        self.assertIn(f'data-order-id="{order.id}"', holder_page)

        self.opener.cookies = visitor_cookies
        visitor_page = self.url_open(page.url).text
        self.assertIn("CARTCACHEBODY", visitor_page)
        self.assertNotIn(f'data-order-id="{order.id}"', visitor_page)
