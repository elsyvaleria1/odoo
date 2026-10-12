from odoo.tests import tagged

from .common import TestTradeOrderCase


@tagged("post_install", "-at_install")
class TestCatalog(TestTradeOrderCase):
    def test_catalog_domain_includes_ok_field(self):
        order = self._make_order()

        domain = order._get_domain_product_catalog()

        self.assertIn(("sale_ok", "=", True), list(domain))

    def test_add_extra_context_has_common_keys(self):
        order = self._make_order()

        ctx = order._prepare_catalog_extra_context()

        for key in (
            "product_catalog_currency_id",
            "product_catalog_digits",
            "show_sections",
        ):
            self.assertIn(key, ctx)

    def test_update_existing_line_quantity(self):
        order = self._make_order()
        line = self._make_line(order=order, product_qty=1.0)

        order._update_order_line_info(self.product.id, 4.0)

        self.assertEqual(line.product_qty, 4.0)

    def test_update_zero_quantity_removes_line_in_draft(self):
        order = self._make_order()
        line = self._make_line(order=order, product_qty=2.0)

        price = order._update_order_line_info(self.product.id, 0.0)

        self.assertFalse(line.exists())
        self.assertEqual(price, self.product.list_price)

    def test_catalog_lines_data_empty_recordset(self):
        data = self.env["test_trade.order.line"]._get_product_catalog_lines_data()

        self.assertEqual(data, {"quantity": 0})

    def test_catalog_lines_data_single_line(self):
        line = self._make_line(product_qty=3.0, price_unit=42.0)

        data = line._get_product_catalog_lines_data()

        self.assertEqual(data["quantity"], 3.0)
        self.assertEqual(data["price"], 42.0)
        self.assertFalse(data["readOnly"])

    def test_catalog_lines_data_multi_line_aggregates_quantity(self):
        order = self._make_order()
        lines = self._make_line(order=order, product_qty=2.0) + self._make_line(
            order=order, product_qty=5.0
        )

        data = lines._get_product_catalog_lines_data()

        self.assertEqual(data["quantity"], 7.0)
        self.assertTrue(data["readOnly"])

    def test_update_creates_line_when_absent(self):
        order = self._make_order()
        self.assertFalse(order.line_ids)

        price = order._update_order_line_info(self.product.id, 3.0)

        self.assertEqual(len(order.line_ids), 1)
        line = order.line_ids
        self.assertEqual(line.product_id, self.product)
        self.assertEqual(line.product_qty, 3.0)
        self.assertEqual(price, line.price_unit)

    def test_update_created_line_gets_a_sequence(self):
        order = self._make_order()
        first = self._make_line(order=order, product_qty=1.0)
        other_product = self.env["product.product"].create(
            {"name": "BO Product 2", "list_price": 50.0},
        )

        order._update_order_line_info(other_product.id, 2.0)

        created = order.line_ids.filtered(lambda l: l.product_id == other_product)
        self.assertEqual(len(created), 1)
        self.assertGreaterEqual(created.sequence, first.sequence)

    def test_update_zero_quantity_on_absent_line_returns_default_price(self):
        order = self._make_order()

        price = order._update_order_line_info(self.product.id, 0.0)

        self.assertFalse(order.line_ids)
        self.assertEqual(price, self.product.list_price)

    def test_update_zero_quantity_keeps_line_when_state_not_editable(self):
        order = self._make_order()
        line = self._make_line(order=order, product_qty=2.0)
        order.state = "done"
        self.assertNotIn(order.state, order._get_catalog_editable_states())

        order._update_order_line_info(self.product.id, 0.0)

        self.assertTrue(line.exists(), "the line must survive outside draft")
        self.assertEqual(line.product_qty, 0.0)

    def test_catalog_is_editable_on_a_live_order(self):
        order = self._make_order()
        line = self._make_line(order=order, product_qty=2.0)

        self.assertFalse(order._is_readonly())
        self.assertFalse(line._get_catalog_single_line_data()["readOnly"])

    def test_catalog_is_readonly_on_a_cancelled_order(self):
        order = self._make_order()
        line = self._make_line(order=order, product_qty=2.0)
        order.action_cancel()

        self.assertTrue(order._is_readonly())
        self.assertTrue(line._get_catalog_single_line_data()["readOnly"])
