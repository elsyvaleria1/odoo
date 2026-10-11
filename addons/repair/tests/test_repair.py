from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, HttpCase, common, tagged
from odoo.tools import float_compare, float_is_zero


class TestRepairCommon(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.res_partner_1 = cls.env["res.partner"].create({"name": "Wood Corner"})
        cls.res_partner_address_1 = cls.env["res.partner"].create(
            {"name": "Willie Burke", "parent_id": cls.res_partner_1.id}
        )
        cls.res_partner_12 = cls.env["res.partner"].create({"name": "Partner 12"})

        cls.product_product_3 = cls.env["product.product"].create(
            {"name": "Desk Combination"}
        )
        cls.product_product_11 = cls.env["product.product"].create(
            {
                "name": "Conference Chair",
                "lst_price": 30.0,
            }
        )
        cls.product_product_5 = cls.env["product.product"].create({"name": "Product 5"})
        cls.product_product_6 = cls.env["product.product"].create(
            {"name": "Large Cabinet"}
        )
        cls.product_product_12 = cls.env["product.product"].create(
            {"name": "Office Chair Black"}
        )
        cls.product_product_13 = cls.env["product.product"].create(
            {"name": "Corner Desk Left Sit"}
        )

        cls.product_storable_no = cls.env["product.product"].create(
            {
                "name": "Product Storable No Tracking #1",
                "is_storable": True,
                "tracking": "none",
            }
        )
        cls.product_storable_no2 = cls.env["product.product"].create(
            {
                "name": "Product Storable No Tracking #2",
                "is_storable": True,
                "tracking": "none",
            }
        )
        cls.product_storable_serial = cls.env["product.product"].create(
            {
                "name": "Product Storable Serial",
                "is_storable": True,
                "tracking": "serial",
            }
        )
        cls.product_storable_lot = cls.env["product.product"].create(
            {
                "name": "Product Storable Lot",
                "is_storable": True,
                "tracking": "lot",
            }
        )

        cls.product_order_repair = cls.env["product.product"].create(
            {
                "name": "Repair Service",
                "type": "service",
                "service_tracking": "repair",
            }
        )

        cls.stock_warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.stock_location_14 = cls.env["stock.location"].create(
            {
                "name": "Shelf 2",
                "location_id": cls.stock_warehouse.lot_stock_id.id,
            }
        )

        cls.repair1 = cls.env["repair.order"].create(
            {
                "product_id": cls.product_product_3.id,
                "product_uom_id": cls.env.ref("base.product_uom_unit").id,
                "picking_type_id": cls.stock_warehouse.repair_type_id.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product_product_11.id,
                            "product_uom_qty": 1.0,
                            "state": "draft",
                            "repair_line_type": "add",
                            "company_id": cls.env.company.id,
                        },
                    )
                ],
                "partner_id": cls.res_partner_12.id,
            }
        )

        cls.repair0 = cls.env["repair.order"].create(
            {
                "product_id": cls.product_product_5.id,
                "product_uom_id": cls.env.ref("base.product_uom_unit").id,
                "user_id": False,
                "picking_type_id": cls.stock_warehouse.repair_type_id.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product_product_12.id,
                            "product_uom_qty": 1.0,
                            "state": "draft",
                            "repair_line_type": "add",
                            "company_id": cls.env.company.id,
                        },
                    )
                ],
                "partner_id": cls.res_partner_12.id,
            }
        )

        cls.repair2 = cls.env["repair.order"].create(
            {
                "product_id": cls.product_product_6.id,
                "product_uom_id": cls.env.ref("base.product_uom_unit").id,
                "user_id": False,
                "picking_type_id": cls.stock_warehouse.repair_type_id.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product_product_13.id,
                            "product_uom_qty": 1.0,
                            "state": "draft",
                            "repair_line_type": "add",
                            "company_id": cls.env.company.id,
                        },
                    )
                ],
                "partner_id": cls.res_partner_12.id,
            }
        )

        cls.env.user.group_ids |= cls.env.ref("stock.group_stock_user")

    def _create_simple_repair_order(self):
        product_to_repair = self.product_product_5
        return self.env["repair.order"].create(
            {
                "product_id": product_to_repair.id,
                "product_uom_id": product_to_repair.uom_id.id,
                "picking_type_id": self.stock_warehouse.repair_type_id.id,
                "partner_id": self.res_partner_12.id,
            }
        )

    def _create_simple_part_move(self, repair_id=False, qty=0.0, product=False):
        if not product:
            product = self.product_product_5
        return self.env["stock.move"].create(
            {
                "repair_line_type": "add",
                "product_id": product.id,
                "product_uom_qty": qty,
                "repair_id": repair_id,
                "company_id": self.env.company.id,
            }
        )

    @classmethod
    def create_quant(cls, product, qty, offset=0, name="L"):
        i = 1
        if product.tracking == "serial":
            i, qty = qty, 1
            if name == "L":
                name = "S"

        vals = []
        for x in range(1, i + 1):
            qDict = {
                "location_id": cls.stock_warehouse.lot_stock_id.id,
                "product_id": product.id,
                "inventory_quantity": qty,
            }

            if product.tracking != "none":
                qDict["trace_id"] = (
                    cls.env["product.trace"]
                    .create(
                        {
                            "name": name + str(offset + x),
                            "product_id": product.id,
                        }
                    )
                    .id
                )
            vals.append(qDict)

        return cls.env["stock.quant"].create(vals)


