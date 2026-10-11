import logging

import odoo
from odoo.exceptions import ValidationError
from odoo.fields import Command

from odoo.addons.point_of_sale.tests.common import PosLazySessionCommon

_logger = logging.getLogger(__name__)

LOGGER = "odoo.addons.point_of_sale.models.stock_picking"


@odoo.tests.tagged("post_install", "-at_install")
class TestPosPicking(PosLazySessionCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.pos_picking_type = cls.warehouse.pos_type_id
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.pos_config_usd.picking_type_id = cls.pos_picking_type

    def _create_order(self, line_specs):
        if not self.pos_config_usd.current_session_id:
            self.pos_config_usd.open_ui()
        order = self.env["pos.order"].create(
            {
                "session_id": self.pos_config_usd.current_session_id.id,
                "company_id": self.env.company.id,
                "amount_tax": 0,
                "amount_total": 0,
                "amount_paid": 0,
                "amount_return": 0,
            }
        )
        order.name = "EBORD%s" % order.id
        self.env["pos.order.line"].create(
            [
                {
                    "order_id": order.id,
                    "name": "L",
                    "price_unit": 1,
                    "price_subtotal": abs(spec["qty"]),
                    "price_subtotal_incl": abs(spec["qty"]),
                    **spec,
                }
                for spec in line_specs
            ]
        )
        return order

    def _create_pos_picking(self, lines):
        return self.env["stock.picking"]._create_picking_from_pos_order_lines(
            self.stock_location.id, lines, self.pos_picking_type
        )

    def test_return_picking_owner_follows_each_refunded_order(self):
        product = self.env["product.product"].create(
            {"name": "Consigned", "is_storable": True, "available_in_pos": True}
        )
        owner_a, owner_b = self.env["res.partner"].create(
            [{"name": "Consignor A"}, {"name": "Consignor B"}]
        )
        for owner in (owner_a, owner_b):
            self.env["stock.quant"]._update_available_quantity(
                product, self.stock_location, 5, owner_id=owner
            )

        sold_orders = []
        for owner in (owner_a, owner_b):
            order = self._create_order([{"product_id": product.id, "qty": 1}])
            picking = self._create_pos_picking(order.lines)
            picking.pos_order_id = order
            picking.move_line_ids.owner_id = owner
            sold_orders.append(order)

        refund_lines = self.env["pos.order.line"]
        for order in sold_orders:
            refund_lines |= self._create_order(
                [
                    {
                        "product_id": product.id,
                        "qty": -1,
                        "refunded_orderline_id": order.lines.id,
                    }
                ]
            ).lines

        return_picking = self._create_pos_picking(refund_lines)

        self.assertEqual(
            return_picking.mapped("state"),
            ["done"],
            "_create_picking_from_pos_order_lines swallows UserError and "
            "ValidationError, so the owner assertion below would pass just as "
            "well on a picking that never validated",
        )
        self.assertEqual(
            sorted(
                (line.owner_id.name, line.quantity)
                for line in return_picking.move_line_ids
            ),
            [(owner_a.name, 1.0), (owner_b.name, 1.0)],
        )

    def test_owner_allocation_rounds_the_shortfall_to_the_product_uom(self):
        product = self.env["product.product"].create(
            {
                "name": "Consigned Fractional",
                "is_storable": True,
                "available_in_pos": True,
            }
        )
        owner = self.env["res.partner"].create({"name": "Consignor F"})
        self.env["stock.quant"]._update_available_quantity(
            product, self.stock_location, 5, owner_id=owner
        )
        order = self._create_order([{"product_id": product.id, "qty": 0.8}])
        picking = self._create_pos_picking(order.lines)
        self.assertEqual(picking.move_line_ids.mapped("quantity"), [0.8])

        owned = 0.0
        for delivered in (0.1, 0.7):
            owned += delivered
        self.assertLess(owned, 0.8, "0.1 + 0.7 accumulates to just under 0.8")

        picking._update_move_line_owners({(product.id, owner.id): owned})

        self.assertEqual(
            [(line.owner_id.name, line.quantity) for line in picking.move_line_ids],
            [(owner.name, 0.8)],
            "the 1.1e-16 shortfall must not become a second move line; unguarded "
            "this reads [('Consignor F', 0.8), (False, 0.0)], because quantity's "
            "own Product Unit rounding turns the sliver into a zero-quantity line "
            "rather than into misplaced stock",
        )

    def test_a_session_closing_picking_is_identified_before_it_validates(self):
        product = self.env["product.product"].create(
            {
                "name": "Closed At Session End",
                "is_storable": True,
                "available_in_pos": True,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            product, self.stock_location, 5
        )
        order = self._create_order([{"product_id": product.id, "qty": 1}])
        order.state = "paid"
        session = order.session_id
        session.update_stock_at_closing = True

        session._create_picking_at_end_of_session()

        picking = self.env["stock.picking"].search(
            [("pos_session_id", "=", session.id)]
        )
        self.assertEqual(len(picking), 1)
        self.assertEqual(picking.origin, session.name)
        self.assertFalse(
            picking.pos_order_id,
            "pos_session._accumulate_stock_amounts selects session pickings with "
            "filtered(lambda p: not p.pos_order_id), so a session-closing picking "
            "must not carry one even when its bucket holds a single order",
        )
        self.assertEqual(picking.state, "done")

    def _create_order_with_one_known_and_one_unknown_lot(self):
        self.pos_picking_type.write(
            {"use_existing_lots": True, "use_create_lots": False}
        )
        product = self.env["product.product"].create(
            {
                "name": "Tracked",
                "is_storable": True,
                "tracking": "lot",
                "available_in_pos": True,
            }
        )
        known_lot = self.env["product.trace"].create(
            {
                "name": "LOT-KNOWN",
                "product_id": product.id,
                "company_id": self.env.company.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            product, self.stock_location, 5, trace_id=known_lot
        )
        return self._create_order(
            [
                {
                    "product_id": product.id,
                    "qty": 1,
                    "pack_lot_ids": [Command.create({"lot_name": name})],
                }
                for name in ("LOT-KNOWN", "LOT-UNKNOWN")
            ]
        )

    def test_unresolvable_lot_name_survives_a_sibling_lot_that_resolves(self):
        order = self._create_order_with_one_known_and_one_unknown_lot()
        with self.assertLogs(LOGGER, "WARNING"):
            picking = self._create_pos_picking(order.lines)
        self.assertEqual(picking.mapped("state"), ["assigned"])
        self.assertEqual(
            sorted(
                line.trace_id.name or line.lot_name or ""
                for line in picking.move_line_ids
            ),
            ["LOT-KNOWN", "LOT-UNKNOWN"],
        )

    def test_failed_auto_validation_names_the_pos_order(self):
        order = self._create_order_with_one_known_and_one_unknown_lot()
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self._create_pos_picking(order.lines)
        self.assertIn(order.name, "\n".join(logs.output))

    def test_archiving_a_picking_type_names_the_pos_config_that_uses_it(self):
        unused_type = self.pos_picking_type.copy(
            {"name": "EB Unused", "sequence_code": "EBX"}
        )
        used_type = self.pos_picking_type.copy(
            {"name": "EB Used", "sequence_code": "EBU"}
        )
        config = self.env["pos.config"].create(
            {"name": "EB Archive Probe", "picking_type_id": used_type.id}
        )
        with self.assertRaisesRegex(ValidationError, config.name):
            (unused_type | used_type).write({"active": False})

    def test_a_lot_spread_over_two_bins_is_consumed_whether_split_or_single_line(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self.pos_config_usd.picking_type_id = warehouse.pos_type_id
        warehouse.pos_type_id.use_existing_lots = True
        root = warehouse.lot_stock_id
        bins = self.env["stock.location"].create(
            [
                {
                    "name": name,
                    "location_id": root.id,
                    "company_id": self.env.company.id,
                }
                for name in ["Challenge A", "Challenge B"]
            ]
        )
        for split in [False, True]:
            product = self.env["product.product"].create(
                {
                    "name": f"Challenge lot {split}",
                    "is_storable": True,
                    "tracking": "lot",
                    "available_in_pos": True,
                }
            )
            lot = self.env["product.trace"].create(
                {
                    "name": f"LOT-{split}",
                    "product_id": product.id,
                    "company_id": self.env.company.id,
                }
            )
            for location in bins:
                self.env["stock.quant"]._update_available_quantity(
                    product, location, 1, trace_id=lot
                )
            quantities = [1, 1] if split else [2]
            order = self._create_order_from_specs(
                [
                    {
                        "product_id": product.id,
                        "qty": qty,
                        "price_unit": index + 1,
                        "pack_lot_ids": [Command.create({"lot_name": lot.name})],
                    }
                    for index, qty in enumerate(quantities)
                ]
            )
            order._create_order_picking()
            quants = self.env["stock.quant"].search(
                [("product_id", "=", product.id), ("location_id", "in", bins.ids)]
            )
            balances = sorted(quants.mapped("quantity"))
            _logger.debug(
                "stock persisted=%s split=%s states=%s balances=%s",
                order.lines.ids,
                split,
                order.picking_ids.mapped("state"),
                balances,
            )
            self.assertEqual(order.picking_ids.mapped("state"), ["done"])
            self.assertEqual(balances, [0.0, 0.0])

    def test_no_variant_lines_of_one_lot_are_moved_and_reserved_in_full(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self.pos_config_usd.picking_type_id = warehouse.pos_type_id
        warehouse.pos_type_id.use_existing_lots = True
        attribute = self.env["product.attribute"].create(
            {"name": "Challenge inscription", "create_variant": "no_variant"}
        )
        values = self.env["product.attribute.value"].create(
            [{"name": label, "attribute_id": attribute.id} for label in ["A", "B"]]
        )
        product = self.env["product.product"].create(
            {
                "name": "Challenge group",
                "is_storable": True,
                "tracking": "lot",
                "available_in_pos": True,
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": attribute.id,
                            "value_ids": [Command.set(values.ids)],
                        }
                    )
                ],
            }
        )
        ptavs = product.attribute_line_ids.product_template_value_ids
        lot = self.env["product.trace"].create(
            {
                "name": "GROUP-LOT",
                "product_id": product.id,
                "company_id": self.env.company.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            product, warehouse.lot_stock_id, 10, trace_id=lot
        )
        order = self._create_order_from_specs(
            [
                {
                    "product_id": product.id,
                    "qty": 1,
                    "attribute_value_ids": [Command.set(ptav.ids)],
                    "pack_lot_ids": [Command.create({"lot_name": lot.name})],
                }
                for ptav in ptavs
            ]
        )
        order._create_order_picking()
        moves = order.picking_ids.move_ids
        _logger.debug(
            "grouping ordered=%s demands=%s done_quantities=%s attrs=%s",
            sum(order.lines.mapped("qty")),
            moves.mapped("product_uom_qty"),
            moves.mapped("quantity"),
            [m.never_product_template_attribute_value_ids.ids for m in moves],
        )
        self.assertEqual(sum(order.lines.mapped("qty")), 2)
        self.assertEqual(sum(moves.mapped("quantity")), 2)

        reservation = order.picking_ids.copy({"move_ids": [Command.clear()]})
        groups = order.lines.grouped(lambda line: tuple(line.attribute_value_ids.ids))
        reserved_moves = (
            self.env["stock.move"]
            .create(
                [
                    reservation._prepare_stock_move_vals(lines)
                    for lines in groups.values()
                ]
            )
            ._action_confirm()
        )
        reserved_moves.move_line_ids.unlink()
        reserved_moves._add_move_lines_from_pos_order_lines(
            order.lines, are_quantities_done=False
        )
        self.assertEqual(reserved_moves.mapped("quantity"), [1, 1])
        _logger.debug(
            "STOCK attribute reservation quantities=%s",
            reserved_moves.mapped("quantity"),
        )
