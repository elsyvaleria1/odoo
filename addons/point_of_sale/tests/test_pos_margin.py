import logging
import time
from unittest.mock import patch

import odoo

from odoo.addons.point_of_sale.tests.common import TestPoSCommon

_logger = logging.getLogger(__name__)


@odoo.tests.tagged("post_install", "-at_install")
class TestPosMargin(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config

        self.stock_location = (
            self.env["stock.warehouse"]
            .create(
                {
                    "partner_id": self.env.user.partner_id.id,
                    "name": "Stock location",
                    "code": "WH",
                }
            )
            .lot_stock_id
        )
        self.customer_location = self.env.ref("stock.stock_location_customers")
        self.supplier_location = self.env.ref("stock.stock_location_suppliers")
        self.uom_unit = self.env.ref("uom.product_uom_unit")

    def _synced_orders(self):
        return self.pos_session.order_ids.sorted("id")

    def test_positive_margin(self):

        product1 = self.create_product("Product 1", self.categ_basic, 10, 5)
        product2 = self.create_product("Product 2", self.categ_basic, 50, 30)

        self.open_new_session()

        orders = [
            self.create_ui_order_data([(product1, 1)]),
            self.create_ui_order_data([(product2, 1)]),
            self.create_ui_order_data([(product1, 2), (product2, 2)]),
        ]

        self.env["pos.order"].sync_from_ui(orders)

        self.assertEqual(self._synced_orders()[0].margin, 5)
        self.assertEqual(self._synced_orders()[1].margin, 20)
        self.assertEqual(self._synced_orders()[2].margin, 50)

        self.assertEqual(self._synced_orders()[0].margin_percent, 0.5)
        self.assertEqual(self._synced_orders()[1].margin_percent, 0.4)
        self.assertEqual(round(self._synced_orders()[2].margin_percent, 2), 0.42)

        self.pos_session.action_pos_session_closing_control()

    def test_negative_margin(self):

        product1 = self.create_product("Product 1", self.categ_basic, 10, 15)
        product2 = self.create_product("Product 2", self.categ_basic, 50, 100)

        self.open_new_session()

        orders = [
            self.create_ui_order_data([(product1, 1)]),
            self.create_ui_order_data([(product2, 1)]),
            self.create_ui_order_data([(product1, 2), (product2, 2)]),
        ]

        self.env["pos.order"].sync_from_ui(orders)

        self.assertEqual(self._synced_orders()[0].margin, -5)
        self.assertEqual(self._synced_orders()[1].margin, -50)
        self.assertEqual(self._synced_orders()[2].margin, -110)

        self.assertEqual(self._synced_orders()[0].margin_percent, -0.5)
        self.assertEqual(self._synced_orders()[1].margin_percent, -1)
        self.assertEqual(round(self._synced_orders()[2].margin_percent, 2), -0.92)

        self.pos_session.action_pos_session_closing_control()

    def test_full_margin(self):

        product1 = self.create_product("Product 1", self.categ_basic, 10)
        product2 = self.create_product("Product 2", self.categ_basic, 50)

        self.open_new_session()

        orders = [
            self.create_ui_order_data([(product1, 1)]),
            self.create_ui_order_data([(product2, 1)]),
            self.create_ui_order_data([(product1, 2), (product2, 2)]),
        ]

        self.env["pos.order"].sync_from_ui(orders)

        self.assertEqual(self._synced_orders()[0].margin, 10)
        self.assertEqual(self._synced_orders()[1].margin, 50)
        self.assertEqual(self._synced_orders()[2].margin, 120)

        self.assertEqual(self._synced_orders()[0].margin_percent, 1)
        self.assertEqual(self._synced_orders()[1].margin_percent, 1)
        self.assertEqual(self._synced_orders()[2].margin_percent, 1)

        self.pos_session.action_pos_session_closing_control()

    def test_tax_margin(self):

        product1 = self.create_product(
            "Product 1", self.categ_basic, 10, 5, self.taxes["tax7"].ids
        )
        product2 = self.create_product(
            "Product 2", self.categ_basic, 55, 30, self.taxes["tax10"].ids
        )

        self.open_new_session()

        orders = [
            self.create_ui_order_data([(product1, 1)]),
            self.create_ui_order_data([(product2, 1)]),
            self.create_ui_order_data([(product1, 2), (product2, 2)]),
        ]

        self.env["pos.order"].sync_from_ui(orders)

        self.assertEqual(self._synced_orders()[0].margin, 5)
        self.assertEqual(self._synced_orders()[1].margin, 20)
        self.assertEqual(self._synced_orders()[2].margin, 50)

        self.assertEqual(self._synced_orders()[0].margin_percent, 0.5)
        self.assertEqual(self._synced_orders()[1].margin_percent, 0.4)
        self.assertEqual(round(self._synced_orders()[2].margin_percent, 2), 0.42)

        self.pos_session.action_pos_session_closing_control()

    def test_other_currency_margin(self):

        current_config = self.config
        self.config = self.other_currency_config

        product1 = self.create_product("Product 1", self.categ_basic, 10, 5)
        product2 = self.create_product("Product 2", self.categ_basic, 50, 30)

        self.open_new_session()

        orders = [
            self.create_ui_order_data([(product1, 1)]),
            self.create_ui_order_data([(product2, 1)]),
            self.create_ui_order_data([(product1, 2), (product2, 2)]),
        ]

        self.env["pos.order"].sync_from_ui(orders)

        self.assertEqual(self._synced_orders()[0].margin, 2.5)
        self.assertEqual(self._synced_orders()[1].margin, 10)
        self.assertEqual(self._synced_orders()[2].margin, 25)

        self.assertEqual(self._synced_orders()[0].margin_percent, 0.5)
        self.assertEqual(self._synced_orders()[1].margin_percent, 0.4)
        self.assertEqual(round(self._synced_orders()[2].margin_percent, 2), 0.42)

        self.pos_session.action_pos_session_closing_control()

        self.config = current_config

    def test_tax_and_other_currency_margin(self):

        current_config = self.config
        self.config = self.other_currency_config

        product1 = self.create_product(
            "Product 1", self.categ_basic, 10, 5, self.taxes["tax7"].ids
        )
        product2 = self.create_product(
            "Product 2", self.categ_basic, 55, 30, self.taxes["tax10"].ids
        )

        self.open_new_session()

        orders = [
            self.create_ui_order_data([(product1, 1)]),
            self.create_ui_order_data([(product2, 1)]),
            self.create_ui_order_data([(product1, 2), (product2, 2)]),
        ]

        self.env["pos.order"].sync_from_ui(orders)

        self.assertEqual(self._synced_orders()[0].margin, 2.5)
        self.assertEqual(self._synced_orders()[1].margin, 10)
        self.assertEqual(self._synced_orders()[2].margin, 25)

        self.assertEqual(self._synced_orders()[0].margin_percent, 0.5)
        self.assertEqual(self._synced_orders()[1].margin_percent, 0.4)
        self.assertEqual(self._synced_orders()[2].margin_percent, 0.4167)

        self.pos_session.action_pos_session_closing_control()

        self.config = current_config

    def test_return_margin(self):

        product1 = self.create_product("Product 1", self.categ_basic, 10, 5)
        product2 = self.create_product("Product 2", self.categ_basic, 50, 30)

        self.open_new_session()

        orders = [
            self.create_ui_order_data([(product1, -1)]),
            self.create_ui_order_data([(product2, -1)]),
            self.create_ui_order_data([(product1, -2), (product2, -2)]),
        ]

        self.env["pos.order"].sync_from_ui(orders)

        self.assertEqual(self._synced_orders()[0].margin, -5)
        self.assertEqual(self._synced_orders()[1].margin, -20)
        self.assertEqual(self._synced_orders()[2].margin, -50)

        self.assertEqual(self._synced_orders()[0].margin_percent, 0.5)
        self.assertEqual(self._synced_orders()[1].margin_percent, 0.4)
        self.assertEqual(round(self._synced_orders()[2].margin_percent, 2), 0.42)

        self.pos_session.action_pos_session_closing_control()

    def test_fifo_margin_real_time(self):

        product1 = self.create_product("Product 1", self.categ_anglo, 10, 5)
        product2 = self.create_product("Product 2", self.categ_basic, 50, 30)

        move1 = (
            self.env["stock.move"]
            .create(
                {
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "product_id": product1.id,
                    "product_uom_id": self.uom_unit.id,
                    "product_uom_qty": 2,
                    "value_manual": 2 * 3,
                    "price_unit": 3,
                }
            )
            .sudo()
        )
        move1._action_confirm()
        move1._action_assign()
        move1.move_line_ids.quantity = 2
        move1.picked = True
        move1._action_done()

        move2 = (
            self.env["stock.move"]
            .create(
                {
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "product_id": product1.id,
                    "product_uom_id": self.uom_unit.id,
                    "product_uom_qty": 1,
                    "value_manual": 1 * 7,
                    "price_unit": 7,
                }
            )
            .sudo()
        )
        move2._action_confirm()
        move2._action_assign()
        move2.move_line_ids.quantity = 1
        move2.picked = True
        move2._action_done()

        self.open_new_session()

        orders = [
            self.create_ui_order_data([(product1, 1), (product2, 1)]),
            self.create_ui_order_data([(product1, 2)]),
        ]

        self.env["pos.order"].sync_from_ui(orders)

        self.assertEqual(self._synced_orders()[0].margin, 27)
        self.assertEqual(self._synced_orders()[1].margin, 10)

        self.assertEqual(self._synced_orders()[0].margin_percent, 0.45)
        self.assertEqual(self._synced_orders()[1].margin_percent, 0.5)

        self.pos_session.action_pos_session_closing_control()

    def test_avco_margin_closing_time(self):

        self.categ_anglo.property_cost_method = "average"
        product1 = self.create_product("Product 1", self.categ_anglo, 10, 5)
        product2 = self.create_product("Product 2", self.categ_basic, 50, 30)
        self.env.company.point_of_sale_config_id.point_of_sale_update_stock_quantities = "closing"

        move1 = (
            self.env["stock.move"]
            .create(
                {
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "product_id": product1.id,
                    "product_uom_id": self.uom_unit.id,
                    "product_uom_qty": 2,
                    "value_manual": 2 * 3,
                    "price_unit": 3,
                }
            )
            .sudo()
        )
        move1._action_confirm()
        move1._action_assign()
        move1.move_line_ids.quantity = 2
        move1.picked = True
        move1._action_done()

        move2 = (
            self.env["stock.move"]
            .create(
                {
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "product_id": product1.id,
                    "product_uom_id": self.uom_unit.id,
                    "product_uom_qty": 1,
                    "value_manual": 1 * 6,
                    "price_unit": 6,
                }
            )
            .sudo()
        )
        move2._action_confirm()
        move2._action_assign()
        move2.move_line_ids.quantity = 1
        move2.picked = True
        move2._action_done()

        self.open_new_session()

        orders = [
            self.create_ui_order_data([(product1, 1), (product2, 1)]),
            self.create_ui_order_data([(product1, 2)]),
        ]

        self.env["pos.order"].sync_from_ui(orders)

        self.assertEqual(self._synced_orders()[0].margin, 0)
        self.assertEqual(self._synced_orders()[1].margin, 0)

        self.assertEqual(self._synced_orders()[1].margin_percent, 0)
        self.assertEqual(self._synced_orders()[1].margin_percent, 0)

        total_cash_payment = sum(
            self.pos_session.mapped("order_ids.payment_ids")
            .filtered(lambda payment: payment.payment_method_id.type == "cash")
            .mapped("amount")
        )
        self.pos_session.update_closing_cash_details(total_cash_payment)
        self.pos_session.close_session_from_ui()

        self.assertEqual(self._synced_orders()[0].margin, 26)
        self.assertEqual(self._synced_orders()[1].margin, 12)

        self.assertEqual(self._synced_orders()[0].margin_percent, 0.4333)
        self.assertEqual(self._synced_orders()[1].margin_percent, 0.6)

        self.env.company.point_of_sale_config_id.point_of_sale_update_stock_quantities = "real"

    def _receive(self, product, qty, price_unit):
        move = (
            self.env["stock.move"]
            .create(
                {
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "product_id": product.id,
                    "product_uom_id": self.uom_unit.id,
                    "product_uom_qty": qty,
                    "value_manual": qty * price_unit,
                    "price_unit": price_unit,
                }
            )
            .sudo()
        )
        move._action_confirm()
        move._action_assign()
        move.move_line_ids.quantity = qty
        move.picked = True
        move._action_done()

    def test_closing_costs_each_product_once(self):
        self.categ_anglo.property_cost_method = "average"
        products = [
            self.create_product(f"Costed {index}", self.categ_anglo, 10, 4)
            for index in range(5)
        ]
        for index, product in enumerate(products):
            self._receive(product, 10, 2 + index)
        company_config = self.env.company.point_of_sale_config_id
        company_config.point_of_sale_update_stock_quantities = "closing"
        self.addCleanup(
            setattr, company_config, "point_of_sale_update_stock_quantities", "real"
        )
        self.open_new_session()
        self.env["pos.order"].sync_from_ui(
            [
                self.create_ui_order_data([(product, 1) for product in products])
                for _ in range(10)
            ]
        )
        lines = self.pos_session.order_ids.lines
        self.assertEqual(len(lines), 50)
        self.assertFalse(any(lines.mapped("is_total_cost_computed")))

        PosOrderLine = type(self.env["pos.order.line"])
        PosOrder = type(self.env["pos.order"])
        consider_moves = PosOrderLine._get_stock_moves_to_consider
        update_at_closing = PosOrder._update_total_cost_at_session_closing
        costed_products = []
        queries = []
        elapsed = []

        def spy_moves(line, stock_moves, product):
            costed_products.append(product.id)
            return consider_moves(line, stock_moves, product)

        def count_queries(orders, stock_moves):
            orders.env.flush_all()
            before = orders.env.cr.sql_statement_count
            started = time.perf_counter()
            update_at_closing(orders, stock_moves)
            orders.env.flush_all()
            queries.append(orders.env.cr.sql_statement_count - before)
            elapsed.append(time.perf_counter() - started)

        total_cash = sum(self.pos_session.order_ids.payment_ids.mapped("amount"))
        with (
            patch.object(PosOrderLine, "_get_stock_moves_to_consider", spy_moves),
            patch.object(
                PosOrder, "_update_total_cost_at_session_closing", count_queries
            ),
        ):
            self.pos_session.update_closing_cash_details(total_cash)
            self.pos_session.close_session_from_ui()
        _logger.debug(
            "closing cost update: %s queries in %s s for %s lines",
            queries,
            elapsed,
            len(lines),
        )

        self.assertEqual(
            sorted(costed_products),
            sorted(product.id for product in products),
            "the moves and their cost are computed once per product, not per line",
        )
        self.assertTrue(all(lines.mapped("is_total_cost_computed")))
        for index, product in enumerate(products):
            product_lines = lines.filtered(lambda l, p=product: l.product_id == p)
            self.assertEqual(product_lines.mapped("price_cost"), [2 + index] * 10)
            self.assertEqual(product_lines.mapped("total_cost"), [2 + index] * 10)
            self.assertEqual(product_lines.mapped("margin"), [8 - index] * 10)
