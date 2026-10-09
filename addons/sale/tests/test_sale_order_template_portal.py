from lxml import html

from odoo import http
from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.sale.tests.common import SaleOrderTemplateCommon


@tagged("post_install", "-at_install")
class TestPortalQuoteOptionUpdate(HttpCase, SaleOrderTemplateCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.sale_order_with_option = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "display_type": "line_section",
                            "name": "Optional products",
                            "is_optional": True,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": cls.product.id,
                        }
                    ),
                ],
            }
        )
        cls.sale_order_with_option._portal_get_or_create_token()
        cls.optional_line = cls._get_optional_product_lines(cls.sale_order_with_option)

    def test_a_zero_optional_quantity_is_rendered_as_zero(self):
        self.optional_line.product_qty = 0
        self.assertTrue(self.optional_line._can_be_edited_on_portal())
        self.authenticate(None, None)
        page = self.url_open(self.sale_order_with_option.get_portal_url())
        [quantity] = html.fromstring(page.content).xpath(
            f"//form[.//input[@name='line_id'][@value='{self.optional_line.id}']]"
            "//input[contains(@class, 'js_quantity')]"
        )
        self.assertEqual(quantity.get("value"), "0")

    def _update_line(self, access_token=None, **values):
        return self.url_open(
            f"/my/orders/{self.sale_order_with_option.id}/line",
            data={
                "access_token": access_token
                or self.sale_order_with_option.access_token,
                "line_id": self.optional_line.id,
                "csrf_token": http.Request.csrf_token(self),
                **values,
            },
            allow_redirects=False,
        )

    def test_the_buttons_step_the_quantity_and_return_to_the_order(self):
        self.authenticate(None, None)
        quantity = self.optional_line.product_qty

        response = self._update_line(quantity=int(quantity), delta=1)

        self.assertEqual(response.status_code, 303)
        self.assertIn(
            self.sale_order_with_option.get_portal_url(), response.headers["Location"]
        )
        self.assertEqual(self.optional_line.product_qty, quantity + 1)
        self._update_line(quantity=int(quantity + 1), delta=-1)
        self.assertEqual(self.optional_line.product_qty, quantity)

    def test_a_typed_quantity_wins_over_the_button_enter_submits_with(self):
        self.authenticate(None, None)

        self._update_line(quantity=7, delta=-1)

        self.assertEqual(self.optional_line.product_qty, 7)

    def test_negative_input_quantity_is_clamped_to_zero(self):
        self.authenticate(None, None)

        self._update_line(quantity=-5)

        self.assertEqual(
            self.optional_line.product_qty,
            0,
            "a negative input_quantity must be clamped to 0, never applied as-is",
        )

    def test_an_order_out_of_reach_answers_nothing_and_changes_nothing(self):
        self.authenticate(None, None)
        quantity = self.optional_line.product_qty

        response = self._update_line(
            access_token="not-the-token", quantity=quantity + 3
        )

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/my"))
        self.assertEqual(self.optional_line.product_qty, quantity)
