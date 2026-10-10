from lxml import html

from odoo import http
from odoo.fields import Command
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.web.controllers.utils import FRAGMENTS_HEADER


@tagged("post_install", "-at_install")
class TestQuickReorderForm(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref("website.default_website")
        cls.buyer = new_test_user(
            cls.env, login="reorder_buyer", groups="base.group_portal"
        )
        cls.other = new_test_user(
            cls.env, login="reorder_other", groups="base.group_portal"
        )
        product_values = {"sale_ok": True, "website_published": True, "list_price": 10}
        cls.pen = cls.env["product.product"].create(
            {"name": "Reorder Pen", **product_values}
        )
        cls.side, cls.drink_a, cls.drink_b = cls.env["product.product"].create(
            [
                {"name": "Reorder Side", **product_values},
                {"name": "Reorder Drink A", **product_values},
                {"name": "Reorder Drink B", **product_values},
            ]
        )
        side_combo = cls.env["product.combo"].create(
            {
                "name": "Side",
                "combo_item_ids": [Command.create({"product_id": cls.side.id})],
            }
        )
        drink_combo = cls.env["product.combo"].create(
            {
                "name": "Drink",
                "combo_item_ids": [
                    Command.create({"product_id": cls.drink_a.id}),
                    Command.create({"product_id": cls.drink_b.id}),
                ],
            }
        )
        cls.side_item = side_combo.combo_item_ids
        cls.drink_b_item = drink_combo.combo_item_ids.filtered(
            lambda item: item.product_id == cls.drink_b
        )
        cls.menu = cls.env["product.product"].create(
            {
                "name": "Reorder Menu",
                "type": "combo",
                "combo_ids": [
                    Command.link(side_combo.id),
                    Command.link(drink_combo.id),
                ],
                **product_values,
            }
        )

    def _past_order(self, partner):
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "website_id": self.website.id,
                "line_ids": [
                    Command.create({"product_id": self.pen.id, "product_qty": 2}),
                    Command.create({"product_id": self.menu.id, "product_qty": 1}),
                ],
            }
        )
        menu_line = order.line_ids.filtered(lambda line: line.product_id == self.menu)
        for item in (self.side_item, self.drink_b_item):
            self.env["sale.order.line"].create(
                {
                    "order_id": order.id,
                    "product_id": item.product_id.id,
                    "product_qty": 1,
                    "linked_line_id": menu_line.id,
                    "combo_item_id": item.id,
                }
            )
        order.action_confirm()
        return order

    def _line(self, order, product):
        return order.line_ids.filtered(lambda line: line.product_id == product)

    def _quick_add(self, line, quantity="3", fragments=True):
        return self.url_open(
            "/shop/cart/quick_add",
            data={
                "csrf_token": http.Request.csrf_token(self),
                "line_id": line.id,
                "quantity": quantity,
            },
            headers={FRAGMENTS_HEADER: "1"} if fragments else None,
            allow_redirects=False,
        )

    def _cart(self):
        return self.env["sale.order"].search(
            [
                ("partner_id", "=", self.buyer.partner_id.id),
                ("state", "=", "draft"),
                ("website_id", "=", self.website.id),
            ],
            order="id desc",
            limit=1,
        )

    def _cart_lines(self):
        return {
            (line.product_id, line.combo_item_id, line.product_qty)
            for line in self._cart().line_ids
        }

    def test_a_past_line_is_added_at_the_chosen_quantity_and_answers_the_cart(self):
        order = self._past_order(self.buyer.partner_id)
        self.authenticate("reorder_buyer", "reorder_buyer")

        response = self._quick_add(self._line(order, self.pen))

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(
            [fragment["key"] for fragment in body["fragments"]],
            [
                "website_sale.cart_lines",
                "website_sale.shorter_cart_summary",
                "website_sale.quick_reorder_history",
            ],
        )
        (updated,) = (
            e for e in body["events"] if e["name"] == "website_sale:cart_updated"
        )
        self.assertTrue(updated["detail"]["quick_reorder"])
        self.assertEqual(body["data"]["cart_quantity"], 3)
        self.assertEqual(
            self._cart_lines(), {(self.pen, self.env["product.combo.item"], 3)}
        )

    def test_a_combo_comes_back_with_its_choices_at_the_chosen_quantity(self):
        order = self._past_order(self.buyer.partner_id)
        self.authenticate("reorder_buyer", "reorder_buyer")

        self._quick_add(self._line(order, self.menu), quantity="2")

        self.assertEqual(
            self._cart_lines(),
            {
                (self.menu, self.env["product.combo.item"], 2),
                (self.side, self.side_item, 2),
                (self.drink_b, self.drink_b_item, 2),
            },
        )

    def test_a_choice_no_longer_offered_is_not_added_back(self):
        order = self._past_order(self.buyer.partner_id)
        self.drink_b.active = False
        self.authenticate("reorder_buyer", "reorder_buyer")

        self._quick_add(self._line(order, self.menu), quantity="1")

        self.assertNotIn(self.drink_b, self._cart().line_ids.product_id)
        self.assertIn(self.side, self._cart().line_ids.product_id)

    def test_order_again_builds_the_combo_the_same_way(self):
        order = self._past_order(self.buyer.partner_id)
        self.drink_b.active = False
        self.authenticate("reorder_buyer", "reorder_buyer")

        response = self.url_open(
            "/my/orders/reorder",
            data={"csrf_token": http.Request.csrf_token(self), "order_id": order.id},
            allow_redirects=False,
        )

        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(
            self._cart_lines(),
            {
                (self.pen, self.env["product.combo.item"], 2),
                (self.menu, self.env["product.combo.item"], 1),
                (self.side, self.side_item, 1),
            },
        )

    def test_a_line_of_someone_else_s_order_is_not_found(self):
        order = self._past_order(self.other.partner_id)
        self.authenticate("reorder_buyer", "reorder_buyer")

        self.assertEqual(self._quick_add(self._line(order, self.pen)).status_code, 404)

    def test_no_quantity_is_refused_with_a_message(self):
        order = self._past_order(self.buyer.partner_id)
        self.authenticate("reorder_buyer", "reorder_buyer")

        response = self._quick_add(self._line(order, self.pen), quantity="0")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["error"]["message"], "Choose a quantity to add."
        )

    def test_without_javascript_the_line_comes_back_to_the_cart(self):
        order = self._past_order(self.buyer.partner_id)
        self.authenticate("reorder_buyer", "reorder_buyer")

        response = self._quick_add(self._line(order, self.pen), fragments=False)

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/shop/cart"))

    def test_the_cart_lists_each_past_line_as_a_form_of_its_own(self):
        order = self._past_order(self.buyer.partner_id)
        self.authenticate("reorder_buyer", "reorder_buyer")
        self._quick_add(self._line(order, self.pen))

        page = html.fromstring(self.url_open("/shop/cart").content)

        (form,) = page.xpath("//form[contains(@class, 'o_wsale_quick_reorder_line')]")
        self.assertEqual(form.get("action"), "/shop/cart/quick_add")
        self.assertEqual(
            form.xpath(".//input[@name='line_id']/@value"),
            [str(self._line(order, self.menu).id)],
        )
        self.assertFalse(page.xpath("//form//form"))
