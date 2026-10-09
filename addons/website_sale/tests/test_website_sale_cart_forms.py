from odoo import http
from odoo.libs.json import loads as json_loads
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale.tests.common import MockRequest


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

    def test_a_cart_change_tells_the_visitors_other_tabs_by_bus(self):
        self._post_line({"X-Odoo-Tab": "tab-a"}, quantity=4)

        channel = [self.env.cr.dbname, "sale.order", self.line.order_id.id]
        notices = [
            json_loads(row.message)
            for row in self.env["bus.bus"].sudo().search([])
            if json_loads(row.channel) == channel
        ]
        notice = next(
            notice["payload"]
            for notice in reversed(notices)
            if notice["type"] == "fragment.invalidated"
        )
        self.assertEqual(notice["origin"], "tab-a")
        self.assertIn("website_sale.cart_lines", notice["keys"])
        self.assertEqual(
            notice["events"]["website_sale:cart_updated"]["cart_quantity"], 4
        )


@tagged("post_install", "-at_install")
class TestCartBusChannel(HttpCase):
    def test_a_session_with_a_cart_hears_its_channel(self):
        website = self.env["website"].get_current_website()
        order = self.env["sale.order"].create(
            {
                "partner_id": self.env.ref("base.public_partner").id,
                "website_id": website.id,
            }
        )
        with MockRequest(self.env, website=website, sale_order_id=order.id):
            channels = self.env["ir.websocket"]._get_bus_channels([])
        self.assertIn(order, channels)


@tagged("post_install", "-at_install")
class TestCouponForm(TestCartLineForm):
    def _apply(self, promo, headers=None):
        return self.url_open(
            "/shop/pricelist?r=/shop/cart",
            data={"csrf_token": http.Request.csrf_token(self), "promo": promo},
            headers=headers,
            allow_redirects=False,
        )

    def test_an_unknown_code_returns_to_the_page_that_says_so(self):
        response = self._apply("NO-SUCH-CODE")

        self.assertEqual(response.status_code, 303)
        self.assertTrue(
            response.headers["Location"].endswith("/shop/cart?code_not_available=1")
        )

    def test_asked_in_place_the_code_answers_the_cart_and_its_events(self):
        response = self._apply("NO-SUCH-CODE", {"X-Odoo-Fragments": "1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        fragments = {
            fragment["key"]: fragment["html"] for fragment in payload["fragments"]
        }
        self.assertEqual(
            set(fragments),
            {
                "website_sale.cart_lines",
                "website_sale.cart_summary_content",
                "website_sale.total",
                "website_sale.total_no_promotions",
            },
        )
        # the total the coupon form sits in says what the redirect's query would
        self.assertIn('name="coupon_code"', fragments["website_sale.total"])
        self.assertIn("alert-danger", fragments["website_sale.total"])
        events = {event["name"] for event in payload["events"]}
        self.assertEqual(
            events, {"website_sale:cart_updated", "payment:amount_changed"}
        )
