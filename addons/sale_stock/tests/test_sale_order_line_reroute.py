from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.sale_stock.tests.common import TestSaleStockCommon


@tagged("post_install", "-at_install")
class TestSaleOrderLineReroute(TestSaleStockCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        stock = cls.warehouse.lot_stock_id
        customers = cls.env.ref("stock.stock_location_customers")
        cls.ship_type = cls.warehouse.out_type_id
        cls.ship_3p_type = cls.ship_type.copy(
            {"name": "Ship 3P", "sequence_code": "SHIP3P"},
        )
        cls.route_ship, cls.route_3p = cls.env["stock.route"].create(
            [
                {
                    "name": name,
                    "sale_selectable": True,
                    "rule_ids": [
                        Command.create(
                            {
                                "name": name,
                                "action": "pull",
                                "picking_type_id": picking_type.id,
                                "location_src_id": stock.id,
                                "location_dest_id": customers.id,
                                "procure_method": "make_to_stock",
                            },
                        ),
                    ],
                }
                for name, picking_type in (
                    ("Ship", cls.ship_type),
                    ("Ship 3P", cls.ship_3p_type),
                )
            ],
        )
        cls.product_1, cls.product_2 = cls.env["product.product"].create(
            [
                {"name": "Rerouted product 1", "is_storable": True},
                {"name": "Rerouted product 2", "is_storable": True},
            ],
        )
        for product in cls.product_1 | cls.product_2:
            cls.env["stock.quant"]._update_available_quantity(product, stock, 10)

    def _confirm_3p_order(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_qty": 3,
                            "route_ids": [Command.set(self.route_3p.ids)],
                        },
                    )
                    for product in self.product_1 | self.product_2
                ],
            },
        )
        order.action_confirm()
        self.assertEqual(order.picking_ids.picking_type_id, self.ship_3p_type)
        return order

    def test_new_route_replaces_the_pending_transfer(self):
        order = self._confirm_3p_order()
        ship_3p = order.picking_ids

        order.line_ids.route_ids = self.route_ship

        self.assertEqual(ship_3p.state, "cancel")
        ship = order.picking_ids - ship_3p
        self.assertEqual(ship.picking_type_id, self.ship_type)
        self.assertRecordValues(
            ship.move_ids.sorted("product_id"),
            [
                {"product_id": self.product_1.id, "product_uom_qty": 3},
                {"product_id": self.product_2.id, "product_uom_qty": 3},
            ],
        )
        self.assertEqual(ship.move_ids.sale_line_id, order.line_ids)

    def test_new_route_moves_only_the_changed_line(self):
        order = self._confirm_3p_order()
        ship_3p = order.picking_ids
        rerouted, kept = order.line_ids

        rerouted.route_ids = self.route_ship

        self.assertNotEqual(ship_3p.state, "cancel")
        self.assertEqual(
            ship_3p.move_ids.filtered(lambda m: m.state != "cancel").sale_line_id, kept
        )
        self.assertEqual(
            rerouted.move_ids.filtered(lambda m: m.state != "cancel").picking_type_id,
            self.ship_type,
        )

    def test_same_route_keeps_the_transfer(self):
        order = self._confirm_3p_order()
        ship_3p = order.picking_ids

        order.line_ids.route_ids = self.route_3p

        self.assertEqual(order.picking_ids, ship_3p)
        self.assertNotIn("cancel", ship_3p.move_ids.mapped("state"))

    def test_route_is_kept_once_goods_moved(self):
        order = self._confirm_3p_order()
        ship_3p = order.picking_ids
        for move in ship_3p.move_ids:
            move.write({"quantity": move.product_uom_qty, "picked": True})
        ship_3p.button_validate()

        with self.assertRaisesRegex(UserError, "goods already moved"):
            order.line_ids.route_ids = self.route_ship

    def test_route_is_kept_on_a_locked_order(self):
        order = self._confirm_3p_order()
        order.locked = True

        with self.assertRaisesRegex(UserError, "locked order"):
            order.line_ids.route_ids = self.route_ship
