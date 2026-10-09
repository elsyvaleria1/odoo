from odoo import http
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCartLineForm(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create(
            {
                "name": "PN Crate",
                "list_price": 10.0,
                "is_published": True,
                "sale_ok": True,
            }
        )

    def setUp(self):
        super().setUp()
        self.authenticate(None, None)
        self.call_jsonrpc(
            "/shop/cart/add",
            {
                "product_template_id": self.product.product_tmpl_id.id,
                "product_id": self.product.id,
                "quantity": 2,
            },
        )
        self.line = self.env["sale.order.line"].search(
            [("product_id", "=", self.product.id)], order="id desc", limit=1
        )

    def _post_line(self, headers=None, **values):
        return self.url_open(
            "/shop/cart/line",
            data={
                "line_id": self.line.id,
                "csrf_token": http.Request.csrf_token(self),
                **values,
            },
            headers=headers,
            allow_redirects=False,
        )

    def test_a_button_steps_the_line_and_returns_to_the_cart(self):
        response = self._post_line(quantity=2, delta=1)

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/shop/cart"))
        self.assertEqual(self.line.product_uom_qty, 3)

    def test_asked_in_place_it_answers_the_cart_fragments_and_events(self):
        response = self._post_line({"X-Odoo-Fragments": "1"}, quantity=5)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [fragment["key"] for fragment in payload["fragments"]],
            [
                "website_sale.cart_lines",
                "website_sale.total",
                "website_sale.quick_reorder_history",
            ],
        )
        events = {event["name"]: event["detail"] for event in payload["events"]}
        self.assertEqual(events["website_sale:cart_updated"]["cart_quantity"], 5)
        self.assertEqual(self.line.product_uom_qty, 5)

    def test_removing_the_last_line_sends_the_page_to_the_empty_cart(self):
        response = self._post_line({"X-Odoo-Fragments": "1"}, delete=1)

        payload = response.json()
        self.assertEqual(payload["fragments"], [])
        self.assertEqual(payload["redirect"], "/shop/cart")
        self.assertFalse(self.line.exists())
