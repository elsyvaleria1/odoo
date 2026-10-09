from lxml import html

from odoo import http
from odoo.fields import Command
from odoo.libs.json import loads as json_loads
from odoo.tests import tagged

from odoo.addons.base.tests.common import HttpCaseWithUserPortal
from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.web.controllers.utils import PARTIAL_NAVIGATION_HEADER


@tagged("post_install", "-at_install")
class TestWebsiteSaleReorderFromPortal(HttpCaseWithUserPortal):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.website = cls.env["website"].get_current_website()
        cls.website.write(
            {
                "prevent_zero_price_sale": False,
            }
        )
        cls.empty_cart = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner_portal.id,
            }
        )
        cls.product_1, cls.product_2 = cls.env["product.product"].create(
            [
                {
                    "name": "Reorder Product 1",
                    "sale_ok": True,
                    "website_published": True,
                },
                {
                    "name": "Reorder Product 2",
                    "sale_ok": True,
                    "website_published": True,
                },
            ]
        )

    def test_website_sale_reorder_from_portal(self):
        no_variant_attribute = self.env["product.attribute"].create(
            {
                "name": "Size",
                "create_variant": "no_variant",
                "value_ids": [
                    Command.create({"name": "S"}),
                    Command.create({"name": "M"}),
                    Command.create({"name": "L", "is_custom": True}),
                ],
            }
        )
        s, _m, l = no_variant_attribute.value_ids
        no_variant_template = self.env["product.template"].create(
            {
                "name": "Sofa",
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": no_variant_attribute.id,
                            "value_ids": [
                                Command.set(no_variant_attribute.value_ids.ids)
                            ],
                        }
                    )
                ],
            }
        )
        ptavs = no_variant_template.attribute_line_ids.product_template_value_ids
        ptav_s = ptavs.filtered(lambda ptav: ptav.product_attribute_value_id == s)
        ptav_l = ptavs.filtered(lambda ptav: ptav.product_attribute_value_id == l)
        user_admin = self.env.ref("base.user_admin")
        order = self.empty_cart
        order.write(
            {
                "partner_id": user_admin.partner_id.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_1.id,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_2.id,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": no_variant_template.product_variant_id.id,
                            "product_no_variant_attribute_value_ids": [
                                Command.set(ptav_s.ids)
                            ],
                        }
                    ),
                    Command.create(
                        {
                            "product_id": no_variant_template.product_variant_id.id,
                            "product_no_variant_attribute_value_ids": [
                                Command.set(ptav_l.ids)
                            ],
                            "product_custom_attribute_value_ids": [
                                Command.create(
                                    {
                                        "custom_product_template_attribute_value_id": ptav_l.id,
                                        "custom_value": "Whatever",
                                    }
                                )
                            ],
                        }
                    ),
                ],
            }
        )
        order.action_confirm()
        order.message_subscribe(user_admin.partner_id.ids)

        self.start_tour("/", "website_sale_reorder_from_portal", login="admin")

        reorder_cart = self.env["sale.order"].search(
            [("website_id", "!=", False)], limit=1
        )
        previous_lines = order.line_ids
        order_lines = reorder_cart.line_ids

        self.assertEqual(previous_lines.product_id, order_lines.product_id)
        self.assertEqual(
            previous_lines.product_id.sorted("id").mapped("name"),
            order_lines.product_id.sorted("id").mapped("name"),
        )
        self.assertEqual(
            previous_lines.product_no_variant_attribute_value_ids,
            order_lines.product_no_variant_attribute_value_ids,
        )

    def test_is_reorder_allowed(self):
        line_published_product = Command.create(
            {
                "product_id": self.product_1.id,
            }
        )
        self.product_2.active = False
        line_archived_product = Command.create(
            {
                "product_id": self.product_2.id,
            }
        )
        line_section = Command.create(
            {
                "name": "Free line",
                "display_type": "line_section",
            }
        )
        line_downpayment = Command.create(
            {
                "name": "Down with the Payment",
                "is_downpayment": True,
                "price_unit": 5,
            }
        )

        order = self.empty_cart.with_user(self.user_portal).sudo()
        order.line_ids = [line_section]
        order.action_confirm()

        with MockRequest(self.env, website=self.website):
            self.assertFalse(
                order._is_reorder_allowed(),
                "Reordering a line section should not be allowed",
            )

            order.line_ids = [line_archived_product]
            self.assertFalse(
                order._is_reorder_allowed(),
                "Reordering an archived product should not be allowed",
            )

            order.line_ids = [line_published_product]
            self.assertTrue(
                order._is_reorder_allowed(),
                "Reordering a published product should be allowed",
            )

            self.product_1.website_published = False
            self.assertFalse(
                order._is_reorder_allowed(),
                "Reordering an unpublished product should not be allowed",
            )

            order.line_ids = [line_downpayment]
            self.assertFalse(
                order._is_reorder_allowed(),
                "Reordering a down payment should not be allowed",
            )

            self.product_2.write({"active": True, "list_price": 0.0})
            self.assertTrue(
                order._is_reorder_allowed(),
                "Reordering a zero-priced product should be allowed when enabled",
            )

    def _reorder(self, order, access_token=None):
        return self.url_open(
            "/my/orders/reorder",
            data={
                "csrf_token": http.Request.csrf_token(self),
                "order_id": order.id,
                "access_token": access_token or "",
            },
            allow_redirects=False,
        )

    def test_an_order_out_of_reach_is_not_found(self):
        self.authenticate(None, None)

        refused = self._reorder(self.empty_cart, access_token="not-the-token")

        self.assertEqual(refused.status_code, 404)

    def test_a_visitor_with_the_order_s_link_reorders_it(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_portal.id,
                "line_ids": [Command.create({"product_id": self.product_2.id})],
            }
        )
        self.authenticate(None, None)

        response = self._reorder(
            order, access_token=order._portal_get_or_create_token()
        )

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/shop/cart"))

    def test_a_reorder_goes_to_the_cart_which_reports_it_once(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_portal.id,
                "line_ids": [Command.create({"product_id": self.product_1.id})],
            }
        )
        self.authenticate("portal", "portal")

        response = self._reorder(order)
        refreshed = self.url_open(
            "/shop/cart", headers={PARTIAL_NAVIGATION_HEADER: "1"}
        )
        visited = self.url_open("/shop/cart")
        revisited = self.url_open("/shop/cart")

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/shop/cart"))
        # another tab refreshing its cart in place does not take the report
        self.assertNotIn("data-add-to-cart-tracking", refreshed.text)
        reported = html.fromstring(visited.content).xpath(
            "//*[@data-add-to-cart-tracking]/@data-add-to-cart-tracking"
        )
        self.assertEqual(
            [item["item_name"] for item in json_loads(reported[0])],
            ["Reorder Product 1"],
        )
        self.assertNotIn("data-add-to-cart-tracking", revisited.text)
