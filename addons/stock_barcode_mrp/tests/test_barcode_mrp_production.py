from unittest.mock import patch

from odoo import Command
from odoo.tests import Form

from odoo.addons.stock_barcode.tests.test_barcode_client_action import (
    TestBarcodeClientAction,
)


class TestMRPBarcodeClientAction(TestBarcodeClientAction):
    def setUp(self):
        super().setUp()

        self.component01 = self.env["product.product"].create(
            {
                "name": "Compo 01",
                "is_storable": True,
                "barcode": "compo01",
            }
        )
        self.component_lot = self.env["product.product"].create(
            {
                "name": "Compo Lot",
                "is_storable": True,
                "barcode": "compo_lot",
                "tracking": "lot",
            }
        )

        self.final_product = self.env["product.product"].create(
            {
                "name": "Final Product",
                "is_storable": True,
                "barcode": "final",
            }
        )

        self.final_product_lot = self.env["product.product"].create(
            {
                "name": "Final Product2",
                "is_storable": True,
                "barcode": "final_lot",
                "tracking": "lot",
            }
        )

        self.by_product = self.env["product.product"].create(
            {"name": "By Product", "is_storable": True, "barcode": "byproduct"}
        )

        self.bom_lot = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.final_product_lot.product_tmpl_id.id,
                "product_qty": 2.0,
                "bom_line_ids": [
                    (0, 0, {"product_id": self.component01.id, "product_qty": 2.0}),
                    (0, 0, {"product_id": self.component_lot.id, "product_qty": 2.0}),
                ],
            }
        )

    def test_barcode_production_process(self):
        self.env["stock.quant"].create(
            {
                "quantity": 4,
                "product_id": self.component01.id,
                "location_id": self.stock_location.id,
            }
        )

        mo = self.env["mrp.production"].create(
            {
                "product_id": self.final_product.id,
                "product_qty": 1,
                "move_raw_ids": [
                    (0, 0, {"product_id": self.component01.id, "product_uom_qty": 2})
                ],
            }
        )

        mo.action_confirm()

        url = "/odoo/action-stock_barcode.stock_picking_type_action_kanban"
        self.start_tour(url, "test_process_confirmed_mo", login="admin", timeout=180)
        self.assertEqual(mo.state, "done")
        self.assertEqual(mo.qty_produced, 1)
        self.assertEqual(mo.qty_producing, 1)
        url = f"/odoo/{mo.id}/action-stock_barcode_mrp.stock_barcode_mo_client_action"
        self.start_tour(url, "test_scrap_done_mo", login="admin")
        self.assertRecordValues(
            mo.scrap_ids,
            [
                {"product_id": self.final_product.id, "scrap_qty": 1, "state": "done"},
            ],
        )

    def test_barcode_production_create(self):
        self.env["stock.quant"].create(
            {
                "quantity": 4,
                "product_id": self.component01.id,
                "location_id": self.stock_location.id,
            }
        )
        self.start_tour(
            "/odoo/barcode", "test_barcode_production_create", login="admin"
        )
        mo = self.env["mrp.production"].search([], order="id desc", limit=1)
        self.assertEqual(mo.state, "done")
        self.assertEqual(mo.qty_produced, 2)
        self.assertRecordValues(
            mo.move_raw_ids,
            [
                {"product_id": self.component01.id, "product_uom_qty": 2},
            ],
        )

    def test_barcode_production_create_bom(self):
        component02 = self.env["product.product"].create(
            {
                "name": "Compo 02",
                "is_storable": True,
                "barcode": "compo02",
            }
        )
        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.final_product.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    (0, 0, {"product_id": self.component01.id, "product_qty": 2.0}),
                    (0, 0, {"product_id": component02.id, "product_qty": 3.0}),
                ],
            }
        )
        for component in [self.component01, component02]:
            self.env["stock.quant"].create(
                {
                    "quantity": 99,
                    "product_id": component.id,
                    "location_id": self.stock_location.id,
                }
            )

        url = "/odoo/action-stock_barcode.stock_picking_type_action_kanban"
        self.start_tour(url, "test_barcode_production_create_bom", login="admin")
        manufacturing_orders = self.env["mrp.production"].search(
            [], order="id desc", limit=2
        )
        for mo in manufacturing_orders:
            self.assertEqual(mo.state, "done")
            self.assertEqual(mo.qty_produced, 3)
            self.assertRecordValues(
                mo.move_raw_ids,
                [
                    {
                        "product_id": self.component01.id,
                        "product_uom_qty": 2,
                        "quantity": 6,
                    },
                    {"product_id": component02.id, "product_uom_qty": 3, "quantity": 9},
                ],
            )

    def test_barcode_production_create_tracked_bom(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("mrp.group_mrp_byproducts").id),
                ],
            }
        )
        self.env["stock.quant"].create(
            {
                "quantity": 4,
                "product_id": self.component01.id,
                "location_id": self.stock_location.id,
            }
        )
        trace_id = self.env["product.trace"].create(
            {
                "name": "lot01",
                "product_id": self.component_lot.id,
            }
        )
        self.env["stock.quant"].create(
            {
                "quantity": 4,
                "product_id": self.component_lot.id,
                "location_id": self.stock_location.id,
                "trace_id": trace_id.id,
            }
        )
        self.start_tour(
            "/odoo/barcode", "test_barcode_production_create_tracked_bom", login="admin"
        )
        mo = self.env["mrp.production"].search([], order="id desc", limit=1)
        self.assertEqual(mo.state, "done")
        self.assertEqual(mo.qty_produced, 3)
        self.assertRecordValues(
            mo.move_raw_ids,
            [
                {
                    "product_id": self.component01.id,
                    "product_uom_qty": 3,
                    "quantity": 3,
                },
                {
                    "product_id": self.component_lot.id,
                    "product_uom_qty": 3,
                    "quantity": 3,
                },
            ],
        )
        self.assertRecordValues(
            mo.move_byproduct_ids,
            [
                {"product_id": self.by_product.id, "product_uom_qty": 2, "quantity": 2},
            ],
        )

    def test_barcode_production_generate_serial_numbers(self):
        group_tracking = self.env.ref("stock.group_production_lot")
        self.env.user.write({"group_ids": [Command.link(group_tracking.id)]})
        self.final_product_lot.tracking = "serial"
        sequence = self.env["ir.sequence"].search(
            [("code", "=", "product.trace")], limit=1
        )
        sequence.write({"number_next_actual": 128})
        lot = self.env["product.trace"].create(
            {"name": "boptilot-001", "product_id": self.component_lot.id}
        )
        self.env["stock.quant"]._update_available_quantity(
            self.component01, self.stock_location, quantity=99
        )
        self.env["stock.quant"]._update_available_quantity(
            self.component_lot, self.stock_location, quantity=99, trace_id=lot
        )
        productions = self.env["mrp.production"].create(
            [
                {
                    "name": f"MO/TEST/{i}",
                    "bom_id": self.bom_lot.id,
                    "product_id": self.final_product_lot.id,
                    "product_qty": qty,
                }
                for (i, qty) in [(1, 1), (2, 5), (3, 10)]
            ]
        )
        productions.action_confirm()
        self.start_tour(
            "/odoo/barcode",
            "test_barcode_production_generate_serial_numbers",
            login="admin",
        )

    def test_barcode_production_reserved_from_multiple_locations(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        picking_type_production = self.env["stock.picking.type"].search(
            [("code", "=", "mrp_operation"), ("company_id", "=", self.env.company.id)]
        )
        picking_type_production.restrict_scan_dest_location = "no"
        picking_type_production.restrict_scan_source_location = "mandatory"
        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.final_product.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    (0, 0, {"product_id": self.component01.id, "product_qty": 2.0}),
                ],
            }
        )
        self.env["stock.quant"].create(
            {
                "quantity": 1,
                "product_id": self.component01.id,
                "location_id": self.shelf1.id,
            }
        )
        self.env["stock.quant"].create(
            {
                "quantity": 2,
                "product_id": self.component01.id,
                "location_id": self.shelf2.id,
            }
        )
        self.env["stock.quant"].create(
            {
                "quantity": 2,
                "product_id": self.component01.id,
                "location_id": self.shelf3.id,
            }
        )
        self.env["stock.quant"].create(
            {
                "quantity": 1,
                "product_id": self.component01.id,
                "location_id": self.shelf4.id,
            }
        )
        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.final_product
        mo_form.product_qty = 3
        mo = mo_form.save()
        mo.action_confirm()

        url = f"/odoo/{mo.id}/action-stock_barcode_mrp.stock_barcode_mo_client_action"
        self.start_tour(
            url,
            "test_barcode_production_reserved_from_multiple_locations",
            login="admin",
            timeout=180,
        )

    def test_barcode_production_scan_other_than_reserved(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )
        picking_type_production = self.env["stock.picking.type"].search(
            [("code", "=", "mrp_operation"), ("company_id", "=", self.env.company.id)]
        )
        picking_type_production.restrict_scan_source_location = "mandatory"
        picking_type_production.show_reserved_sns = True
        lot_01 = self.env["product.trace"].create(
            {
                "name": "lot_01",
                "product_id": self.component_lot.id,
            }
        )
        lot_02 = self.env["product.trace"].create(
            {
                "name": "lot_02",
                "product_id": self.component_lot.id,
            }
        )
        self.env["stock.quant"].create(
            {
                "quantity": 2,
                "product_id": self.component01.id,
                "location_id": self.stock_location.id,
            }
        )
        self.env["stock.quant"].create(
            {
                "quantity": 2,
                "product_id": self.component01.id,
                "location_id": self.shelf1.id,
            }
        )
        self.env["stock.quant"].create(
            {
                "quantity": 2,
                "product_id": self.component_lot.id,
                "location_id": self.stock_location.id,
                "trace_id": lot_01.id,
            }
        )
        self.env["stock.quant"].create(
            {
                "quantity": 2,
                "product_id": self.component_lot.id,
                "location_id": self.stock_location.id,
                "trace_id": lot_02.id,
            }
        )

        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.final_product_lot
        mo_form.product_qty = 2
        mo = mo_form.save()
        mo.action_confirm()

        url = f"/odoo/{mo.id}/action-stock_barcode_mrp.stock_barcode_mo_client_action"
        self.start_tour(
            url,
            "test_barcode_production_scan_other_than_reserved",
            login="admin",
            timeout=180,
        )

        self.assertEqual(mo.state, "done")
        self.assertEqual(len(mo.move_raw_ids.move_line_ids), 2)
        self.assertRecordValues(
            mo.move_raw_ids,
            [
                {
                    "product_id": self.component01.id,
                    "product_uom_qty": 2,
                    "quantity": 2,
                    "trace_ids": [],
                    "location_id": self.stock_location.id,
                },
                {
                    "product_id": self.component_lot.id,
                    "product_uom_qty": 2,
                    "quantity": 2,
                    "trace_ids": lot_02.ids,
                    "location_id": self.stock_location.id,
                },
            ],
        )
        self.assertRecordValues(
            mo.move_raw_ids.move_line_ids,
            [
                {
                    "product_id": self.component01.id,
                    "quantity": 2,
                    "trace_id": False,
                    "location_id": self.shelf1.id,
                },
                {
                    "product_id": self.component_lot.id,
                    "quantity": 2,
                    "trace_id": lot_02.id,
                    "location_id": self.stock_location.id,
                },
            ],
        )
        self.assertRecordValues(
            mo.finished_move_line_ids,
            [
                {"product_id": self.final_product_lot.id, "quantity": 2},
            ],
        )
        self.assertEqual(mo.finished_move_line_ids.trace_id.name, "finished_lot")

    def test_barcode_production_component_no_stock(self):
        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.final_product.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    (0, 0, {"product_id": self.component01.id, "product_qty": 2.0}),
                ],
            }
        )
        url = "/odoo/action-stock_barcode.stock_picking_type_action_kanban"
        self.start_tour(
            url,
            "test_barcode_production_component_no_stock",
            login="admin",
            timeout=180,
        )

    def test_mo_scrap_digipad_view(self):
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.final_product.id,
                "product_qty": 1,
                "move_raw_ids": [
                    (0, 0, {"product_id": self.component01.id, "product_uom_qty": 1})
                ],
            }
        )
        mo.action_confirm()

        url = f"/odoo/{mo.id}/action-stock_barcode_mrp.stock_barcode_mo_client_action"
        self.start_tour(url, "test_mo_scrap_digipad_view", login="admin", timeout=180)

    def test_barcode_production_components_reservation_state(self):
        self.env["stock.quant"].create(
            {
                "quantity": 4,
                "product_id": self.component01.id,
                "location_id": self.stock_location.id,
            }
        )
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.final_product.id,
                "product_qty": 1,
                "move_raw_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.component01.id,
                            "product_uom_qty": 2,
                            "picked": False,
                        },
                    )
                ],
            }
        )
        mo.action_confirm()
        url = f"/odoo/{mo.id}/action-stock_barcode_mrp.stock_barcode_mo_client_action"

        self.assertEqual(
            mo.move_raw_ids.move_line_ids.quantity, mo.move_raw_ids.product_uom_qty
        )
        self.start_tour(
            url,
            "test_barcode_production_components_reservation_state_reserved",
            login="admin",
            timeout=180,
        )

        self.assertEqual(len(mo.move_raw_ids.move_line_ids), 1)
        mo.action_unreserve()
        self.assertEqual(len(mo.move_raw_ids.move_line_ids), 0)
        self.start_tour(
            url,
            "test_barcode_production_components_reservation_state_unreserved",
            login="admin",
            timeout=180,
        )
        self.assertEqual(
            len(mo.move_raw_ids.move_line_ids),
            0,
            "Verify MO components are still unreserved after open the MO in the Barcode app",
        )

    def test_barcode_production_add_scrap(self):
        component02 = self.env["product.product"].create(
            {
                "name": "Compo 02",
                "is_storable": True,
                "barcode": "compo02",
            }
        )
        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.final_product.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    (0, 0, {"product_id": self.component01.id, "product_qty": 1.0}),
                    (0, 0, {"product_id": component02.id, "product_qty": 1.0}),
                ],
            }
        )
        for component in [self.component01, component02]:
            self.env["stock.quant"].create(
                {
                    "quantity": 99,
                    "product_id": component.id,
                    "location_id": self.stock_location.id,
                }
            )

        url = "/odoo/action-stock_barcode.stock_picking_type_action_kanban"
        self.start_tour(
            url, "test_barcode_production_add_scrap", login="admin", timeout=180
        )
        mo = self.env["mrp.production"].search([], order="id desc", limit=1)
        self.assertEqual(mo.scrap_count, 1)
        self.assertEqual(mo.scrap_ids.product_id.name, "Compo 01")

    def test_barcode_production_add_byproduct(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("mrp.group_mrp_byproducts").id),
                    Command.link(self.env.ref("stock.group_production_lot").id),
                ],
            }
        )
        warehouse = self.stock_location.warehouse_id
        warehouse.manu_type_id.use_create_components_lots = False
        warehouse.manufacture_steps = "pbm_sam"
        component02 = self.env["product.product"].create(
            {
                "name": "Compo 02",
                "is_storable": True,
                "barcode": "compo02",
            }
        )
        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.final_product.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    (0, 0, {"product_id": self.component01.id, "product_qty": 1.0}),
                    (0, 0, {"product_id": component02.id, "product_qty": 1.0}),
                ],
            }
        )
        for component in [self.component01, component02]:
            self.env["stock.quant"].create(
                {
                    "quantity": 99,
                    "product_id": component.id,
                    "location_id": warehouse.pbm_loc_id.id,
                }
            )

        url = "/odoo/action-stock_barcode.stock_picking_type_action_kanban"
        self.start_tour(
            url, "test_barcode_production_add_byproduct", login="admin", timeout=180
        )
        mo = self.env["mrp.production"].search([], order="id desc", limit=1)
        self.assertRecordValues(
            mo.move_byproduct_ids,
            [
                {
                    "product_id": self.by_product.id,
                    "location_dest_id": warehouse.sam_loc_id.id,
                },
                {
                    "product_id": self.component_lot.id,
                    "location_dest_id": warehouse.sam_loc_id.id,
                },
            ],
        )
        self.assertEqual(mo.move_byproduct_ids[1].trace_ids.name, "byprod_lot_001")

    def test_split_line_on_exit_for_production(self):
        product_final = self.env["product.product"].create(
            {
                "name": "Final Product",
                "is_storable": True,
            }
        )
        bom = self.env["mrp.bom"].create(
            {
                "product_id": product_final.id,
                "product_tmpl_id": product_final.product_tmpl_id.id,
                "product_uom_id": product_final.uom_id.id,
                "product_qty": 1.0,
                "type": "normal",
                "consumption": "flexible",
                "bom_line_ids": [
                    (0, 0, {"product_id": self.product1.id, "product_qty": 2}),
                    (0, 0, {"product_id": self.product2.id, "product_qty": 1}),
                ],
            }
        )

        self.env["stock.quant"].create(
            {
                "quantity": 4,
                "product_id": self.product1.id,
                "location_id": self.stock_location.id,
            }
        )
        self.env["stock.quant"].create(
            {
                "quantity": 2,
                "product_id": self.product2.id,
                "location_id": self.stock_location.id,
            }
        )

        production = self.env["mrp.production"].create(
            {
                "name": "production_split_line_on_exit",
                "bom_id": bom.id,
                "product_id": product_final.id,
                "product_qty": 2,
            }
        )
        production.action_confirm()

        self.start_tour(
            "odoo/barcode/", "test_split_line_on_exit_for_production", login="admin"
        )
        self.assertRecordValues(
            production.move_raw_ids,
            [
                {"product_id": self.product1.id, "quantity": 4, "picked": True},
                {"product_id": self.product2.id, "quantity": 2, "picked": True},
            ],
        )
        self.assertRecordValues(
            production.move_raw_line_ids,
            [
                {"product_id": self.product1.id, "quantity": 3, "picked": True},
                {"product_id": self.product1.id, "quantity": 1, "picked": False},
                {"product_id": self.product2.id, "quantity": 1, "picked": True},
                {"product_id": self.product2.id, "quantity": 1, "picked": False},
            ],
        )

    def test_mrp_uncompleted_move_split_on_barcode_exit(self):
        available_comp, unavailable_comp = self.component01, self.product1
        unavailable_comp.write(
            {"name": "Compo 02", "code": False, "default_code": False}
        )
        self.env["stock.quant"]._update_available_quantity(
            available_comp, self.stock_location, quantity=20
        )

        manufacturing_order = self.env["mrp.production"].create(
            {
                "name": "TMUMSOBE mo",
                "product_id": self.final_product.id,
                "product_qty": 20,
                "move_raw_ids": [
                    Command.create(
                        {
                            "product_id": available_comp.id,
                            "product_uom_qty": 20,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": unavailable_comp.id,
                            "product_uom_qty": 4,
                        }
                    ),
                ],
            }
        )
        manufacturing_order.action_confirm()
        with Form(manufacturing_order) as mo_form:
            mo_form.qty_producing = 10.0
        self.assertRecordValues(
            manufacturing_order.move_raw_ids.sorted("quantity"),
            [
                {"product_uom_qty": 4.0, "quantity": 2.0, "picked": True},
                {"product_uom_qty": 20.0, "quantity": 10.0, "picked": True},
            ],
        )
        action = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = f"/web#action={action.id}"
        self.start_tour(
            url, "test_mrp_uncompleted_move_split_on_barcode_exit", login="admin"
        )
        self.assertRecordValues(
            manufacturing_order.move_raw_ids.sorted("quantity"),
            [
                {"product_uom_qty": 4.0, "quantity": 3.0, "picked": True},
                {"product_uom_qty": 20.0, "quantity": 10.0, "picked": True},
            ],
        )
        self.assertRecordValues(
            manufacturing_order.move_raw_ids.move_line_ids.sorted("quantity"),
            [
                {"product_id": unavailable_comp.id, "quantity": 3.0, "picked": True},
                {"product_id": available_comp.id, "quantity": 4.0, "picked": True},
                {"product_id": available_comp.id, "quantity": 6.0, "picked": False},
            ],
        )

    def test_barcode_production_component_different_uom(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("base.group_uom").id)]}
        )
        uom_kg = self.env.ref("base.product_uom_kgm")
        uom_gm = self.env.ref("base.product_uom_gram")
        self.component01.uom_id = uom_gm
        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.final_product.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.component01.id,
                            "product_qty": 1.0,
                            "product_uom_id": uom_kg.id,
                        },
                    ),
                ],
            }
        )
        url = "/odoo/action-stock_barcode.stock_picking_type_action_kanban"
        self.start_tour(
            url,
            "test_barcode_production_component_different_uom",
            login="admin",
            timeout=180,
        )

    def test_multi_company_manufacture_creation_in_barcode(self):
        company2 = self.env["res.company"].create({"name": "second company"})
        self.env.user.company_ids = [(4, company2.id)]
        self.env["stock.picking.type"].search(
            [
                ("code", "=", "mrp_operation"),
                ("company_id", "=", company2.id),
            ],
            limit=1,
        ).barcode = "company2_mrp_operation"

        cids = "-".join(str(cid) for cid in self.env.user.company_ids.ids)
        url = "/odoo/action-stock_barcode.stock_barcode_action_main_menu"
        self.start_tour(
            url,
            "test_multi_company_manufacture_creation_in_barcode",
            login="admin",
            timeout=180,
            cookies={"cids": cids},
        )

        self.assertEqual(
            len(self.env["mrp.production"].search([("company_id", "=", company2.id)])),
            2,
        )

    def test_multi_company_record_access_in_mrp_barcode(self):
        company2 = self.env["res.company"].create({"name": "second company"})
        company2_product = self.env["product.product"].create(
            {
                "name": "second company product",
                "company_id": company2.id,
                "barcode": "second_company_product",
            }
        )

        self.env["stock.picking.type"].search(
            [
                ("code", "=", "mrp_operation"),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        ).barcode = "company_mrp_operation"

        cids = "-".join(str(cid) for cid in self.env.user.company_ids.ids)
        url = "/odoo/action-stock_barcode.stock_barcode_action_main_menu"
        self.start_tour(
            url,
            "test_multi_company_record_access_in_mrp_barcode",
            login="admin",
            timeout=180,
            cookies={"cids": cids},
        )

        self.assertFalse(
            self.env["mrp.production"].search(
                [
                    ("company_id", "=", self.env.company.id),
                    ("product_id", "=", company2_product.id),
                ],
                limit=1,
            )
        )

        companies = self.env.company + company2
        self.env = self.env(
            context=dict(self.env.context, allowed_company_ids=companies.ids)
        )
        self.env["stock.picking.type"].search(
            [
                ("code", "=", "mrp_operation"),
                ("company_id", "=", company2.id),
            ],
            limit=1,
        ).barcode = "company2_mrp_operation"
        cids += f"-{company2.id}"
        self.start_tour(
            url,
            "test_multi_company_record_access_in_mrp_barcode2",
            login="admin",
            timeout=180,
            cookies={"cids": cids},
        )

        self.assertTrue(
            self.env["mrp.production"].search(
                [
                    ("company_id", "=", company2.id),
                    ("product_id", "=", company2_product.id),
                ],
                limit=1,
            )
        )

    def test_kit_bom_decomposition_keeps_location(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        self.picking_type_internal.active = True

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 10.0
        )
        self.env["stock.quant"]._update_available_quantity(
            self.component01, self.stock_location, 10.0
        )

        final_2 = self.env["product.product"].create(
            {
                "name": "final2",
                "is_storable": True,
                "barcode": "final2",
            }
        )
        for comp1, comp2, final_prod in [
            (self.component01, self.product1, self.final_product),
            (self.component01, self.product2, final_2),
        ]:
            self.env["mrp.bom"].create(
                {
                    "product_tmpl_id": final_prod.product_tmpl_id.id,
                    "product_id": final_prod.id,
                    "product_qty": 1.0,
                    "type": "phantom",
                    "bom_line_ids": [
                        (0, 0, {"product_id": comp1.id, "product_qty": 1.0}),
                        (0, 0, {"product_id": comp2.id, "product_qty": 1.0}),
                    ],
                }
            )

        test_pickings = self.env["stock.picking"]
        for i in range(1, 3):
            test_pickings += self.env["stock.picking"].create(
                {
                    "name": f"test_kit_bom_decomposition_keeps_location_picking{i}",
                    "picking_type_id": self.picking_type_internal.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.stock_location.id,
                }
            )

        url = "/odoo/action-stock_barcode.stock_barcode_action_main_menu"
        self.start_tour(
            url, "test_kit_bom_decomposition_keeps_location", login="admin", timeout=180
        )

        expected_move_line_vals_list = [
            [
                {
                    "product_id": self.component01.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.shelf1.id,
                },
                {
                    "product_id": self.product1.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.shelf1.id,
                },
                {
                    "product_id": self.component01.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.shelf2.id,
                },
                {
                    "product_id": self.product1.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.shelf2.id,
                },
            ],
            [
                {
                    "product_id": self.component01.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.shelf1.id,
                },
                {
                    "product_id": self.product1.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.shelf1.id,
                },
                {
                    "product_id": self.component01.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.shelf2.id,
                },
                {
                    "product_id": self.product2.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.shelf2.id,
                },
            ],
        ]

        for test_picking, expected_move_line_vals in zip(
            test_pickings, expected_move_line_vals_list, strict=True
        ):
            self.assertRecordValues(test_picking.move_line_ids, expected_move_line_vals)

    def test_always_backorder_mo_without_redirect_to_backend(self):
        warehouse = self.stock_location.warehouse_id
        manufacturing_type = warehouse.manu_type_id
        manufacturing_type.create_backorder = "always"
        product = self.final_product
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "product_qty": 1.0,
            }
        )
        mo = self.env["mrp.production"].create(
            {
                "product_id": product.id,
                "product_qty": 3.0,
                "bom_id": bom.id,
            }
        )
        mo.action_confirm()

        action_id = self.env.ref("stock_barcode.stock_picking_type_action_kanban")
        url = "/web#action=" + str(action_id.id)
        self.start_tour(url, "test_always_backorder_mo", login="admin", timeout=180)
        self.assertRecordValues(mo, [{"state": "done", "qty_produced": 1.0}])
        bo = mo.backorder_ids - mo
        self.assertRecordValues(bo, [{"product_id": product.id, "product_qty": 2.0}])

    def test_always_backorder_from_barcode_is_posted_once_and_printed(self):
        manufacturing_type = self.stock_location.warehouse_id.manu_type_id
        manufacturing_type.write(
            {"create_backorder": "always", "auto_print_done_production_order": True}
        )
        bom = self.env["mrp.bom"].create(
            {"product_tmpl_id": self.final_product.product_tmpl_id.id}
        )
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.final_product.id,
                "product_qty": 3.0,
                "bom_id": bom.id,
                "picking_type_id": manufacturing_type.id,
            }
        )
        mo.action_confirm()
        mo.qty_producing = 1
        Production = self.registry["mrp.production"]
        post_inventory = Production._post_inventory
        posted = []

        def counting_post(records, cancel_backorder=False):
            if records:
                posted.append(records.ids)
            return post_inventory(records, cancel_backorder=cancel_backorder)

        with patch.object(Production, "_post_inventory", counting_post):
            action = mo.with_context(barcode_trigger=True).button_mark_done()

        self.assertEqual(posted, [mo.ids])
        self.assertRecordValues(mo, [{"state": "done", "qty_produced": 1.0}])
        self.assertEqual(action["tag"], "do_multi_print")
        self.assertEqual(
            [report["report_name"] for report in action["params"]["reports"]],
            [self.env.ref("mrp.action_report_production_order").report_name],
        )

    def test_backorder_partial_completion_save_sensible_split(self):
        available_comp, unavailable_comp = self.component01, self.product1
        self.env["stock.quant"]._update_available_quantity(
            available_comp, self.stock_location, quantity=10
        )

        manufacturing_order = self.env["mrp.production"].create(
            {
                "name": "TBPCSNS mo",
                "product_id": self.final_product.id,
                "product_qty": 10,
                "move_raw_ids": [
                    Command.create(
                        {
                            "product_id": available_comp.id,
                            "product_uom_qty": 10,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": unavailable_comp.id,
                            "product_uom_qty": 4,
                        }
                    ),
                ],
            }
        )
        manufacturing_order.action_confirm()

        action_id = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = f"/web#action={action_id.id}"
        self.start_tour(
            url,
            "test_backorder_partial_completion_save_sensible_split",
            login="admin",
            timeout=180,
        )
        self.assertEqual(manufacturing_order.state, "done")
        self.assertEqual(
            manufacturing_order.move_raw_ids.filtered(
                lambda m: m.product_id == unavailable_comp
            ).mapped("quantity"),
            [2.00],
        )
        backorder_mo = manufacturing_order.backorder_ids - manufacturing_order
        self.assertRecordValues(
            backorder_mo.move_raw_ids.sorted("product_uom_qty"),
            [
                {
                    "product_id": unavailable_comp.id,
                    "product_uom_qty": 2,
                    "quantity": 0,
                    "picked": False,
                },
                {
                    "product_id": available_comp.id,
                    "product_uom_qty": 5,
                    "quantity": 5,
                    "picked": False,
                },
            ],
        )
        self.assertRecordValues(
            backorder_mo.move_finished_ids,
            [
                {
                    "quantity": 5,
                    "product_uom_qty": 5,
                }
            ],
        )

    def test_backorder_partial_completion_preserves_reserved_qty_on_exit(self):
        manufacturing_order = self.env["mrp.production"].create(
            {
                "name": "TBPCSNS mo",
                "product_id": self.final_product.id,
                "product_qty": 1,
                "move_raw_ids": [
                    Command.create(
                        {
                            "product_id": self.component01.id,
                            "product_uom_qty": 6,
                        }
                    ),
                ],
            }
        )
        manufacturing_order.action_confirm()
        action_id = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = f"/web#action={action_id.id}"
        self.start_tour(
            url,
            "test_backorder_partial_completion_preserves_reserved_qty_on_exit",
            login="admin",
            timeout=180,
        )

    def test_barcode_mo_creation_in_mo2(self):
        mo2_operation_type = self.env["stock.picking.type"].create(
            {
                "name": "MO2",
                "barcode": "MO2_BARCODE",
                "code": "mrp_operation",
                "sequence_code": "MO2",
                "warehouse_id": self.warehouse.id,
            }
        )

        product_to_manufacture = self.env["product.product"].create(
            {
                "name": "Product4",
                "is_storable": True,
                "barcode": "MO2_TEST_PRODUCT",
            }
        )
        self.start_tour(
            "/odoo/barcode", "test_barcode_mo_creation_in_mo2", login="admin"
        )

        mos = self.env["mrp.production"].search(
            [("product_id", "=", product_to_manufacture.id)]
        )
        self.assertEqual(
            len(mos), 2, "Two Manufacturing Orders must have been created."
        )
        self.assertEqual(
            mos[0].picking_type_id,
            mo2_operation_type,
            "The first MO was not created with the correct operation type (MO2).",
        )
        self.assertEqual(
            mos[1].picking_type_id,
            mo2_operation_type,
            "The second MO was not created with the correct operation type (MO2).",
        )

    def test_barcode_mo_creation_in_scan_mo2(self):
        mo2_operation_type = self.env["stock.picking.type"].create(
            {
                "name": "MO2",
                "code": "mrp_operation",
                "sequence_code": "MO2",
                "warehouse_id": self.warehouse.id,
            }
        )

        product_to_manufacture = self.env["product.product"].create(
            {
                "name": "Test Product",
                "is_storable": True,
                "barcode": "MO2_TEST_PRODUCT",
            }
        )
        url = "/odoo/action-stock_barcode.stock_picking_type_action_kanban"
        self.start_tour(
            url, "test_barcode_mo_creation_in_scan_mo2", login="admin", timeout=180
        )

        mo = self.env["mrp.production"].search(
            [("product_id", "=", product_to_manufacture.id)], limit=1
        )
        self.assertTrue(mo, "The Manufacturing Order was not created.")
        self.assertEqual(
            mo.picking_type_id,
            mo2_operation_type,
            "The MO was not created with the correct operation type (MO2).",
        )

    def test_setting_barcode_mrp_allow_extra_product(self):
        picking_type_manufacturing = self.warehouse.manu_type_id
        picking_type_manufacturing.barcode_allow_extra_product = False

        self.env["stock.quant"].create(
            {
                "quantity": 4,
                "product_id": self.component01.id,
                "location_id": self.stock_location.id,
            }
        )

        mo = self.env["mrp.production"].create(
            {
                "product_id": self.final_product.id,
                "product_qty": 1,
                "move_raw_ids": [
                    Command.create(
                        {"product_id": self.component01.id, "product_uom_qty": 2}
                    )
                ],
            }
        )
        mo.action_confirm()

        url = f"/odoo/{mo.id}/action-stock_barcode_mrp.stock_barcode_mo_client_action"
        self.start_tour(
            url, "test_setting_barcode_mrp_allow_extra_product", login="admin"
        )

    def test_no_split_uncompleted_done_move(self):
        self.env["stock.quant"]._update_available_quantity(
            self.component01, self.stock_location, quantity=2
        )

        manufacturing_order = self.env["mrp.production"].create(
            {
                "name": "TBPCSNS mo",
                "product_id": self.final_product.id,
                "product_qty": 1,
                "move_raw_ids": [
                    Command.create(
                        {
                            "product_id": self.component01.id,
                            "product_uom_qty": 2,
                        }
                    ),
                ],
            }
        )
        manufacturing_order.action_confirm()

        action_id = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = f"/web#action={action_id.id}"
        self.start_tour(
            url, "test_no_split_uncompleted_done_move", login="admin", timeout=180
        )

        self.assertEqual(manufacturing_order.state, "done")
        self.assertRecordValues(
            manufacturing_order.move_finished_ids,
            [{"quantity": 1, "product_uom_qty": 1}],
        )
        self.assertRecordValues(
            manufacturing_order.move_raw_ids, [{"quantity": 1, "product_uom_qty": 2}]
        )

    def test_add_product_with_different_uom(self):
        new_uom = self.env["uom.uom"].create(
            {"name": "Little Boutch", "rounding": 0.01}
        )
        self.product1.uom_id = new_uom.id
        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.final_product
        mo_form.product_qty = 1
        mo = mo_form.save()
        mo.action_confirm()
        action = self.env.ref("stock_barcode_mrp.stock_barcode_mo_client_action")
        url = "/web#action=%s&active_id=%s" % (action.id, mo.id)
        self.start_tour(url, "test_add_product_with_different_uom", login="admin")
        self.assertEqual(
            mo.move_raw_ids.product_uom_id, mo.move_raw_ids.product_id.uom_id
        )
        self.assertEqual(mo.state, "done")

    def test_not_allowing_component_lot_creation(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("mrp.group_mrp_byproducts").id),
                ],
            }
        )
        product = self.final_product
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    Command.create(
                        {"product_id": self.productserial1.id, "product_qty": 1.0}
                    )
                ],
            }
        )
        mo = self.env["mrp.production"].create(
            {
                "name": "TNACLC",
                "product_id": self.final_product.id,
                "product_qty": 1.0,
                "bom_id": bom.id,
            }
        )
        lots = self.env["product.trace"].create(
            [
                {
                    "name": "SN005",
                    "product_id": self.productserial1.id,
                    "company_id": self.env.company.id,
                },
                {
                    "name": "SN008",
                    "product_id": self.productserial1.id,
                    "company_id": self.env.company.id,
                },
            ]
        )
        for lot in lots:
            self.env["stock.quant"]._update_available_quantity(
                self.productserial1, self.stock_location, 1, trace_id=lot
            )
        mo.action_confirm()
        self.assertEqual(mo.move_raw_line_ids.trace_id, lots[0])
        self.by_product.tracking = "serial"
        action_id = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = f"/web#action={action_id.id}"
        self.start_tour(url, "test_not_allowing_component_lot_creation", login="admin")
        self.assertEqual(mo.move_raw_line_ids.trace_id, lots[1])
        self.assertEqual(mo.move_byproduct_ids.move_line_ids.lot_name, "77734319")

    def test_mo_barcode_byproduct_destination_location(self):
        picking_type_production = self.env["stock.picking.type"].search(
            [("code", "=", "mrp_operation"), ("company_id", "=", self.env.company.id)]
        )
        picking_type_production.restrict_scan_source_location = "mandatory"
        grp_by_product = self.env.ref("mrp.group_mrp_byproducts")
        grp_multi_loc = self.env.ref("stock.group_stock_multi_locations")
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(grp_by_product.id),
                    Command.link(grp_multi_loc.id),
                ]
            }
        )

        self.bom_lot.write(
            {
                "byproduct_ids": [
                    Command.create(
                        {"product_id": self.by_product.id, "product_qty": 1.0}
                    ),
                    Command.create(
                        {"product_id": self.component01.id, "product_qty": 1.0}
                    ),
                ],
            }
        )

        mo = self.env["mrp.production"].create(
            {
                "product_id": self.final_product.id,
                "product_qty": 1,
                "bom_id": self.bom_lot.id,
            }
        )
        mo.action_confirm()

        mo.move_byproduct_ids[0].location_dest_id = self.shelf1.id
        mo.move_byproduct_ids[1].location_dest_id = self.shelf2.id

        action = self.env.ref("stock_barcode_mrp.stock_barcode_mo_client_action")
        url = f"/web#action={action.id}&active_id={mo.id}"
        self.start_tour(
            url, "test_mo_barcode_byproduct_destination_location", login="admin"
        )

    def test_select_mo_component_line_scan_package_type(self):
        self.env.user.group_ids += self.env.ref("stock.group_tracking_lot")
        self.env["stock.package.type"].create(
            {"name": "stock package type 1", "barcode": "000555555555555555555555"}
        )
        manufacturing_order = self.env["mrp.production"].create(
            {
                "name": "tsmclspt MO",
                "product_id": self.final_product.id,
                "move_raw_ids": [
                    Command.create(
                        {
                            "product_id": self.component01.id,
                            "product_uom_qty": 2,
                        }
                    )
                ],
            }
        )
        manufacturing_order.action_confirm()
        action = self.env.ref("stock_barcode_mrp.stock_barcode_mo_client_action")
        url = "/web#action=%s&active_id=%s" % (action.id, manufacturing_order.id)
        self.start_tour(
            url, "test_select_mo_component_line_scan_package_type", login="admin"
        )
        self.assertEqual(manufacturing_order.state, "done")

    def test_create_all_transfers_for_3_step_manufacturing(self):
        self.env.user._get_default_warehouse_id().manufacture_steps = "pbm_sam"
        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.final_product.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    Command.create(
                        {"product_id": self.component01.id, "product_qty": 1.0}
                    ),
                ],
                "byproduct_ids": [
                    Command.create(
                        {"product_id": self.by_product.id, "product_qty": 2.0}
                    )
                ],
            }
        )

        action_id = self.env.ref("stock_barcode.stock_picking_type_action_kanban")
        url = "/web#action=" + str(action_id.id)
        self.start_tour(
            url, "test_create_all_transfers_for_3_step_manufacturing", login="admin"
        )

        mos = self.env["mrp.production"].search(
            [("product_id", "=", self.final_product.id)]
        )
        self.assertEqual(len(mos), 1, "There should be only 1 MO created via Barcode")
        self.assertEqual(
            len(mos.picking_ids),
            2,
            "2 transfers should be created for a 3-step manufacture process",
        )

        pick_component_transfer = mos.picking_ids.search(
            [("picking_type_id.name", "=", "Pick Components")]
        )
        store_final_transfer = mos.picking_ids.search(
            [("picking_type_id.name", "=", "Store Finished Product")]
        )

        self.assertEqual(
            pick_component_transfer.move_ids[0].product_id, self.component01
        )
        self.assertEqual(pick_component_transfer.move_ids[0].product_qty, 1)
        sfp_moves = store_final_transfer.move_ids
        final_move = sfp_moves.filtered(
            lambda move: move.product_id == self.final_product
        )
        by_product_move = sfp_moves.filtered(
            lambda move: move.product_id == self.by_product
        )
        self.assertEqual(len(sfp_moves), 2)
        self.assertEqual(final_move.product_qty, 1)
        self.assertEqual(by_product_move.product_qty, 2)

    def test_quant_selection_mrp(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )

        package = self.env["stock.package"].create({"name": "package001"})
        self.env["stock.quant"]._update_available_quantity(
            self.component01, self.stock_location, 10
        )
        self.env["stock.quant"]._update_available_quantity(
            self.component01, self.stock_location, 20, package_id=package
        )

        lot1, lot2 = self.env["product.trace"].create(
            [
                {
                    "name": f"lot{i}",
                    "product_id": self.component_lot.id,
                }
                for i in range(1, 3)
            ]
        )
        self.env["stock.quant"]._update_available_quantity(
            self.component_lot, self.stock_location, 10, trace_id=lot1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.component_lot, self.shelf1, 10, trace_id=lot2
        )

        mo = self.env["mrp.production"].create(
            {
                "product_id": self.final_product.id,
                "product_qty": 1,
                "move_raw_ids": [
                    Command.create(
                        {"product_id": self.component01.id, "product_uom_qty": 2}
                    )
                ],
            }
        )
        mo.action_confirm()

        url = f"/odoo/{mo.id}/action-stock_barcode_mrp.stock_barcode_mo_client_action"
        self.start_tour(url, "test_quant_selection_mrp", login="admin")

        self.assertRecordValues(
            mo.move_raw_ids.move_line_ids,
            [
                {
                    "product_id": self.component01.id,
                    "qty_done": 2,
                    "location_id": self.stock_location.id,
                    "trace_id": False,
                    "package_id": package.id,
                    "state": "done",
                },
                {
                    "product_id": self.component_lot.id,
                    "qty_done": 2,
                    "location_id": self.shelf1.id,
                    "trace_id": lot2.id,
                    "package_id": False,
                    "state": "done",
                },
            ],
        )

    def test_gs1_qty_final_product(self):
        barcodes_gs1_nomenclature = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        self.env.company.write({"nomenclature_id": barcodes_gs1_nomenclature.id})
        gs1_final_product = self.env["product.product"].create(
            {
                "name": "PRO_FINAL_GTIN_8",
                "is_storable": True,
                "barcode": "82655853",
                "uom_id": self.uom_unit.id,
            }
        )
        self.env["stock.quant"].create(
            {
                "quantity": 8,
                "product_id": self.component01.id,
                "location_id": self.stock_location.id,
            }
        )
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": gs1_final_product.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    Command.create(
                        {"product_id": self.component01.id, "product_qty": 2.0}
                    ),
                ],
            }
        )
        mo = self.env["mrp.production"].create(
            {
                "product_id": gs1_final_product.id,
                "product_qty": 4,
                "bom_id": bom.id,
            }
        )
        mo.action_confirm()
        action = self.env.ref("stock_barcode_mrp.stock_barcode_mo_client_action")
        url = "/web#action=%s&active_id=%s" % (action.id, mo.id)
        self.start_tour(url, "test_gs1_qty_final_product", login="admin")
        self.assertEqual(mo.state, "done")
