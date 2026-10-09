from odoo import http
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestSaveForLater(HttpCase):
    def test_a_cart_line_saved_for_later_moves_to_the_wishlist(self):
        product = self.env["product.product"].create(
            {
                "name": "PN Lamp",
                "list_price": 10.0,
                "is_published": True,
                "sale_ok": True,
            }
        )
        self.authenticate(None, None)
        self.call_jsonrpc(
            "/shop/cart/add",
            {
                "product_template_id": product.product_tmpl_id.id,
                "product_id": product.id,
                "quantity": 1,
            },
        )
        line = self.env["sale.order.line"].search(
            [("product_id", "=", product.id)], order="id desc", limit=1
        )

        response = self.url_open(
            "/shop/wishlist/save_for_later",
            data={"line_id": line.id, "csrf_token": http.Request.csrf_token(self)},
            headers={"X-Odoo-Fragments": "1"},
        )

        events = {event["name"]: event["detail"] for event in response.json()["events"]}
        self.assertEqual(
            events["website_sale_wishlist:product_added"], {"product_id": product.id}
        )
        self.assertFalse(line.exists())
        self.assertIn(
            product,
            self.env["product.wishlist"].sudo().search([]).product_id,
        )