@tagged("post_install", "-at_install")
class TestRepair(TestRepairCommon):
    def test_01_repair_states_transition(self):
        repair = self._create_simple_repair_order()

        lineA = self._create_simple_part_move(repair.id, -1.0, self.product_storable_no)
        repair.move_ids |= lineA
        with self.assertRaises(UserError):
            repair.action_validate()

        lineA.product_uom_qty = 2.0
        lineB = self._create_simple_part_move(repair.id, 2.0, self.product_storable_lot)
        repair.move_ids |= lineB
        quant = self.create_quant(self.product_storable_no, 1)
        quant |= self.create_quant(self.product_storable_lot, 3)
        quant.action_apply_inventory()

        lineC = self._create_simple_part_move(repair.id, 1.0, self.product_storable_no2)
        repair.move_ids |= lineC

        repair.product_id = self.product_storable_serial
        validate_action = repair.action_validate()
        self.assertEqual(
            validate_action.get("res_model"),
            "wizard.repair.order.confirm.insufficient.stock",
        )
        warn_qty_wizard = Form(
            self.env["wizard.repair.order.confirm.insufficient.stock"].with_context(
                **validate_action["context"]
            )
        ).save()
        warn_qty_wizard.action_proceed()

        self.assertEqual(
            repair.state, "confirmed", 'Repair order should be in "Confirmed" state.'
        )
        self.assertEqual(
            lineA.state,
            "partially_available",
            'Repair line #1 should be in "Partial Availability" state.',
        )
        self.assertEqual(
            lineB.state, "assigned", 'Repair line #2 should be in "Available" state.'
        )
        self.assertEqual(
            lineC.state,
            "confirmed",
            'Repair line #3 should be in "Waiting Availability" state.',
        )


        self.assertEqual(len(repair.sale_order_id), 0)
        repair.partner_id = None
        with self.assertRaises(UserError) as err:
            repair.action_create_sale_order()
        self.assertIn("You need to define a customer", err.exception.args[0])
        repair.partner_id = self.res_partner_12.id
        repair.action_create_sale_order()
        self.assertNotEqual(len(repair.sale_order_id), 0)
        self.assertEqual(len(repair.sale_order_id.line_ids), 3)
        with self.assertRaises(UserError) as err:
            repair.action_create_sale_order()


        self.assertNotEqual(repair.state, "done")
        repair.action_repair_cancel()
        self.assertEqual(repair.state, "cancel")
        self.assertTrue(all(m.state == "cancel" for m in repair.move_ids))
        self.assertTrue(
            all(
                float_is_zero(sol.product_qty, 2)
                for sol in repair.sale_order_id.line_ids
            )
        )


        repair.action_repair_cancel_draft()
        self.assertEqual(repair.state, "draft")
        self.assertTrue(all(m.state == "draft" for m in repair.move_ids))

        quant = self.create_quant(self.product_storable_serial, 1)
        quant.action_apply_inventory()
        repair.trace_id = quant.trace_id
        repair.action_validate()
        self.assertEqual(repair.state, "confirmed")

        repair.action_repair_start()
        self.assertEqual(repair.state, "under_repair")

        repair.move_ids.picked = True
        self.assertTrue(repair.has_uncomplete_moves)
        lot = lineB.move_line_ids.trace_id
        with self.assertRaises(UserError) as err:
            lineB.move_line_ids.trace_id = False
            repair.action_repair_done()

        lineB.move_line_ids.trace_id = lot

        lineA.quantity = 2
        lineC.quantity = 2
        lineD = self._create_simple_part_move(repair.id, 0.0)
        repair.move_ids |= lineD

        self.assertEqual(lineD.state, "assigned")
        num_of_lines = len(repair.move_ids)
        self.assertFalse(repair.move_id)
        self.assertFalse(repair.has_uncomplete_moves)
        repair.action_repair_end()
        self.assertFalse(
            (repair.move_id | repair.move_ids).picking_id, "No picking for repair moves"
        )
        self.assertEqual(repair.state, "done")
        done_moves = repair.move_ids - lineD
        self.assertTrue(all(m.state == "done" for m in done_moves))
        self.assertEqual(lineD.state, "cancel")
        self.assertEqual(len(repair.move_id), 1)
        self.assertEqual(len(repair.move_ids), num_of_lines)

        with self.assertRaises(UserError) as err:
            repair.action_repair_cancel()

    def test_02_repair_sale_order_binding(self):
        so_form = Form(self.env["sale.order"])
        so_form.partner_id = self.res_partner_1
        with so_form.line_ids.new() as line:
            line.product_id = self.product_order_repair
            line.product_qty = 2.0
        with so_form.line_ids.new() as line:
            line.display_type = "line_section"
            line.name = "Dummy Section"
        sale_order = so_form.save()
        order_line = sale_order.line_ids[0]
        line_section = sale_order.line_ids[1]
        self.assertEqual(len(sale_order.repair_order_ids), 0)
        sale_order.action_confirm()
        self.assertEqual(len(sale_order.repair_order_ids), 1)
        repair_order = sale_order.repair_order_ids[0]
        self.assertEqual(sale_order, repair_order.sale_order_id)
        self.assertEqual(repair_order.state, "confirmed")
        order_line.product_qty = 0
        self.assertEqual(repair_order.state, "cancel")
        order_line.product_qty = 1
        line_section.name = "updated section"
        self.assertEqual(repair_order.state, "confirmed")
        repair_order.action_repair_cancel()
        self.assertTrue(float_is_zero(order_line.product_qty, 2))
        order_line.product_qty = 3
        self.assertEqual(repair_order.state, "confirmed")
        ro_form = Form(repair_order)
        with ro_form.move_ids.new() as ro_line_form:
            ro_line_form.repair_line_type = "add"
            ro_line_form.product_id = self.product_product_11
            ro_line_form.product_uom_qty = 1
        ro_form.save()
        ro_line_0 = repair_order.move_ids[0]
        sol_part_0 = ro_line_0.sale_line_id
        self.assertEqual(
            float_compare(sol_part_0.product_qty, ro_line_0.product_uom_qty, 2), 0
        )
        sol_part_0.product_qty = 5
        self.assertNotEqual(
            float_compare(sol_part_0.product_qty, ro_line_0.product_uom_qty, 2), 0
        )
        ro_line_0.product_uom_qty = 3
        self.assertEqual(
            float_compare(sol_part_0.product_qty, ro_line_0.product_uom_qty, 2), 0
        )
        self.assertFalse(float_is_zero(sol_part_0.price_unit, 2))
        repair_order.under_warranty = True
        self.assertTrue(float_is_zero(sol_part_0.price_unit, 2))
        repair_order.under_warranty = False
        self.assertFalse(float_is_zero(sol_part_0.price_unit, 2))

        ro_line_0.repair_line_type = "remove"
        self.assertTrue(float_is_zero(sol_part_0.product_qty, 2))
        ro_line_0.repair_line_type = "add"
        self.assertEqual(
            float_compare(sol_part_0.product_qty, ro_line_0.product_uom_qty, 2), 0
        )
        ro_line_0.repair_line_type = "recycle"
        self.assertTrue(float_is_zero(sol_part_0.product_qty, 2))
        ro_line_0.repair_line_type = "add"
        self.assertEqual(
            float_compare(sol_part_0.product_qty, ro_line_0.product_uom_qty, 2), 0
        )
        sol_count = len(sale_order.line_ids)
        with ro_form.move_ids.new() as ro_line_form:
            ro_line_form.repair_line_type = "remove"
            ro_line_form.product_id = self.product_product_12
            ro_line_form.product_uom_qty = 1
        with ro_form.move_ids.new() as ro_line_form:
            ro_line_form.repair_line_type = "recycle"
            ro_line_form.product_id = self.product_product_13
            ro_line_form.product_uom_qty = 1
        ro_form.save()
        ro_line_1 = repair_order.move_ids[1]
        self.assertEqual(len(sale_order.line_ids), sol_count)
        ro_line_1.repair_line_type = "add"
        sol_part_1 = ro_line_1.sale_line_id
        self.assertNotEqual(len(sale_order.line_ids), sol_count)
        self.assertEqual(
            float_compare(sol_part_1.product_qty, ro_line_1.product_uom_qty, 2), 0
        )
        repair_order.move_ids = [(2, ro_line_1.id, 0)]
        self.assertTrue(float_is_zero(sol_part_1.product_qty, 2))

        repair_order.action_repair_start()
        for line in repair_order.move_ids:
            line.quantity = line.product_uom_qty
        repair_order.action_repair_end()
        self.assertEqual(order_line.product_qty, order_line.qty_transferred)
        self.assertEqual(
            float_compare(sol_part_0.product_qty, ro_line_0.quantity, 2), 0
        )
        self.assertTrue(float_is_zero(sol_part_1.qty_transferred, 2))

    def test_repair_compute_product_uom(self):
        repair = self.env["repair.order"].create(
            {
                "product_id": self.product_product_3.id,
                "picking_type_id": self.stock_warehouse.repair_type_id.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "repair_line_type": "add",
                            "product_id": self.product_product_11.id,
                        },
                    )
                ],
            }
        )
        self.assertEqual(repair.product_uom_id, self.product_product_3.uom_id)
        self.assertEqual(
            repair.move_ids[0].product_uom_id, self.product_product_11.uom_id
        )

    def test_repair_compute_location(self):
        repair = self.env["repair.order"].create(
            {
                "product_id": self.product_product_3.id,
                "picking_type_id": self.stock_warehouse.repair_type_id.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "repair_line_type": "add",
                            "product_id": self.product_product_11.id,
                        },
                    )
                ],
            }
        )
        self.assertEqual(repair.location_id, self.stock_warehouse.lot_stock_id)
        self.assertEqual(
            repair.move_ids[0].location_id, self.stock_warehouse.lot_stock_id
        )
        location_dest_id = self.env["stock.location"].search(
            [
                ("usage", "=", "production"),
                ("company_id", "=", repair.company_id.id),
            ],
            limit=1,
        )
        self.assertEqual(repair.move_ids[0].location_dest_id, location_dest_id)

    def test_no_recompute_location_when_change_user_after_confirm(self):
        user1 = self.env["res.users"].create(
            {
                "name": "A User",
                "login": "a_user",
                "email": "a@user.com",
            }
        )
        repair_order = self._create_simple_repair_order()
        repair_order.location_id = self.stock_location_14
        repair_order.recycle_location_id = self.stock_location_14
        repair_order.action_validate()
        repair_order.user_id = user1
        self.assertEqual(repair_order.location_id, self.stock_location_14)
        self.assertEqual(repair_order.recycle_location_id, self.stock_location_14)
        repair_order.action_repair_start()
        repair_order.action_repair_end()
        with Form(repair_order) as ro_form:
            ro_form.user_id = user1
        self.assertEqual(repair_order.location_id, self.stock_location_14)
        self.assertEqual(repair_order.recycle_location_id, self.stock_location_14)

    def test_purchase_price_so_create_from_repair(self):
        if not self.env["ir.module.module"].search(
            [("name", "=", "sale_margin"), ("state", "=", "installed")]
        ):
            self.skipTest(
                "sale_margin is not installed, so there is no purchase price to test"
            )
        self.product_product_11.standard_price = 10
        repair = self.env["repair.order"].create(
            {
                "partner_id": self.res_partner_1.id,
                "product_id": self.product_product_3.id,
                "picking_type_id": self.stock_warehouse.repair_type_id.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "repair_line_type": "add",
                            "product_id": self.product_product_11.id,
                        },
                    )
                ],
            }
        )
        repair.action_create_sale_order()
        self.assertEqual(
            repair.sale_order_id.line_ids.product_id, self.product_product_11
        )
        self.assertEqual(repair.sale_order_id.line_ids.purchase_price, 10)

    def test_repair_from_return(self):

        product = self.env["product.product"].create(
            {
                "name": "Test Product",
                "is_storable": True,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            product, self.stock_location_14, 1
        )
        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.stock_warehouse.out_type_id
        picking_form.partner_id = self.res_partner_1
        with picking_form.move_ids.new() as move:
            move.product_id = product
            move.product_uom_qty = 1.0
        picking = picking_form.save()
        picking.action_confirm()
        picking.action_assign()
        picking.button_validate()

        self.assertEqual(picking.state, "done")
        stock_return_picking_form = Form(
            self.env["wizard.stock.picking.return"].with_context(
                active_ids=picking.ids,
                active_id=picking.ids[0],
                active_model="stock.picking",
            )
        )
        stock_return_picking = stock_return_picking_form.save()
        stock_return_picking.product_return_moves.quantity = 1.0
        stock_return_picking_action = stock_return_picking.action_create_returns()
        return_picking = self.env["stock.picking"].browse(
            stock_return_picking_action["res_id"]
        )
        return_picking.move_ids.picked = True
        return_picking.button_validate()
        self.assertEqual(return_picking.state, "done")

        res_dict = return_picking.action_repair_return()
        repair_form = Form.from_action(self.env, res_dict)
        repair_form.product_id = product
        repair = repair_form.save()
        repair_form = Form(repair)
        with repair_form.move_ids.new() as move:
            move.product_id = self.product_product_5
            move.product_uom_qty = 1.0
            move.quantity = 1.0
            move.repair_line_type = "add"
        repair = repair_form.save()
        repair.action_repair_start()
        repair.action_repair_end()
        self.assertEqual(repair.state, "done")
        self.assertEqual(
            len(return_picking.move_ids),
            1,
            "Parts added to the repair order shoudln't be added to the return picking",
        )
        self.assertEqual(
            repair.location_id,
            return_picking.location_dest_id,
            "Repair location should have defaulted to return destination location",
        )
        self.assertEqual(
            repair.partner_id,
            return_picking.partner_id,
            "Repair customer should have defaulted to return customer",
        )
        self.assertEqual(
            repair.picking_type_id,
            return_picking.picking_type_id.warehouse_id.repair_type_id,
        )

    def test_repair_with_product_in_package(self):
        self.product_product_3.is_storable = True
        self.product_product_3.tracking = "serial"
        sn_1 = self.env["product.trace"].create(
            {"name": "sn_1", "product_id": self.product_product_3.id}
        )
        sn_2 = self.env["product.trace"].create(
            {"name": "sn_2", "product_id": self.product_product_3.id}
        )

        package_1 = self.env["stock.package"].create({"name": "Package-test-1"})
        package_2 = self.env["stock.package"].create({"name": "Package-test-2"})

        self.env["stock.quant"]._update_available_quantity(
            self.product_product_3,
            self.stock_warehouse.lot_stock_id,
            1,
            trace_id=sn_1,
            package_id=package_1,
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product_product_3,
            self.stock_warehouse.lot_stock_id,
            1,
            trace_id=sn_2,
            package_id=package_2,
        )
        self.assertEqual(self.product_product_3.qty_available, 2)
        repair_order = self.env["repair.order"].create(
            {
                "product_id": self.product_product_3.id,
                "product_uom_id": self.product_product_3.uom_id.id,
                "location_id": self.stock_warehouse.lot_stock_id.id,
                "trace_id": sn_1.id,
                "picking_type_id": self.stock_warehouse.repair_type_id.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_product_5.id,
                            "product_uom_qty": 1.0,
                            "state": "draft",
                            "repair_line_type": "add",
                        },
                    )
                ],
            }
        )
        repair_order.action_validate()
        self.assertEqual(repair_order.state, "confirmed")
        repair_order.action_repair_start()
        self.assertEqual(repair_order.state, "under_repair")
        repair_order.move_ids.quantity = 1
        repair_order.action_repair_end()
        self.assertEqual(repair_order.state, "done")

    def test_sn_with_no_tracked_product(self):
        self.env.ref("base.group_user").implied_ids += self.env.ref(
            "stock.group_production_lot"
        )
        sn_1 = self.env["product.trace"].create(
            {"name": "sn_1", "product_id": self.product_storable_serial.id}
        )
        ro_form = Form(self.env["repair.order"])
        ro_form.product_id = self.product_storable_serial
        ro_form.trace_id = sn_1
        repair_order = ro_form.save()
        ro_form = Form(repair_order)
        ro_form.product_id = self.product_storable_no
        repair_order = ro_form.save()
        self.assertFalse(repair_order.trace_id)

    def test_onchange_picking_type_id_and_name(self):
        stock_location_1 = self.env.ref("stock.stock_location_stock")
        stock_location_2 = stock_location_1.copy()
        picking_type_1 = self.env["stock.picking.type"].create(
            {
                "name": "new_picking_type_1",
                "code": "repair_operation",
                "sequence_code": "PT1",
                "default_location_src_id": stock_location_1.id,
            }
        )
        picking_type_2 = self.env["stock.picking.type"].create(
            {
                "name": "new_picking_type_2",
                "code": "repair_operation",
                "sequence_code": "PT2",
                "default_location_src_id": stock_location_2.id,
            }
        )
        repair_order = self.env["repair.order"].create(
            {
                "product_id": self.product_product_3.id,
                "picking_type_id": picking_type_1.id,
            }
        )
        part = self.env["product.product"].create(
            {
                "name": "Part",
                "is_storable": True,
            }
        )
        self.env["stock.move"].create(
            {
                "repair_line_type": "add",
                "product_id": part.id,
                "product_uom_qty": 1,
                "repair_id": repair_order.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(part, stock_location_2, 1)
        repair_order._action_repair_confirm()
        move = repair_order.move_ids[0]
        self.assertEqual(repair_order.name, "WH/PT1/00001")
        self.assertEqual(move.reference, "WH/PT1/00001")
        self.assertEqual(move.location_id, stock_location_1)
        self.assertEqual(move.quantity, 0.0)
        repair_order.picking_type_id = picking_type_2
        self.assertEqual(repair_order.name, "WH/PT2/00001")
        self.assertEqual(move.reference, "WH/PT2/00001")
        self.assertEqual(move.location_id, stock_location_2)
        self.assertEqual(move.quantity, 1.0)
        repair_order.picking_type_id = picking_type_1
        self.assertEqual(repair_order.name, "WH/PT1/00002")
        self.assertEqual(move.reference, "WH/PT1/00002")
        repair_order.picking_type_id = picking_type_1
        self.assertEqual(repair_order.name, "WH/PT1/00002")
        self.assertEqual(move.reference, "WH/PT1/00002")

    def test_repair_components_lots_show_in_invoice(self):
        quant = self.create_quant(self.product_storable_serial, 1)
        quant.action_apply_inventory()
        repair_order = self.env["repair.order"].create(
            {
                "product_id": self.product_product_3.id,
                "product_uom_id": self.product_product_3.uom_id.id,
                "partner_id": self.res_partner_12.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product_storable_serial.id,
                            "product_uom_qty": 1.0,
                            "state": "draft",
                            "repair_line_type": "add",
                        }
                    )
                ],
            }
        )
        repair_order.action_validate()
        repair_order.action_repair_start()
        repair_order.action_repair_end()
        repair_order.action_create_sale_order()
        sale_order = repair_order.sale_order_id
        sale_order.action_confirm()
        invoice = sale_order._create_invoices()
        invoice.action_post()
        res = invoice._prepare_invoice_lot_rows()
        self.assertEqual(len(res), 1, "The invoice should have one line")
        self.assertEqual(
            res[0]["product_name"],
            self.product_storable_serial.display_name,
            "The product name should be the same",
        )
        self.assertEqual(
            res[0]["lot_name"], quant.trace_id.name, "The lot name should be the same"
        )

    def test_create_repair_order_from_cross_company_sn(self):
        sn_01 = self.env["product.trace"].create(
            {"name": "sn_1", "product_id": self.product_product_3.id}
        )
        action = sn_01.action_lot_open_repairs()
        repair_order = (
            self.env["repair.order"]
            .with_context(action.get("context"))
            .create(
                {
                    "product_id": self.product_product_3.id,
                    "product_uom_id": self.product_product_3.uom_id.id,
                    "partner_id": self.res_partner_12.id,
                }
            )
        )
        self.assertEqual(repair_order.company_id, self.env.company)

    def test_delivered_qty_of_generated_so(self):
        repair_order = self.env["repair.order"].create(
            {
                "product_id": self.product_order_repair.id,
                "product_uom_id": self.product_order_repair.uom_id.id,
                "partner_id": self.res_partner_1.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product_order_repair.id,
                            "product_uom_qty": 1.0,
                            "state": "draft",
                            "repair_line_type": "add",
                        }
                    )
                ],
            }
        )
        repair_order.action_validate()
        repair_order.action_repair_start()
        repair_order.action_repair_end()
        self.assertEqual(repair_order.state, "done")
        self.assertEqual(repair_order.move_ids.quantity, 1.0)
        repair_order.action_create_sale_order()
        sale_order = repair_order.sale_order_id
        sale_order.action_confirm()
        self.assertEqual(sale_order.line_ids.qty_transferred, 1.0)

    def test_repair_order_uncomplete_moves(self):
        repair_order = self.env["repair.order"].create(
            {
                "product_id": self.product_order_repair.id,
                "product_uom_id": self.product_order_repair.uom_id.id,
                "partner_id": self.res_partner_1.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product_product_5.id,
                            "product_uom_qty": 3.0,
                            "state": "draft",
                            "repair_line_type": "add",
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_product_6.id,
                            "product_uom_qty": 4.0,
                            "state": "draft",
                            "repair_line_type": "add",
                        }
                    ),
                ],
            }
        )
        repair_order.action_validate()
        repair_order.action_repair_start()
        self.assertFalse(repair_order.has_uncomplete_moves)
        repair_order.move_ids[0].quantity = 1.0
        self.assertTrue(repair_order.has_uncomplete_moves)
        repair_order.move_ids[1].quantity = 2
        self.assertTrue(repair_order.has_uncomplete_moves)
        repair_order.move_ids[0].quantity = 3.0
        repair_order.move_ids[1].quantity = 4.0
        self.assertFalse(repair_order.has_uncomplete_moves)
        repair_order.action_repair_end()

    def test_repair_final_product_generate_lot_and_serial(self):
        self.stock_warehouse.repair_type_id.use_create_lots = True
        repair_order = self.env["repair.order"].create(
            {
                "product_id": self.product_storable_lot.id,
                "product_uom_id": self.product_storable_lot.uom_id.id,
                "partner_id": self.res_partner_1.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product_product_5.id,
                            "product_uom_qty": 3.0,
                            "state": "draft",
                            "repair_line_type": "add",
                        }
                    ),
                ],
            }
        )
        repair_order.action_validate()
        repair_order.action_repair_start()
        self.assertFalse(repair_order.trace_id.name)
        repair_order.action_generate_serial()
        self.assertTrue(repair_order.trace_id.name)

    def test_trigger_orderpoint_from_repair(self):
        self.assertFalse(
            self.env["stock.move"].search(
                [("product_id", "=", self.product_storable_no.id)]
            )
        )
        route = self.env["stock.route"].create(
            {
                "name": "new route",
                "rule_ids": [
                    (
                        0,
                        False,
                        {
                            "name": "rule_test",
                            "location_src_id": self.stock_warehouse.lot_stock_id.id,
                            "location_dest_id": self.stock_location_14.id,
                            "company_id": self.env.company.id,
                            "action": "pull",
                            "picking_type_id": self.env.ref("stock.picking_type_in").id,
                            "procure_method": "make_to_stock",
                        },
                    )
                ],
            }
        )
        self.env["stock.warehouse.orderpoint"].create(
            {
                "name": "Cake RR",
                "route_id": route.id,
                "location_id": self.stock_location_14.id,
                "product_id": self.product_storable_no.id,
                "product_min_qty": 0,
                "product_max_qty": 1,
                "trigger": "auto",
            }
        )
        self.product_product_3.is_storable = True
        repair_order = self.env["repair.order"].create(
            {
                "product_id": self.product_product_3.id,
                "product_uom_id": self.product_product_3.uom_id.id,
                "partner_id": self.res_partner_12.id,
                "location_id": self.stock_location_14.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product_storable_no.id,
                            "product_uom_qty": 1.0,
                            "state": "draft",
                            "repair_line_type": "add",
                        }
                    )
                ],
            }
        )
        validate_action = repair_order.action_validate()
        self.assertEqual(
            validate_action.get("res_model"),
            "wizard.repair.order.confirm.insufficient.stock",
        )
        warn_qty_wizard = Form(
            self.env["wizard.repair.order.confirm.insufficient.stock"].with_context(
                **validate_action["context"]
            )
        ).save()
        warn_qty_wizard.action_proceed()
        self.assertEqual(
            repair_order.state,
            "confirmed",
            'Repair order should be in "Confirmed" state.',
        )
        move = self.env["stock.move"].search(
            [
                ("product_id", "=", self.product_storable_no.id),
                (
                    "location_dest_id",
                    "=",
                    self.stock_location_14.id,
                ),
            ]
        )
        self.assertTrue(move.picking_id)
        self.assertFalse(move.repair_id)
        self.assertEqual(move.location_id, self.stock_warehouse.lot_stock_id)
        self.assertEqual(move.location_dest_id, self.stock_location_14)

    def test_open_and_create_repair_from_lot(self):
        sn_1 = self.env["product.trace"].create(
            {"name": "sn_1", "product_id": self.product_storable_serial.id}
        )
        action = sn_1.action_lot_open_repairs()
        context = action.get("context")
        tracked_product_repair_line = self.env["product.product"].create(
            {
                "name": "Test Product",
                "is_storable": True,
                "tracking": "serial",
            }
        )
        tracked_product_sn = self.env["product.trace"].create(
            {
                "name": "tracked_product_sn1",
                "product_id": tracked_product_repair_line.id,
            }
        )
        repair_order = (
            self.env["repair.order"]
            .with_context(context)
            .create(
                {
                    "product_id": self.product_storable_serial.id,
                    "product_uom_id": self.product_storable_serial.uom_id.id,
                    "location_id": self.stock_warehouse.lot_stock_id.id,
                    "trace_id": sn_1.id,
                    "picking_type_id": self.stock_warehouse.repair_type_id.id,
                }
            )
        )
        repair_order.with_context(context).move_ids = [
            Command.create(
                {
                    "product_id": tracked_product_repair_line.id,
                    "product_uom_qty": 1.0,
                    "repair_line_type": "add",
                    "trace_ids": [(4, tracked_product_sn.id)],
                    "quantity": 1.0,
                }
            )
        ]
        self.assertEqual(repair_order.trace_id, sn_1)
        copied_move = repair_order.move_ids.copy()
        self.assertFalse(copied_move.repair_id)

    def test_missing_inventory_loss_location_raises_user_error(self):
        inv_locations = self.env["stock.location"].search(
            [
                ("usage", "=", "inventory"),
                ("company_id", "=", self.env.company.id),
            ]
        )
        if inv_locations:
            inv_locations.write({"usage": "internal"})
        with self.assertRaises(UserError):
            self.env["stock.warehouse"].create(
                {
                    "name": "ELCT",
                    "code": "ET",
                }
            )

    def test_add_product_from_catalog(self):
        catalog_action = self.repair0.action_add_from_catalog()
        domain = catalog_action.get("domain")
        self.assertEqual(self.product_order_repair.type, "service")
        self.assertEqual(self.product_product_11.type, "consu")
        self.assertTrue(self.product_product_11.filtered_domain(domain))
        self.assertFalse(self.product_order_repair.filtered_domain(domain))

    def test_search_date_category(self):
        self.env["repair.order"].search([]).unlink()
        repair_order = self.env["repair.order"].create(
            {
                "partner_id": self.res_partner_1.id,
                "schedule_date": fields.Datetime.now(),
                "picking_type_id": self.stock_warehouse.repair_type_id.id,
            }
        )
        repair_order.action_validate()
        repairs = self.env["repair.order"].search(
            [("date_category", "in", ["yesterday", "today"])]
        )
        self.assertEqual(len(repairs), 1)

    def test_sale_order_line_discount_on_repair_order(self):
        repair_order = self.repair0
        repair_order.action_create_sale_order()
        sale_line = repair_order.move_ids.sale_line_id
        sale_line.discount = 15
        repair_order.action_validate()
        repair_order.action_repair_start()
        repair_order.action_repair_end()
        self.assertEqual(sale_line.discount, 15)

    def test_delete_repair_resets_outgoing_stock_moves(self):
        repair = self._create_simple_repair_order()
        self._create_simple_part_move(repair.id, 1.0)
        moves = repair.move_ids
        self.assertEqual(repair.state, "draft")
        self.assertEqual(moves.state, "draft")
        repair.unlink()
        self.assertFalse(repair.exists())
        self.assertFalse(moves.exists())

    def test_unlinking_a_confirmed_part_cancels_it_once(self):
        repair = self._create_simple_repair_order()
        part = self._create_simple_part_move(repair.id, 1.0)
        repair.action_validate()
        self.assertNotIn(part.state, ("draft", "cancel"))
        StockMove = type(self.env["stock.move"])
        original = StockMove._action_cancel
        cancelled = []

        def counting(moves):
            cancelled.extend(moves.ids)
            return original(moves)

        with patch.object(StockMove, "_action_cancel", counting):
            part.unlink()

        self.assertFalse(part.exists())
        self.assertEqual(cancelled.count(part.id), 1)


@tagged("post_install", "-at_install")
class TestRepairHttp(HttpCase):
    def test_repair_without_product_in_parts(self):
        self.env["res.partner"].create({"name": "A Partner"})
        product = self.env["product.product"].create(
            {"name": "A Product", "default_code": "1234"}
        )
        repair = self.env["repair.order"].create(
            {
                "move_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_uom_qty": 1.0,
                            "repair_line_type": "add",
                        }
                    )
                ],
            }
        )

        self.start_tour(
            f"/odoo/repairs/{repair.id}",
            "test_repair_without_product_in_parts",
            login="admin",
        )
        self.assertTrue(repair.has_uncomplete_moves)
