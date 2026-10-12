from unittest.mock import patch

import odoo
from odoo import Command, http
from odoo.tests import Form, tagged

from odoo.addons.stock_barcode.controllers.stock_barcode import StockBarcodeController
from odoo.addons.stock_barcode.tests.test_barcode_client_action import (
    TestBarcodeClientAction,
)


@tagged("post_install", "-at_install")
class TestPickingBarcodeClientAction(TestBarcodeClientAction):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("base.user_admin").write(
            {
                "email": "mitchell.admin@example.com",
            }
        )

    def test_internal_picking_from_scratch(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ]
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 2.0
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf1, 2.0
        )
        self.picking_type_internal.restrict_scan_dest_location = "mandatory"
        self.picking_type_internal.restrict_scan_source_location = "mandatory"
        internal_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_internal.id,
            }
        )
        url = self._get_client_action_url(internal_picking.id)

        picking_write_orig = odoo.addons.stock.models.stock_picking.StockPicking.write
        picking_button_validate_orig = (
            odoo.addons.stock.models.stock_picking.StockPicking.button_validate
        )
        product1 = self.product1
        stock_location = self.stock_location
        shelf1 = self.shelf1
        shelf3 = self.shelf3
        assertEqual = self.assertEqual
        self1 = self
        self1.stop_count_write = False

        def picking_write_mock(self, vals):
            if self1.stop_count_write:
                return picking_write_orig(self, vals)
            self1.call_count += 1
            if self1.call_count == 1:
                cmd = vals["move_line_ids"][0]
                write_vals = cmd[2]
                assertEqual(cmd[0], 0)
                assertEqual(cmd[1], 0)
                assertEqual(write_vals["product_id"], product1.id)
                assertEqual(write_vals["picking_id"], internal_picking.id)
                assertEqual(write_vals["location_id"], shelf1.id)
                assertEqual(write_vals["location_dest_id"], stock_location.id)
                assertEqual(write_vals["quantity"], 1)
            elif self1.call_count == 2:
                cmd = vals["move_line_ids"][0]
                write_vals = cmd[2]
                assertEqual(cmd[0], 1)
                assertEqual(write_vals["location_dest_id"], shelf3.id)
            return picking_write_orig(self, vals)

        def picking_button_validate_mock(self, **validate_kwargs):
            self1.stop_count_write = True
            return picking_button_validate_orig(self, **validate_kwargs)

        with (
            patch(
                "odoo.addons.stock.models.stock_picking.StockPicking.write",
                new=picking_write_mock,
            ),
            patch(
                "odoo.addons.stock.models.stock_picking.StockPicking.button_validate",
                new=picking_button_validate_mock,
            ),
        ):
            self.start_tour(
                url, "test_internal_picking_from_scratch", login="admin", timeout=180
            )

        self.assertEqual(self.call_count, 2)
        self.assertRecordValues(
            internal_picking.move_line_ids,
            [
                {
                    "product_id": self.product1.id,
                    "quantity": 2,
                    "location_id": self.shelf1.id,
                    "location_dest_id": self.shelf2.id,
                    "picked": True,
                    "result_package_id": False,
                },
                {
                    "product_id": self.product2.id,
                    "quantity": 1,
                    "location_id": self.shelf1.id,
                    "location_dest_id": self.shelf3.id,
                    "picked": True,
                    "result_package_id": False,
                },
                {
                    "product_id": self.product2.id,
                    "quantity": 1,
                    "location_id": self.shelf1.id,
                    "location_dest_id": self.shelf2.id,
                    "picked": True,
                    "result_package_id": False,
                },
                {
                    "product_id": self.product1.id,
                    "quantity": 1,
                    "location_id": self.shelf1.id,
                    "location_dest_id": self.shelf3.id,
                    "picked": True,
                    "result_package_id": False,
                },
            ],
        )

    def test_picking_scan_package_confirmation(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )
        package1 = self.env["stock.package"].create({"name": "package001"})

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 1, package_id=package1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 1, package_id=package1
        )

        delivery_with_move = self.env["stock.picking"].create(
            {
                "name": "Delivery with Stock Move",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                            "product_id": self.product1.id,
                            "product_uom_id": self.uom_unit.id,
                            "product_uom_qty": 2,
                        },
                    )
                ],
            }
        )
        delivery_with_move.action_confirm()
        delivery_with_move.action_assign()

        url = f"/odoo/{delivery_with_move.id}/action-stock_barcode.stock_barcode_picking_client_action"
        self.start_tour(
            url, "test_picking_scan_package_confirmation", login="admin", timeout=180
        )

    def test_internal_picking_from_scratch_with_package(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )
        self.picking_type_internal.active = True
        self.env["stock.package.type"].create(
            [
                {"name": "Palet", "sequence_code": "PAL-", "barcode": "PT_PALET"},
            ]
        )
        package2, package3, package4 = self.env["stock.package"].create(
            [{"name": f"P0000{i}"} for i in range(2, 5)]
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 1, package_id=package2
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 2, package_id=package2
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 1, package_id=package3
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 1, package_id=package4
        )
        self.assertEqual(package2.location_id.id, self.stock_location.id)

        self.start_tour(
            "/odoo/barcode",
            "test_internal_picking_from_scratch_with_package",
            login="admin",
        )

        self.assertEqual(len(self.package.quant_ids), 2)
        self.assertEqual(self.package.location_id.id, self.shelf2.id)
        self.assertRecordValues(
            self.package.quant_ids,
            [
                {
                    "product_id": self.product1.id,
                    "quantity": 1,
                    "location_id": self.shelf2.id,
                },
                {
                    "product_id": self.product2.id,
                    "quantity": 1,
                    "location_id": self.shelf2.id,
                },
            ],
        )

        self.assertEqual(package2.location_id.id, self.shelf2.id)
        self.assertRecordValues(
            package2.quant_ids,
            [
                {
                    "product_id": self.product1.id,
                    "quantity": 1,
                    "location_id": self.shelf2.id,
                },
                {
                    "product_id": self.product2.id,
                    "quantity": 2,
                    "location_id": self.shelf2.id,
                },
            ],
        )

        self.assertEqual(package3.parent_package_id.id, package4.parent_package_id.id)
        self.assertTrue(
            package3.location_id.id == package4.location_id.id == self.shelf1.id
        )
        palet = package3.parent_package_id
        self.assertRecordValues(
            palet.contained_quant_ids.sorted(lambda q: q.product_id.id),
            [
                {
                    "product_id": self.product1.id,
                    "quantity": 1,
                    "location_id": self.shelf1.id,
                    "package_id": package3.id,
                },
                {
                    "product_id": self.product2.id,
                    "quantity": 1,
                    "location_id": self.shelf1.id,
                    "package_id": package4.id,
                },
            ],
        )

    def test_internal_picking_reserved_1(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        self.picking_type_internal.restrict_scan_dest_location = "mandatory"
        self.picking_type_internal.restrict_scan_source_location = "mandatory"
        internal_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_internal.id,
            }
        )
        url = self._get_client_action_url(internal_picking.id)

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf1, 1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf3, 1
        )
        move1 = self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 1,
                "picking_id": internal_picking.id,
            }
        )
        move2 = self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "product_id": self.product2.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 2,
                "picking_id": internal_picking.id,
            }
        )
        internal_picking.action_confirm()
        internal_picking.action_assign()
        move1.move_line_ids.location_dest_id = self.shelf2.id
        for ml in move2.move_line_ids:
            if ml.location_id.id == self.shelf1.id:
                ml.location_dest_id = self.shelf2.id
            else:
                ml.location_dest_id = self.shelf4.id

        self.start_tour(
            url, "test_internal_picking_reserved_1", login="admin", timeout=180
        )

    def test_internal_picking_reserved_move_packages_into_new_palet(self):
        self.env.user.group_ids = [
            Command.link(self.env.ref("stock.group_tracking_lot").id),
            Command.link(self.env.ref("stock.group_stock_multi_locations").id),
        ]
        self.picking_type_internal.active = True
        self.picking_type_internal.show_entire_packs = True
        box_type, palet_type = self.env["stock.package.type"].create(
            [
                {"name": "Box", "sequence_code": "BOX-"},
                {"name": "Palet", "sequence_code": "PAL-", "barcode": "PT_PALET"},
            ]
        )
        packages = self.env["stock.package"].create(
            [
                {
                    "name": f"BOX-0{i}",
                    "package_type_id": box_type.id,
                }
                for i in range(1, 7)
            ]
        )
        for i, package in enumerate(packages):
            product = self.product1 if (i % 2 == 0) else self.product2
            self.env["stock.quant"]._update_available_quantity(
                product, self.stock_location, 5, package_id=package
            )

        palets = self.env["stock.package"].create(
            [
                {
                    "name": f"PAL-0{i}",
                    "package_type_id": palet_type.id,
                }
                for i in range(1, 4)
            ]
        )
        packages[:2].parent_package_id = palets[0]
        packages[2:4].parent_package_id = palets[1]

        internal_pickings = self.env["stock.picking"].create(
            [
                {
                    "name": f"TEST/INT/000{i}",
                    "location_id": self.picking_type_internal.default_location_src_id.id,
                    "location_dest_id": self.picking_type_internal.default_location_dest_id.id,
                    "picking_type_id": self.picking_type_internal.id,
                }
                for i in (1, 2)
            ]
        )
        internal_pickings[0].action_add_entire_packs(palets.ids)
        internal_pickings[1].action_add_entire_packs(packages[4:].ids)
        internal_pickings.action_confirm()

        self.start_tour(
            "/odoo/barcode",
            "test_internal_picking_reserved_move_packages_into_new_palet",
            login="admin",
        )

    def test_receipt_from_scratch_with_lots_1(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_production_lot").id),
                ],
            }
        )
        stock_2 = self.env["stock.location"].create(
            {
                "name": "Stock 2",
                "location_id": self.stock_location.location_id.id,
                "barcode": "WHSTOCK-2",
            }
        )
        receipt_picking = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        url = self._get_client_action_url(receipt_picking.id)
        self.start_tour(
            url, "test_receipt_from_scratch_with_lots_1", login="admin", timeout=180
        )
        self.assertRecordValues(
            receipt_picking.move_line_ids,
            [
                {"lot_name": "lot1", "location_dest_id": self.stock_location.id},
                {"lot_name": "lot2", "location_dest_id": self.shelf1.id},
                {"lot_name": "lot3", "location_dest_id": stock_2.id},
            ],
        )

    def test_receipt_from_scratch_with_lots_2(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_production_lot").id),
                ],
            }
        )
        self.picking_type_in.write(
            {
                "use_existing_lots": True,
                "use_create_lots": True,
            }
        )

        receipt_picking = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        url = self._get_client_action_url(receipt_picking.id)
        self.start_tour(
            url, "test_receipt_from_scratch_with_lots_2", login="admin", timeout=180
        )
        self.assertEqual(
            receipt_picking.move_line_ids.mapped("lot_name"), ["lot1", "lot2"]
        )
        self.assertEqual(receipt_picking.move_line_ids.mapped("qty_done"), [2, 2])

    def test_receipt_from_scratch_with_lots_3(self):
        receipt_picking = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        url = self._get_client_action_url(receipt_picking.id)
        self.start_tour(
            url, "test_receipt_from_scratch_with_lots_3", login="admin", timeout=180
        )
        move_lines = receipt_picking.move_line_ids
        self.assertEqual(move_lines[0].product_id.id, self.product1.id)
        self.assertEqual(move_lines[0].qty_done, 2.0)
        self.assertEqual(move_lines[1].product_id.id, self.productlot1.id)
        self.assertEqual(move_lines[1].qty_done, 2.0)
        self.assertEqual(move_lines[1].lot_name, "lot1")

    def test_receipt_from_scratch_with_lots_4(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.picking_type_in.use_create_lots = False
        self.picking_type_in.use_existing_lots = False

        receipt_picking = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        url = self._get_client_action_url(receipt_picking.id)
        self.start_tour(
            url, "test_receipt_from_scratch_with_lots_4", login="admin", timeout=180
        )
        move_lines = receipt_picking.move_line_ids
        self.assertEqual(move_lines[0].product_id.id, self.productserial1.id)
        self.assertEqual(move_lines[0].qty_done, 3.0)

    def test_receipt_with_sn_1(self):
        self.picking_type_in.use_create_lots = True
        self.picking_type_in.use_existing_lots = True
        snObj = self.env["product.trace"]
        snObj.create({"name": "sn1", "product_id": self.productserial1.id})

        receipt_picking = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
                "state": "draft",
            }
        )

        self.env["stock.move"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "product_id": self.productserial1.id,
                "product_uom_id": self.productserial1.uom_id.id,
                "product_uom_qty": 1,
                "picking_id": receipt_picking.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )

        url = self._get_client_action_url(receipt_picking.id)
        self.start_tour(url, "test_receipt_with_sn_1", login="admin", timeout=180)
        move_lines = receipt_picking.move_line_ids
        self.assertEqual(move_lines[0].product_id.id, self.productserial1.id)
        self.assertEqual(move_lines[0].trace_id.name, "sn1")
        self.assertEqual(move_lines[0].quantity, 1.0)

    def test_receipt_reserved_1(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        receipt_picking = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        picking_write_orig = odoo.addons.stock.models.stock_picking.StockPicking.write
        url = self._get_client_action_url(receipt_picking.id)

        self.env["stock.location"].create(
            {
                "name": "Stock 2",
                "location_id": self.stock_location.location_id.id,
                "barcode": "WHSTOCK-2",
            }
        )

        move1 = self.env["stock.move"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 4,
                "picking_id": receipt_picking.id,
                "description_picking": "First Item\nMove carefully\nABC [123]",
            }
        )
        move2 = self.env["stock.move"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "product_id": self.product2.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 4,
                "picking_id": receipt_picking.id,
                "description_picking": "Second Item\nMove carefully\nDEF [456]",
            }
        )
        receipt_picking.action_confirm()
        receipt_picking.action_assign()

        assertEqual = self.assertEqual
        ml1 = move1.move_line_ids
        ml2 = move2.move_line_ids
        shelf1 = self.shelf1
        self1 = self

        def picking_write_mock(self, vals):
            self1.call_count += 1
            if self1.call_count == 1:
                assertEqual(len(vals["move_line_ids"]), 2)
                assertEqual(vals["move_line_ids"][0][:2], [1, ml2.id])
                assertEqual(vals["move_line_ids"][1][:2], [1, ml1.id])
            return picking_write_orig(self, vals)

        with patch(
            "odoo.addons.stock.models.stock_picking.StockPicking.write",
            new=picking_write_mock,
        ):
            self.start_tour(url, "test_receipt_reserved_1", login="admin", timeout=180)
            self.assertEqual(self.call_count, 1)
            self.assertEqual(
                receipt_picking.move_line_ids[0].location_dest_id.id, shelf1.id
            )
            self.assertEqual(
                receipt_picking.move_line_ids[1].location_dest_id.id, shelf1.id
            )

    def test_receipt_reserved_2_partial_put_in_pack(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )
        receipt_form = Form(self.env["stock.picking"])
        receipt_form.picking_type_id = self.picking_type_in
        with receipt_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 3
        with receipt_form.move_ids.new() as move:
            move.product_id = self.product2
            move.product_uom_qty = 3
        receipt_picking = receipt_form.save()
        receipt_picking.action_confirm()
        receipt_picking.action_assign()
        receipt_picking.name = "receipt_test"
        self._reset_package_sequence(1000)

        self.start_tour(
            "/odoo/barcode",
            "test_receipt_reserved_2_partial_put_in_pack",
            login="admin",
            timeout=180,
        )

        package1 = self.env["stock.package"].search([("name", "=", "PACK0001000")])
        package2 = self.env["stock.package"].search([("name", "=", "PACK0001001")])
        self.assertRecordValues(
            receipt_picking.move_ids,
            [
                {
                    "product_id": self.product1.id,
                    "product_uom_qty": 3,
                    "quantity": 3,
                    "picked": True,
                },
                {
                    "product_id": self.product2.id,
                    "product_uom_qty": 1,
                    "quantity": 1,
                    "picked": True,
                },
            ],
        )
        self.assertRecordValues(
            receipt_picking.move_line_ids.sorted(),
            [
                {
                    "product_id": self.product2.id,
                    "quantity": 1,
                    "picked": True,
                    "result_package_id": package2.id,
                },
                {
                    "product_id": self.product1.id,
                    "quantity": 1,
                    "picked": True,
                    "result_package_id": package2.id,
                },
                {
                    "product_id": self.product1.id,
                    "quantity": 2,
                    "picked": True,
                    "result_package_id": package1.id,
                },
            ],
        )
        receipt_backorder = receipt_picking.backorder_ids
        self.assertRecordValues(
            receipt_backorder.move_ids,
            [
                {
                    "product_id": self.product2.id,
                    "product_uom_qty": 2,
                    "quantity": 2,
                    "picked": False,
                },
            ],
        )

    def test_receipt_reserved_put_in_pack_after_interruption(self):
        group_package = self.env.ref("stock.group_tracking_lot")
        self.env.user.write({"group_ids": [Command.link(group_package.id)]})
        self.picking_type_in.restrict_scan_product = True
        self._reset_package_sequence()
        self.env["stock.package.type"].create(
            [
                {"name": "Box", "sequence_code": "BOX-", "barcode": "PT_BOX"},
                {"name": "Palet", "sequence_code": "PAL-", "barcode": "PT_PALET"},
            ]
        )
        product3, product4 = self.env["product.product"].create(
            [
                {
                    "name": f"product{i}",
                    "is_storable": True,
                    "barcode": f"product{i}",
                }
                for i in [3, 4]
            ]
        )
        receipts = self.env["stock.picking"].create(
            [
                {
                    "name": f"TEST/IN/000{i}",
                    "location_id": self.picking_type_in.default_location_src_id.id,
                    "location_dest_id": self.picking_type_in.default_location_dest_id.id,
                    "picking_type_id": self.picking_type_in.id,
                    "move_ids": [
                        Command.create(
                            {
                                "location_id": self.picking_type_in.default_location_src_id.id,
                                "location_dest_id": self.picking_type_in.default_location_dest_id.id,
                                "product_id": product.id,
                                "quantity": 1,
                            }
                        )
                        for product in products
                    ],
                }
                for (i, products) in [
                    (1, [self.product1, self.product2, product3, product4]),
                    (2, [self.product1, self.product2]),
                ]
            ]
        )
        receipts.action_confirm()
        self.start_tour(
            "/odoo/barcode",
            "test_receipt_reserved_put_in_pack_after_interruption",
            login="admin",
        )

    def test_receipt_product_not_consecutively(self):
        receipt_picking = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
                "state": "draft",
            }
        )

        url = self._get_client_action_url(receipt_picking.id)
        self.start_tour(
            url, "test_receipt_product_not_consecutively", login="admin", timeout=180
        )

        self.assertEqual(len(receipt_picking.move_line_ids), 2)
        self.assertEqual(
            receipt_picking.move_line_ids.product_id.ids,
            [self.product1.id, self.product2.id],
        )
        self.assertEqual(receipt_picking.move_line_ids.mapped("quantity"), [2, 1])

    def test_delivery_source_location(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        sibling_loc = self.env["stock.location"].create(
            {
                "name": "Second Stock",
                "location_id": self.stock_location.location_id.id,
                "barcode": "WH-SECOND-STOCK",
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4
        )
        delivery_from_stock = self.env["stock.picking"].create(
            {
                "name": "delivery_from_stock",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": delivery_from_stock.location_id.id,
                "location_dest_id": delivery_from_stock.location_dest_id.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 4,
                "picking_id": delivery_from_stock.id,
            }
        )
        delivery_from_stock.action_confirm()
        delivery_from_stock.action_assign()
        self.env["stock.quant"]._update_available_quantity(
            self.product1, sibling_loc, 4
        )
        delivery_from_stock_2 = self.env["stock.picking"].create(
            {
                "name": "delivery_from_second_stock",
                "location_id": sibling_loc.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": delivery_from_stock_2.location_id.id,
                "location_dest_id": delivery_from_stock_2.location_dest_id.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 4,
                "picking_id": delivery_from_stock_2.id,
            }
        )
        delivery_from_stock_2.action_confirm()
        delivery_from_stock_2.action_assign()

        url = "/odoo/action-stock_barcode.stock_barcode_action_main_menu"
        self.start_tour(
            url, "test_delivery_source_location", login="admin", timeout=180
        )
        self.assertEqual(delivery_from_stock.state, "done")
        self.assertEqual(delivery_from_stock_2.state, "done")

    def test_delivery_lot_with_multi_companies(self):
        company_a = self.env["res.company"].create(
            {"name": 'Company "Ah !" (le meme TMTC)'}
        )
        company_b = self.env["res.company"].create({"name": "Company Bae 😏😘"})
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id)
                ],
                "company_ids": [Command.link(company_a.id), Command.link(company_b.id)],
                "company_id": company_b.id,
            }
        )
        warehouse_b = self.env["stock.warehouse"].search(
            [("company_id", "=", company_b.id)]
        )
        location_a = (
            self.env["stock.warehouse"]
            .search([("company_id", "=", company_a.id)])
            .lot_stock_id
        )
        location_b = warehouse_b.lot_stock_id
        picking_type_out_b = warehouse_b.out_type_id
        location_id_by_company = {
            company_a: location_a.id,
            company_b: location_b.id,
        }
        sn_a_1 = self.env["product.trace"].create(
            {
                "name": "tsn-001",
                "product_id": self.productserial1.id,
                "company_id": company_a.id,
            }
        )
        sn_a_2 = self.env["product.trace"].create(
            {
                "name": "tsn-002",
                "product_id": self.productserial1.id,
                "company_id": company_a.id,
            }
        )
        sn_b_1 = self.env["product.trace"].create(
            {
                "name": "tsn-001",
                "product_id": self.productserial1.id,
                "company_id": company_b.id,
            }
        )
        sn_b_2 = self.env["product.trace"].create(
            {
                "name": "tsn-003",
                "product_id": self.productserial1.id,
                "company_id": company_b.id,
            }
        )
        for sn in [sn_a_1, sn_a_2, sn_b_1, sn_b_2]:
            self.env["stock.quant"].with_context(inventory_mode=True).create(
                {
                    "product_id": self.productserial1.id,
                    "inventory_quantity": 1,
                    "trace_id": sn.id,
                    "location_id": location_id_by_company[sn.company_id],
                }
            )
        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = picking_type_out_b
        delivery = picking_form.save()
        url = self._get_client_action_url(delivery.id)
        self.start_tour(
            url, "test_delivery_lot_with_multi_companies", login="admin", timeout=180
        )
        self.assertRecordValues(
            delivery.move_line_ids.trace_id,
            [
                {"name": "tsn-001", "company_id": company_b.id},
                {"name": "tsn-003", "company_id": company_b.id},
            ],
        )

    def test_delivery_lot_with_package(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_tracking_owner").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        self.picking_type_out.show_reserved_sns = True
        snObj = self.env["product.trace"]
        sn1 = snObj.create({"name": "sn1", "product_id": self.productserial1.id})
        sn2 = snObj.create({"name": "sn2", "product_id": self.productserial1.id})
        sn3 = snObj.create({"name": "sn3", "product_id": self.productserial1.id})
        sn4 = snObj.create({"name": "sn4", "product_id": self.productserial1.id})
        package1 = self.env["stock.package"].create({"name": "pack_sn_1"})
        package2 = self.env["stock.package"].create({"name": "pack_sn_2"})
        partner = self.env["res.partner"].create({"name": "Particulier"})
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": self.productserial1.id,
                "inventory_quantity": 1,
                "trace_id": sn1.id,
                "location_id": self.stock_location.id,
                "package_id": package1.id,
            }
        ).action_apply_inventory()
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": self.productserial1.id,
                "inventory_quantity": 1,
                "trace_id": sn2.id,
                "location_id": self.stock_location.id,
                "package_id": package1.id,
            }
        ).action_apply_inventory()

        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.productserial1.id,
                "product_uom_qty": 2,
                "product_uom_id": self.productserial1.uom_id.id,
                "picking_id": delivery_picking.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
            }
        )
        delivery_picking.action_confirm()
        delivery_picking.action_assign()
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": self.productserial1.id,
                "inventory_quantity": 1,
                "trace_id": sn3.id,
                "location_id": self.stock_location.id,
                "package_id": package2.id,
            }
        ).action_apply_inventory()
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": self.productserial1.id,
                "inventory_quantity": 1,
                "trace_id": sn4.id,
                "location_id": self.stock_location.id,
                "package_id": package2.id,
                "owner_id": partner.id,
            }
        ).action_apply_inventory()

        url = self._get_client_action_url(delivery_picking.id)
        self.start_tour(
            url, "test_delivery_lot_with_package", login="admin", timeout=180
        )

        self.assertEqual(delivery_picking.state, "done")
        self.assertEqual(len(delivery_picking.move_line_ids), 2)
        move_line_1 = delivery_picking.move_line_ids[0]
        move_line_2 = delivery_picking.move_line_ids[1]
        self.assertEqual(move_line_1.trace_id, sn3)
        self.assertEqual(move_line_1.package_id, package2)
        self.assertEqual(move_line_1.owner_id.id, False)
        self.assertEqual(move_line_2.trace_id, sn4)
        self.assertEqual(move_line_2.package_id, package2)
        self.assertEqual(move_line_2.owner_id, partner)

    def test_delivery_lot_with_package_delivery_step(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )
        sn = self.env["product.trace"].create(
            {
                "name": "sn",
                "product_id": self.productlot1.id,
                "company_id": self.env.company.id,
            }
        )
        package1 = self.env["stock.package"].create({"name": "pack_sn"})
        package2 = self.env["stock.package"].create({"name": "pack_sn_2"})
        self.env["stock.quant"].create(
            [
                {
                    "product_id": self.productlot1.id,
                    "inventory_quantity": 1,
                    "trace_id": sn.id,
                    "location_id": self.shelf1.id,
                    "package_id": package1.id,
                },
                {
                    "product_id": self.productlot1.id,
                    "inventory_quantity": 1,
                    "trace_id": sn.id,
                    "location_id": self.shelf2.id,
                },
                {
                    "product_id": self.productlot1.id,
                    "inventory_quantity": 1,
                    "trace_id": sn.id,
                    "location_id": self.shelf2.id,
                    "package_id": package2.id,
                },
            ]
        ).action_apply_inventory()

        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.shelf2.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "product_id": self.productlot1.id,
                "product_uom_qty": 1,
                "product_uom_id": self.productlot1.uom_id.id,
                "picking_id": delivery_picking.id,
                "location_id": self.shelf2.id,
                "location_dest_id": self.customer_location.id,
            }
        )
        delivery_picking.action_confirm()
        delivery_picking.action_assign()

        url = self._get_client_action_url(delivery_picking.id)
        self.start_tour(
            url,
            "test_delivery_lot_with_package_delivery_step",
            login="admin",
            timeout=180,
        )
        self.assertEqual(delivery_picking.state, "done")
        self.assertRecordValues(
            move.move_line_ids,
            [
                {
                    "trace_id": sn.id,
                    "product_id": self.productlot1.id,
                    "quantity": 1,
                    "package_id": package2.id,
                    "result_package_id": False,
                },
            ],
        )

    def test_delivery_pack_from_different_location(self):
        group_multi_loc = self.env.ref("stock.group_stock_multi_locations")
        group_pack = self.env.ref("stock.group_tracking_lot")
        self.env.user.write({"group_ids": [Command.link(group_multi_loc.id)]})
        self.env.user.write({"group_ids": [Command.link(group_pack.id)]})
        self.picking_type_out.restrict_scan_source_location = "mandatory"
        self.env["stock.package"].create(
            {
                "name": "pack-test",
            }
        )
        self.start_tour(
            "/odoo/barcode", "test_delivery_pack_from_different_location", login="admin"
        )

    def test_delivery_reserved_1(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "note": "A Test Note",
            }
        )
        picking_write_orig = odoo.addons.stock.models.stock_picking.StockPicking.write
        url = self._get_client_action_url(delivery_picking.id)

        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 4,
                "picking_id": delivery_picking.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.product2.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 4,
                "picking_id": delivery_picking.id,
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 4
        )

        delivery_picking.action_confirm()
        delivery_picking.action_assign()

        self1 = self

        def picking_write_mock(self, vals):
            self1.call_count += 1
            return picking_write_orig(self, vals)

        with patch(
            "odoo.addons.stock.models.stock_picking.StockPicking.write",
            new=picking_write_mock,
        ):
            self.start_tour(url, "test_delivery_reserved_1", login="admin", timeout=180)
            self.assertEqual(self.call_count, 1)

    def test_delivery_reserved_2(self):
        self.picking_type_out.restrict_scan_source_location = "no"
        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        picking_write_orig = odoo.addons.stock.models.stock_picking.StockPicking.write
        url = self._get_client_action_url(delivery_picking.id)

        partner_1 = self.env["res.partner"].create({"name": "Parter1"})
        partner_2 = self.env["res.partner"].create({"name": "Partner2"})
        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 2,
                "picking_id": delivery_picking.id,
                "restrict_partner_id": partner_1.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 2,
                "picking_id": delivery_picking.id,
                "restrict_partner_id": partner_2.id,
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 4
        )

        delivery_picking.action_confirm()
        delivery_picking.action_assign()
        self.assertEqual(len(delivery_picking.move_ids), 2)

        self1 = self

        def picking_write_mock(self, vals):
            self1.call_count += 1
            return picking_write_orig(self, vals)

        with patch(
            "odoo.addons.stock.models.stock_picking.StockPicking.write",
            new=picking_write_mock,
        ):
            self.start_tour(url, "test_delivery_reserved_2", login="admin", timeout=180)
            self.assertEqual(self.call_count, 0)

    def test_delivery_reserved_3(self):
        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        picking_write_orig = odoo.addons.stock.models.stock_picking.StockPicking.write
        url = self._get_client_action_url(delivery_picking.id)

        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 1,
                "picking_id": delivery_picking.id,
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 2
        )

        delivery_picking.action_confirm()
        delivery_picking.action_assign()

        self1 = self

        def picking_write_mock(self, vals):
            self1.call_count += 1
            return picking_write_orig(self, vals)

        with patch(
            "odoo.addons.stock.models.stock_picking.StockPicking.write",
            new=picking_write_mock,
        ):
            self.start_tour(url, "test_delivery_reserved_3", login="admin", timeout=180)
            self.assertEqual(self.call_count, 0)

    def test_delivery_reserved_4_backorder(self):
        product3 = self.env["product.product"].create(
            {
                "name": "product3",
                "is_storable": True,
                "barcode": "product3",
            }
        )
        delivery = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_out.id,
            }
        )
        common_vals = {
            "location_dest_id": self.stock_location.id,
            "location_id": self.stock_location.id,
            "picking_id": delivery.id,
            "product_uom_qty": 4,
        }
        self.env["stock.move"].create(dict(common_vals, product_id=self.product1.id))
        self.env["stock.move"].create(dict(common_vals, product_id=self.product2.id))
        self.env["stock.move"].create(dict(common_vals, product_id=product3.id))
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 2
        )
        delivery.action_confirm()
        delivery.action_assign()
        url = self._get_client_action_url(delivery.id)
        self.start_tour(
            url, "test_delivery_reserved_4_backorder", login="admin", timeout=180
        )

        self.assertEqual(len(delivery.backorder_ids), 1)
        backorder = delivery.backorder_ids
        self.assertEqual(len(backorder.move_ids), 2)
        self.assertRecordValues(
            backorder.move_ids,
            [
                {
                    "product_uom_qty": 4,
                    "quantity": 2,
                    "picked": False,
                    "product_id": self.product2.id,
                },
                {
                    "product_uom_qty": 4,
                    "quantity": 0,
                    "picked": False,
                    "product_id": product3.id,
                },
            ],
        )

    def test_delivery_reserved_5_dont_show_reserved_sn(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.picking_type_out.show_reserved_sns = False

        serial_numbers = self.env["product.trace"].create(
            [
                {
                    "name": f"sn{n}",
                    "product_id": self.productserial1.id,
                    "company_id": self.env.company.id,
                }
                for n in range(1, 6)
            ]
        )
        for sn in serial_numbers:
            self.env["stock.quant"]._update_available_quantity(
                self.productserial1, self.stock_location, 1, trace_id=sn
            )

        delivery_picking = self.env["stock.picking"].create(
            {
                "name": "test_delivery_reserved_5",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": delivery_picking.location_id.id,
                "location_dest_id": delivery_picking.location_dest_id.id,
                "picking_id": delivery_picking.id,
                "product_id": self.productserial1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 4,
            }
        )
        delivery_picking.action_confirm()
        reserved_move_lines = delivery_picking.move_line_ids
        self.assertEqual(len(delivery_picking.move_line_ids), 4)
        self.assertEqual(reserved_move_lines.mapped("quantity"), [1, 1, 1, 1])
        self.assertEqual(
            reserved_move_lines.trace_id.mapped("name"), ["sn1", "sn2", "sn3", "sn4"]
        )

        url = self._get_client_action_url(delivery_picking.id)
        self.start_tour(
            url,
            "test_delivery_reserved_5_dont_show_reserved_sn",
            login="admin",
            timeout=180,
        )
        self.assertEqual(
            delivery_picking.move_line_ids.trace_id.mapped("name"),
            ["sn1", "sn2", "sn3", "sn5"],
        )

    def test_delivery_reserved_6_dont_show_reserved_lots(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.picking_type_out.show_reserved_sns = False

        lots = self.env["product.trace"].create(
            [
                {
                    "name": f"lot-00{n}",
                    "product_id": self.productlot1.id,
                    "company_id": self.env.company.id,
                }
                for n in range(1, 6)
            ]
        )
        for lot in lots:
            self.env["stock.quant"]._update_available_quantity(
                self.productlot1, self.stock_location, 4, trace_id=lot
            )

        delivery_picking = self.env["stock.picking"].create(
            {
                "name": "test_delivery_reserved_6",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": delivery_picking.location_id.id,
                "location_dest_id": delivery_picking.location_dest_id.id,
                "picking_id": delivery_picking.id,
                "product_id": self.productlot1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 12,
            }
        )
        delivery_picking.action_confirm()
        reserved_move_lines = delivery_picking.move_line_ids
        self.assertEqual(len(delivery_picking.move_line_ids), 3)
        self.assertEqual(reserved_move_lines.mapped("quantity"), [4, 4, 4])
        self.assertEqual(
            reserved_move_lines.trace_id.mapped("name"),
            ["lot-001", "lot-002", "lot-003"],
        )

        url = self._get_client_action_url(delivery_picking.id)
        self.start_tour(
            url,
            "test_delivery_reserved_6_dont_show_reserved_lots",
            login="admin",
            timeout=180,
        )

    def test_delivery_from_scratch_1(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )

        lotObj = self.env["product.trace"]
        lotObj.create({"name": "lot1", "product_id": self.productlot1.id})
        lotObj.create({"name": "lot2", "product_id": self.productlot1.id})

        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        url = self._get_client_action_url(delivery_picking.id)

        self.start_tour(
            url, "test_delivery_from_scratch_with_lots_1", login="admin", timeout=180
        )

        lines = delivery_picking.move_line_ids
        self.assertEqual(lines[0].trace_id.name, "lot1")
        self.assertEqual(lines[1].trace_id.name, "lot2")
        self.assertEqual(lines[0].qty_done, 2)
        self.assertEqual(lines[1].qty_done, 2)

    def test_delivery_from_scratch_with_incompatible_lot(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.picking_type_out.use_create_lots = False
        self.picking_type_out.use_existing_lots = True

        lot = self.env["product.trace"].create(
            {
                "name": "0000000001",
                "product_id": self.productlot1.id,
            }
        )

        for product in [self.product1, self.productserial1]:
            product.barcode = lot.name

            delivery_picking = self.env["stock.picking"].create(
                {
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.customer_location.id,
                    "picking_type_id": self.picking_type_out.id,
                    "state": "draft",
                }
            )
            url = self._get_client_action_url(delivery_picking.id)
            self.start_tour(
                url,
                "test_delivery_from_scratch_with_incompatible_lot",
                login="admin",
                timeout=180,
            )

            self.assertRecordValues(
                delivery_picking.move_line_ids,
                [
                    {"product_id": product.id, "lot_name": False, "trace_id": False},
                ],
            )

            product.barcode = False

    def test_delivery_from_scratch_with_common_lots_name(self):
        (self.product1 + self.product2).tracking = "lot"

        lot01, lot02, sn = self.env["product.trace"].create(
            [
                {
                    "name": lot_name,
                    "product_id": product.id,
                }
                for (lot_name, product) in [
                    ("LOT01", self.product1),
                    ("LOT01", self.product2),
                    ("SUPERSN", self.productserial1),
                ]
            ]
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 2, trace_id=lot01
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 3, trace_id=lot02
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productserial1, self.stock_location, 1, trace_id=sn
        )

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_out
        delivery = picking_form.save()

        url = self._get_client_action_url(delivery.id)
        self.start_tour(
            url,
            "test_delivery_from_scratch_with_common_lots_name",
            login="admin",
            timeout=180,
        )

        self.assertRecordValues(
            delivery.move_line_ids,
            [
                {"product_id": self.product1.id, "trace_id": lot01.id, "qty_done": 2},
                {"product_id": self.product2.id, "trace_id": lot02.id, "qty_done": 3},
                {
                    "product_id": self.productserial1.id,
                    "trace_id": sn.id,
                    "qty_done": 1,
                },
            ],
        )

    def test_delivery_reserved_lots_1(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.picking_type_out.show_reserved_sns = True

        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        url = self._get_client_action_url(delivery_picking.id)

        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.productlot1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 5,
                "picking_id": delivery_picking.id,
            }
        )

        lotObj = self.env["product.trace"]
        lot1 = lotObj.create({"name": "lot1", "product_id": self.productlot1.id})
        lot2 = lotObj.create({"name": "lot2", "product_id": self.productlot1.id})
        lot3 = lotObj.create({"name": "lot3", "product_id": self.productlot1.id})

        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 2, trace_id=lot1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 3, trace_id=lot2
        )

        delivery_picking.action_confirm()
        delivery_picking.action_assign()
        self.assertEqual(delivery_picking.move_ids.state, "assigned")
        self.assertEqual(len(delivery_picking.move_ids.move_line_ids), 2)

        self.start_tour(
            url, "test_delivery_reserved_lots_1", login="admin", timeout=180
        )

        self.assertRecordValues(
            delivery_picking.move_line_ids,
            [
                {"trace_id": lot1.id, "quantity": 2, "picked": True},
                {"trace_id": lot2.id, "quantity": 2, "picked": True},
                {"trace_id": lot3.id, "quantity": 1, "picked": True},
            ],
        )

    def test_delivery_different_products_with_same_lot_name(self):
        self.productlot2 = self.env["product.product"].create(
            {
                "name": "productlot2",
                "is_storable": True,
                "barcode": "productlot2",
                "tracking": "lot",
            }
        )

        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        url = self._get_client_action_url(delivery_picking.id)

        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.productlot1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 2,
                "picking_id": delivery_picking.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.productlot2.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 2,
                "picking_id": delivery_picking.id,
            }
        )

        lot1 = self.env["product.trace"].create(
            {"name": "lot1", "product_id": self.productlot1.id}
        )
        lot2 = self.env["product.trace"].create(
            {"name": "lot1", "product_id": self.productlot2.id}
        )

        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 2, trace_id=lot1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot2, self.stock_location, 2, trace_id=lot2
        )

        delivery_picking.action_confirm()
        delivery_picking.action_assign()

        self.assertEqual(len(delivery_picking.move_ids), 2)

        self.start_tour(
            url,
            "test_delivery_different_products_with_same_lot_name",
            login="admin",
            timeout=180,
        )

        self.env.invalidate_all()
        lines = delivery_picking.move_line_ids
        self.assertEqual(lines[0].trace_id.name, "lot1")
        self.assertEqual(lines[0].product_id.name, "productlot1")
        self.assertEqual(lines[0].qty_done, 2)
        self.assertEqual(lines[1].trace_id.name, "lot1")
        self.assertEqual(lines[1].product_id.name, "productlot2")
        self.assertEqual(lines[1].qty_done, 2)

    def test_scan_same_lot_different_products(self):
        products = self.env["product.product"].create(
            [
                {
                    "name": name,
                    "barcode": name,
                    "is_storable": True,
                    "tracking": "lot",
                }
                for name in ["aaa", "bbb"]
            ]
        )

        self.env["product.trace"].create(
            [
                {
                    "name": "123",
                    "product_id": product.id,
                    "company_id": self.env.company.id,
                }
                for product in products
            ]
        )

        self.picking_type_internal.restrict_scan_product = True
        internal_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.shelf1.id,
                "picking_type_id": self.picking_type_internal.id,
            }
        )
        url = self._get_client_action_url(internal_picking.id)

        self.start_tour(url, "test_scan_same_lot_different_products", login="admin")

    def test_delivery_reserved_with_sn_1(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )

        snObj = self.env["product.trace"]
        sn1 = snObj.create({"name": "sn1", "product_id": self.productserial1.id})
        sn2 = snObj.create({"name": "sn2", "product_id": self.productserial1.id})
        sn3 = snObj.create({"name": "sn3", "product_id": self.productserial1.id})
        sn4 = snObj.create({"name": "sn4", "product_id": self.productserial1.id})

        self.env["stock.quant"]._update_available_quantity(
            self.productserial1, self.stock_location, 1, trace_id=sn1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productserial1, self.stock_location, 1, trace_id=sn2
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productserial1, self.stock_location, 1, trace_id=sn3
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productserial1, self.stock_location, 1, trace_id=sn4
        )

        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )

        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.productserial1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 4,
                "picking_id": delivery_picking.id,
            }
        )
        delivery_picking.action_confirm()

        url = self._get_client_action_url(delivery_picking.id)
        self.start_tour(
            url, "test_delivery_reserved_with_sn_1", login="admin", timeout=180
        )

        lines = delivery_picking.move_line_ids
        self.assertEqual(lines.mapped("trace_id.name"), ["sn1", "sn2", "sn3", "sn4"])
        self.assertEqual(lines.mapped("qty_done"), [1, 1, 1, 1])

    def test_delivery_using_buttons(self):
        product3 = self.env["product.product"].create(
            {
                "name": "product3",
                "is_storable": True,
                "barcode": "product3",
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 2
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 3
        )
        self.env["stock.quant"]._update_available_quantity(
            product3, self.stock_location, 4
        )

        delivery_form = Form(self.env["stock.picking"])
        delivery_form.picking_type_id = self.picking_type_out
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 2
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product2
            move.product_uom_qty = 3
        with delivery_form.move_ids.new() as move:
            move.product_id = product3
            move.product_uom_qty = 4

        delivery_picking = delivery_form.save()
        delivery_picking.action_confirm()
        delivery_picking.action_assign()

        url = self._get_client_action_url(delivery_picking.id)
        self.start_tour(url, "test_delivery_using_buttons", login="admin", timeout=180)

        self.assertEqual(len(delivery_picking.move_line_ids), 4)
        self.assertEqual(
            delivery_picking.move_line_ids.mapped("qty_done"), [2, 3, 4, 2]
        )

    def test_remaining_decimal_accuracy(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.picking_type_out.show_reserved_sns = True
        lot01, lot02 = self.env["product.trace"].create(
            [
                {
                    "name": lot_name,
                    "product_id": self.productlot1.id,
                }
                for lot_name in ["LOT01", "LOT02"]
            ]
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.shelf1, 2, trace_id=lot01
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.shelf1, 2, trace_id=lot02
        )
        delivery_form = Form(self.env["stock.picking"])
        delivery_form.picking_type_id = self.picking_type_out
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 4

        with delivery_form.move_ids.new() as move:
            move.product_id = self.product2
            move.product_uom_qty = 0.12

        with delivery_form.move_ids.new() as move:
            move.product_id = self.productlot1
            move.product_uom_qty = 4

        delivery_picking = delivery_form.save()
        delivery_picking.action_confirm()
        delivery_picking.action_assign()

        url = self._get_client_action_url(delivery_picking.id)
        self.start_tour(
            url, "test_remaining_decimal_accuracy", login="admin", timeout=90
        )

    def test_receipt_reserved_lots_multiloc_1(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_production_lot").id),
                ],
            }
        )

        receipts_picking = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
                "user_id": False,
            }
        )

        url = self._get_client_action_url(receipts_picking.id)

        self.env["stock.move"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "product_id": self.productlot1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 4,
                "picking_id": receipts_picking.id,
            }
        )

        lotObj = self.env["product.trace"]
        lotObj.create({"name": "lot1", "product_id": self.productlot1.id})
        lotObj.create({"name": "lot2", "product_id": self.productlot1.id})

        receipts_picking.action_confirm()
        receipts_picking.action_assign()

        self.assertEqual(receipts_picking.user_id.id, False)
        self.start_tour(
            url, "test_receipt_reserved_lots_multiloc_1", login="admin", timeout=180
        )
        self.assertEqual(receipts_picking.user_id.id, self.env.user.id)
        self.env.invalidate_all()
        lines = receipts_picking.move_line_ids.sorted(
            lambda ml: (
                ml.location_id.complete_name,
                ml.location_dest_id.complete_name,
                ml.id,
            )
        )
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines.mapped("qty_done"), [2, 2])
        self.assertEqual(lines.mapped("location_id.name"), ["Vendors"])
        self.assertEqual(lines[0].location_dest_id.name, "Section 1")
        self.assertEqual(lines[0].lot_name, "lot2")
        self.assertEqual(lines[1].location_dest_id.name, "Section 2")
        self.assertEqual(lines[1].lot_name, "lot1")

    def test_pack_multiple_scan(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )

        sequence = self.env["ir.sequence"].search(
            [
                (
                    "code",
                    "=",
                    "stock.package",
                )
            ],
            limit=1,
        )
        sequence.write({"number_next_actual": 1000})

        self.start_tour(
            "/odoo/barcode", "test_pack_multiple_scan", login="admin", timeout=180
        )

        package = self.env["stock.package"].search([("name", "=", "PACK0001000")])
        self.assertEqual(package.location_id, self.customer_location)

    def test_pack_common_content_scan(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )

        pack1 = self.env["stock.package"].create(
            {
                "name": "PACK1",
            }
        )
        pack2 = self.env["stock.package"].create(
            {
                "name": "PACK2",
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            product_id=self.product1,
            location_id=self.stock_location,
            quantity=5,
            package_id=pack1,
        )
        self.env["stock.quant"]._update_available_quantity(
            product_id=self.product2,
            location_id=self.stock_location,
            quantity=1,
            package_id=pack1,
        )

        self.env["stock.quant"]._update_available_quantity(
            product_id=self.product1,
            location_id=self.stock_location,
            quantity=5,
            package_id=pack2,
        )
        self.env["stock.quant"]._update_available_quantity(
            product_id=self.product2,
            location_id=self.stock_location,
            quantity=1,
            package_id=pack2,
        )

        self.start_tour(
            "/odoo/barcode", "test_pack_common_content_scan", login="admin", timeout=180
        )
        delivery = self._last_picking(self.picking_type_out)
        self.assertEqual(delivery.state, "done")
        self.assertEqual(
            sorted(
                (ml.product_id.name, ml.package_id.name or "", ml.quantity)
                for ml in delivery.move_line_ids
            ),
            [
                ("product1", "", 1),
                ("product1", "PACK1", 5),
                ("product1", "PACK2", 5),
                ("product2", "PACK1", 1),
                ("product2", "PACK2", 1),
            ],
            "the same product in two packages stays on two lines",
        )

    def test_pack_multiple_location(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )
        self.picking_type_internal.active = True
        self.picking_type_internal.show_entire_packs = True
        self.picking_type_internal.restrict_scan_dest_location = "mandatory"
        self.picking_type_internal.restrict_scan_source_location = "mandatory"

        pack1 = self.env["stock.package"].create(
            {
                "name": "PACK0000666",
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            product_id=self.product1,
            location_id=self.shelf1,
            quantity=5,
            package_id=pack1,
        )
        self.env["stock.quant"]._update_available_quantity(
            product_id=self.product2,
            location_id=self.shelf1,
            quantity=5,
            package_id=pack1,
        )

        self.start_tour(
            "/odoo/barcode", "test_pack_multiple_location", login="admin", timeout=180
        )

        self.assertEqual(pack1.location_id, self.shelf2)

    def test_pack_multiple_location_02(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )
        pack1 = self.env["stock.package"].create(
            {
                "name": "PACK0002020",
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            product_id=self.product1,
            location_id=self.shelf1,
            quantity=5,
            package_id=pack1,
        )

        internal_picking = self.env["stock.picking"].create(
            {
                "location_id": self.shelf1.id,
                "location_dest_id": self.shelf2.id,
                "picking_type_id": self.picking_type_internal.id,
            }
        )
        url = self._get_client_action_url(internal_picking.id)

        self.env["stock.move"].create(
            {
                "location_id": self.shelf1.id,
                "location_dest_id": self.shelf2.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 5,
                "picking_id": internal_picking.id,
            }
        )
        internal_picking.action_confirm()
        internal_picking.action_assign()

        self.start_tour(
            url, "test_pack_multiple_location_02", login="admin", timeout=180
        )

        self.assertEqual(pack1.location_id, self.shelf2)

    def test_pack_multiple_location_03(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )

        pack1 = self.env["stock.package"].create(
            {
                "name": "PACK000666",
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            product_id=self.product1,
            location_id=self.shelf1,
            quantity=5,
            package_id=pack1,
        )

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_out
        picking_form.location_id = self.stock_location
        with picking_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 1
        delivery_picking = picking_form.save()
        delivery_picking.action_confirm()
        delivery_picking.action_assign()
        url = self._get_client_action_url(delivery_picking.id)

        self.start_tour(
            url, "test_pack_multiple_location_03", login="admin", timeout=180
        )
        self.assertFalse(delivery_picking.move_line_ids.package_id)

    def test_pack_source_location(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )
        self.picking_type_internal.active = True
        self.picking_type_internal.show_entire_packs = False
        action_id = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = "/web#action=" + str(action_id.id)
        pack1 = self.env["stock.package"].create(
            {
                "name": "PACK123666",
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            product_id=self.product1,
            location_id=self.shelf4,
            quantity=5,
            package_id=pack1,
        )

        self.assertEqual(
            self.env["stock.quant"]._get_available_quantity(
                self.product1, self.shelf4, package_id=pack1
            ),
            5,
        )
        self.start_tour(url, "test_pack_source_location", login="admin", timeout=180)
        self.assertEqual(
            self.env["stock.quant"]._get_available_quantity(
                self.product1, self.shelf4, package_id=pack1
            ),
            0,
        )
        self.assertEqual(
            self.env["stock.quant"]._get_available_quantity(
                self.product1, self.stock_location, package_id=pack1
            ),
            5,
        )

    def test_put_in_pack_from_multiple_pages(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )
        self.picking_type_internal.restrict_scan_dest_location = "no"
        self.picking_type_internal.restrict_scan_source_location = "mandatory"

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf1, 1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf2, 1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf2, 1
        )

        internal_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_internal.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 2,
                "picking_id": internal_picking.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "product_id": self.product2.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 2,
                "picking_id": internal_picking.id,
            }
        )

        url = self._get_client_action_url(internal_picking.id)
        internal_picking.action_confirm()
        internal_picking.action_assign()

        self.start_tour(
            url, "test_put_in_pack_from_multiple_pages", login="admin", timeout=180
        )

        pack = self.env["stock.package"].search([])[-1]
        self.assertEqual(len(pack.quant_ids), 2)
        self.assertEqual(sum(pack.quant_ids.mapped("quantity")), 4)

    def test_put_in_pack_in_new_created_package(self):
        group_package = self.env.ref("stock.group_tracking_lot")
        self.env.user.write({"group_ids": [Command.link(group_package.id)]})
        self._reset_package_sequence(42)
        receipt = self.env["stock.picking"].create(
            {
                "location_id": self.picking_type_in.default_location_src_id.id,
                "location_dest_id": self.picking_type_in.default_location_dest_id.id,
                "name": "TEST/IN/0001",
                "picking_type_id": self.picking_type_in.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.picking_type_in.default_location_src_id.id,
                            "location_dest_id": self.picking_type_in.default_location_dest_id.id,
                            "product_id": self.product1.id,
                            "product_uom_qty": 1,
                        }
                    ),
                    Command.create(
                        {
                            "location_id": self.picking_type_in.default_location_src_id.id,
                            "location_dest_id": self.picking_type_in.default_location_dest_id.id,
                            "product_id": self.product2.id,
                            "product_uom_qty": 1,
                        }
                    ),
                ],
            }
        )
        receipt.action_confirm()
        self.start_tour(
            "/odoo/barcode", "test_put_in_pack_in_new_created_package", login="admin"
        )
        self.assertEqual(
            receipt.move_ids.move_line_ids.result_package_id.name, "PACK0000042"
        )
        self.assertEqual(
            receipt.move_ids[0].move_line_ids.result_package_id.id,
            receipt.move_ids[1].move_line_ids.result_package_id.id,
            "The two receipt's moves must go into the same package",
        )

    def test_put_in_pack_no_freeze(self):
        self.env["res.config.settings"].create(
            {"group_stock_tracking_lot": True}
        ).execute()

        receipt_form = Form(self.env["stock.picking"])
        receipt_form.picking_type_id = self.picking_type_in
        with receipt_form.move_ids.new() as move:
            move.product_id = self.productlot1
            move.product_uom_qty = 13.5

        receipt = receipt_form.save()
        receipt.action_confirm()
        receipt.action_assign()

        action_id = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = "/web#action=" + str(action_id.id)
        self.start_tour(url, "test_put_in_pack_no_freeze", login="admin", timeout=180)

    def test_unpack_package_lines(self):
        group_package = self.env.ref("stock.group_tracking_lot")
        self.env.user.write({"group_ids": [Command.link(group_package.id)]})
        self.picking_type_out.show_entire_packs = True
        box1, box2, palet1, palet2 = self.env["stock.package"].create(
            [
                {"name": "BOX01"},
                {"name": "BOX02"},
                {"name": "PAL01"},
                {"name": "PAL02"},
            ]
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4, package_id=box1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 4, package_id=box1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4, package_id=box2
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 4, package_id=box2
        )
        box1.parent_package_id = palet1
        box2.parent_package_id = palet1
        delivery = self.env["stock.picking"].create(
            {
                "location_id": self.picking_type_out.default_location_src_id.id,
                "location_dest_id": self.picking_type_out.default_location_dest_id.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_uom_qty": 8,
                        }
                    )
                    for product in (self.product1, self.product2)
                ],
            }
        )
        delivery.action_confirm()
        url = self._get_client_action_url(delivery.id)
        self.start_tour(url, "test_unpack_package_lines", login="admin")
        self.assertRecordValues(
            palet2.quant_ids,
            [
                {
                    "product_id": self.product1.id,
                    "quantity": 8,
                    "package_id": palet2.id,
                },
                {
                    "product_id": self.product2.id,
                    "quantity": 8,
                    "package_id": palet2.id,
                },
            ],
        )
        self.assertEqual((box1.quant_ids | box2.quant_ids | palet1.quant_ids).ids, [])

    def test_unpack_palet_then_pack_another_palet(self):
        group_package = self.env.ref("stock.group_tracking_lot")
        group_location = self.env.ref("stock.group_stock_multi_locations")
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(group_location.id),
                    Command.link(group_package.id),
                ]
            }
        )
        self.picking_type_internal.active = True
        self.picking_type_internal.restrict_scan_source_location = "no"
        self.picking_type_internal.restrict_scan_dest_location = "optional"
        self.picking_type_internal.show_entire_packs = True
        self.picking_type_out.restrict_scan_source_location = "no"
        self.picking_type_out.show_entire_packs = True
        box, palet = self.env["stock.package.type"].create(
            [
                {"name": "Box", "sequence_code": "BOX-"},
                {"name": "Palet", "sequence_code": "PAL-", "barcode": "PT_PALET"},
            ]
        )
        box1, box2, palet1 = self.env["stock.package"].create(
            [
                {"name": "BOX01", "package_type_id": box.id},
                {"name": "BOX02", "package_type_id": box.id},
                {"name": "PAL01", "package_type_id": palet.id},
            ]
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4, package_id=box1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 4, package_id=box1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4, package_id=box2
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 4, package_id=box2
        )
        box1.parent_package_id = palet1
        box2.parent_package_id = palet1
        self.start_tour(
            "/odoo/barcode", "test_unpack_palet_then_pack_another_palet", login="admin"
        )
        internal = self._last_picking(self.picking_type_internal)
        delivery = self._last_picking(self.picking_type_out)
        self.assertEqual((internal | delivery).mapped("state"), ["done", "done"])
        new_palet = internal.move_line_ids.result_package_id.parent_package_id
        self.assertEqual(internal.move_line_ids.result_package_id, box1 | box2)
        self.assertEqual(len(new_palet), 1)
        self.assertNotEqual(new_palet, palet1)
        self.assertEqual(new_palet.package_type_id, palet)
        self.assertEqual(
            delivery.move_line_ids.result_package_id.parent_package_id, new_palet
        )

    def test_reload_flow(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )

        self.start_tour("/odoo/barcode", "test_reload_flow", login="admin", timeout=180)

        move_line1 = self.env["stock.move.line"].search_count(
            [
                ("product_id", "=", self.product1.id),
                ("location_dest_id", "=", self.shelf1.id),
                ("location_id", "=", self.supplier_location.id),
                ("quantity", "=", 2),
                ("picked", "=", True),
            ]
        )
        move_line2 = self.env["stock.move.line"].search_count(
            [
                ("product_id", "=", self.product2.id),
                ("location_dest_id", "=", self.shelf1.id),
                ("location_id", "=", self.supplier_location.id),
                ("quantity", "=", 1),
                ("picked", "=", True),
            ]
        )
        self.assertEqual(move_line1, 1)
        self.assertEqual(move_line2, 1)

    def test_duplicate_serial_number(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )
        self.start_tour(
            "/odoo/barcode",
            "test_receipt_duplicate_serial_number",
            login="admin",
            timeout=180,
        )
        self.start_tour(
            "/odoo/barcode",
            "test_delivery_duplicate_serial_number",
            login="admin",
            timeout=180,
        )
        receipt = self._last_picking(self.picking_type_in)
        delivery = self._last_picking(self.picking_type_out)
        for picking in receipt | delivery:
            self.assertEqual(picking.state, "done", picking.name)
            self.assertEqual(
                sorted(ml.trace_id.name for ml in picking.move_line_ids),
                ["sn1", "sn2"],
                picking.name,
            )

    def test_bypass_source_scan(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                    Command.link(self.env.ref("stock.group_production_lot").id),
                ],
            }
        )
        self.picking_type_out.restrict_scan_source_location = "no"

        lot1 = self.env["product.trace"].create(
            {"name": "lot1", "product_id": self.productlot1.id}
        )
        lot2 = self.env["product.trace"].create(
            {"name": "serial1", "product_id": self.productserial1.id}
        )

        pack1 = self.env["stock.package"].create(
            {
                "name": "THEPACK",
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.shelf1, 2, trace_id=lot1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productserial1, self.shelf2, 1, trace_id=lot2
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf2, 4, package_id=pack1
        )

        pack2 = self.env["stock.package"].create({"name": "SUSPACK"})
        other_loc = self.env["stock.location"].create(
            {
                "name": "Second Stock",
                "location_id": self.stock_location.location_id.id,
                "barcode": "WH-SECOND-STOCK",
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, other_loc, 4, package_id=pack2
        )

        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        url = self._get_client_action_url(delivery_picking.id)

        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.productserial1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 1,
                "picking_id": delivery_picking.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.productlot1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 2,
                "picking_id": delivery_picking.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 4,
                "picking_id": delivery_picking.id,
            }
        )
        delivery_picking.action_confirm()
        delivery_picking.action_assign()

        self.start_tour(url, "test_bypass_source_scan", login="admin", timeout=180)
        self.assertEqual(delivery_picking.state, "done")
        self.assertEqual(
            sorted(
                (
                    ml.product_id.name,
                    ml.trace_id.name or "",
                    ml.package_id.name or "",
                    ml.location_id.name,
                    ml.quantity,
                )
                for ml in delivery_picking.move_line_ids
            ),
            [
                ("product1", "", "THEPACK", "Section 2", 4),
                ("productlot1", "lot1", "", "Section 1", 2),
                ("productserial1", "serial1", "", "Section 2", 1),
            ],
        )

    def test_put_in_pack_from_different_location(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        self.picking_type_internal.active = True
        self.picking_type_internal.restrict_scan_source_location = "no"
        self.picking_type_internal.restrict_scan_dest_location = "optional"
        self._reset_package_sequence()
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf3, 1
        )

        internal_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_internal.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.shelf1.id,
                "location_dest_id": self.shelf2.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 1,
                "picking_id": internal_picking.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.shelf3.id,
                "location_dest_id": self.shelf2.id,
                "product_id": self.product2.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 1,
                "picking_id": internal_picking.id,
            }
        )

        url = self._get_client_action_url(internal_picking.id)
        internal_picking.action_confirm()
        internal_picking.action_assign()

        self.start_tour(
            url, "test_put_in_pack_from_different_location", login="admin", timeout=180
        )
        pack = internal_picking.move_line_ids.result_package_id
        self.assertEqual(len(pack.quant_ids), 2)
        self.assertEqual(pack.location_id, self.shelf2)

    def test_put_in_pack_before_dest(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        self.picking_type_internal.active = True
        self.picking_type_internal.restrict_scan_dest_location = "mandatory"
        self.picking_type_internal.restrict_scan_source_location = "mandatory"

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf3, 1
        )

        internal_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_internal.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.shelf1.id,
                "location_dest_id": self.shelf2.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 1,
                "picking_id": internal_picking.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.shelf3.id,
                "location_dest_id": self.shelf4.id,
                "product_id": self.product2.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 1,
                "picking_id": internal_picking.id,
            }
        )

        url = self._get_client_action_url(internal_picking.id)
        internal_picking.action_confirm()
        internal_picking.action_assign()

        self.start_tour(url, "test_put_in_pack_before_dest", login="admin", timeout=180)
        pack = internal_picking.move_line_ids.result_package_id
        self.assertEqual(len(pack), 1)
        self.assertEqual(len(pack.quant_ids), 2)
        self.assertEqual(pack.location_id, self.shelf2)

    def test_put_in_pack_scan_package(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        self._reset_package_sequence()
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf2, 1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf1, 1
        )

        delivery_form = Form(self.env["stock.picking"])
        delivery_form.picking_type_id = self.picking_type_out
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 2
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product2
            move.product_uom_qty = 1

        delivery = delivery_form.save()
        delivery.action_confirm()
        delivery.action_assign()

        url = self._get_client_action_url(delivery.id)
        self.start_tour(
            url, "test_put_in_pack_scan_package", login="admin", timeout=180
        )

        self.assertEqual(delivery.state, "done")
        self.assertEqual(len(delivery.move_line_ids), 3)
        for move_line in delivery.move_line_ids:
            self.assertEqual(move_line.result_package_id.name, "PACK0000001")

    def test_put_in_pack_new_lines(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )

        receipt01 = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        url = self._get_client_action_url(receipt01.id)
        self.start_tour(url, "test_put_in_pack_new_lines", login="admin", timeout=180)

        self.assertRecordValues(
            receipt01.move_line_ids,
            [
                {
                    "product_id": self.product1.id,
                    "qty_done": 1,
                    "result_package_id": self.package.id,
                },
            ],
        )
        self.assertEqual(self.package.quant_ids.available_quantity, 1)

        receipt02 = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        url = self._get_client_action_url(receipt02.id)
        self.start_tour(url, "test_put_in_pack_new_lines", login="admin", timeout=180)

        self.assertRecordValues(
            receipt02.move_line_ids,
            [
                {
                    "product_id": self.product1.id,
                    "qty_done": 1,
                    "result_package_id": self.package.id,
                },
            ],
        )
        self.assertEqual(self.package.quant_ids.available_quantity, 2)

    def test_put_packs_in_existing_pack(self):
        group_package = self.env.ref("stock.group_tracking_lot")
        self.env.user.write({"group_ids": [Command.link(group_package.id)]})
        self.picking_type_out.restrict_scan_source_location = "no"
        mini_box, maxi_box = self.env["stock.package.type"].create(
            [
                {"name": "Mini-Box", "sequence_code": "MNB-"},
                {"name": "Maxi-Box", "sequence_code": "MXB-"},
            ]
        )
        package_create_vals = []
        for amount, package_type in [(4, mini_box), (2, maxi_box)]:
            package_create_vals += [
                {
                    "package_type_id": package_type.id,
                }
                for __ in range(amount)
            ]
        packages = self.env["stock.package"].create(package_create_vals)
        for pack in packages:
            if pack.package_type_id == maxi_box:
                continue
            self.env["stock.quant"]._update_available_quantity(
                self.product1, self.stock_location, 4, package_id=pack
            )
        out_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product1.id,
                            "product_uom_qty": 16,
                        }
                    )
                ],
            }
        )
        out_picking.action_confirm()
        url = self._get_client_action_url(out_picking.id)
        self.start_tour(url, "test_put_packs_in_existing_pack", login="admin")

    def test_put_packs_in_new_pack(self):
        group_package = self.env.ref("stock.group_tracking_lot")
        self.env.user.write({"group_ids": [Command.link(group_package.id)]})
        self.picking_type_out.restrict_scan_source_location = "no"
        package_types = self.env["stock.package.type"].create(
            [
                {"name": "Mini-Box", "barcode": "minibox", "sequence_code": "MNB-"},
                {"name": "Maxi-Box", "barcode": "maxibox", "sequence_code": "MXB-"},
            ]
        )
        packages = self.env["stock.package"].create(
            [{"package_type_id": package_types[0].id} for __ in range(4)]
        )
        for pack in packages:
            self.env["stock.quant"]._update_available_quantity(
                self.product1, self.stock_location, 4, package_id=pack
            )
        out_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product1.id,
                            "product_uom_qty": 16,
                        }
                    )
                ],
            }
        )
        out_picking.name = "WH/OUT/TEST/001"
        out_picking.action_confirm()
        self.start_tour("/odoo/barcode", "test_put_packs_in_new_pack", login="admin")
        receipt = self._last_picking(self.picking_type_in)
        self.assertEqual(receipt.state, "done")
        self.assertEqual(
            sorted(
                (
                    ml.result_package_id.parent_package_id.name,
                    ml.result_package_id.name,
                    ml.product_id.name,
                )
                for ml in receipt.move_line_ids
            ),
            [
                (maxi, mini, product)
                for (maxi, minis) in [
                    ("MXB-0000001", ["MNB-0000005", "MNB-0000006"]),
                    ("MXB-0000002", ["MNB-0000007", "MNB-0000008"]),
                ]
                for mini in minis
                for product in ["product1", "product2"]
            ],
        )
        self.assertEqual(
            sorted(
                (ml.outermost_result_package_id.name, ml.result_package_id.name)
                for ml in out_picking.move_line_ids
            ),
            [
                ("MXB-0000003", "MNB-0000001"),
                ("MXB-0000003", "MNB-0000002"),
                ("MXB-0000004", "MNB-0000003"),
                ("MXB-0000004", "MNB-0000004"),
            ],
        )

    def test_highlight_packs(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )

        pack1 = self.env["stock.package"].create(
            {
                "name": "PACK001",
            }
        )
        pack2 = self.env["stock.package"].create(
            {
                "name": "PACK002",
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4, package_id=pack1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 4, package_id=pack1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 2, package_id=pack2
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 2, package_id=pack2
        )

        out_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "state": "draft",
            }
        )

        self.picking_type_out.show_entire_packs = True
        out_picking.action_add_entire_packs(pack1.id)

        url = self._get_client_action_url(out_picking.id)
        out_picking.action_confirm()
        out_picking.action_assign()

        self.start_tour(url, "test_highlight_packs", login="admin", timeout=180)

    def test_picking_owner_scan_package(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_tracking_owner").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product1,
            self.stock_location,
            7,
            package_id=self.package,
            owner_id=self.owner,
        )

        self.start_tour(
            "/odoo/barcode",
            "test_picking_owner_scan_package",
            login="admin",
            timeout=180,
        )

        move_line = self.env["stock.move.line"].search(
            [("product_id", "=", self.product1.id)], limit=1
        )
        self.assertTrue(move_line)

        line_owner = move_line.owner_id
        self.assertEqual(line_owner.id, self.owner.id)

    def test_picking_type_mandatory_scan_settings(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_production_lot").id),
                ],
            }
        )
        product_without_barcode = self.env["product.product"].create(
            {
                "name": "Barcodeless Product",
                "is_storable": True,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 8
        )
        self.env["stock.quant"]._update_available_quantity(
            product_without_barcode, self.shelf1, 8
        )

        self.picking_type_internal.barcode_validation_after_dest_location = False
        self.picking_type_internal.barcode_validation_all_product_packed = False
        self.picking_type_internal.barcode_validation_full = False
        self.picking_type_internal.restrict_scan_product = True
        self.picking_type_internal.restrict_put_in_pack = "optional"
        self.picking_type_internal.restrict_scan_source_location = "no"
        self.picking_type_internal.restrict_scan_dest_location = "no"

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_internal
        with picking_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 4
        with picking_form.move_ids.new() as move:
            move.product_id = product_without_barcode
            move.product_uom_qty = 4

        picking_internal_1 = picking_form.save()
        picking_internal_1.action_confirm()
        picking_internal_1.action_assign()

        url = self._get_client_action_url(picking_internal_1.id)
        self.start_tour(
            url,
            "test_picking_type_mandatory_scan_settings_pick_int_1",
            login="admin",
            timeout=180,
        )
        self.assertEqual(picking_internal_1.state, "done")

        self.picking_type_internal.restrict_scan_source_location = "mandatory"
        self.picking_type_internal.restrict_scan_dest_location = "mandatory"
        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_internal
        with picking_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 4
        with picking_form.move_ids.new() as move:
            move.product_id = product_without_barcode
            move.product_uom_qty = 4

        picking_internal_2 = picking_form.save()
        picking_internal_2.action_confirm()
        picking_internal_2.action_assign()

        url = self._get_client_action_url(picking_internal_2.id)
        self.start_tour(
            url,
            "test_picking_type_mandatory_scan_settings_pick_int_2",
            login="admin",
            timeout=180,
        )
        self.assertEqual(picking_internal_2.state, "done")

    def test_receipt_scan_package_and_location_after_group_of_product(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        product_without_barcode = self.env["product.product"].create(
            {
                "name": "Barcodeless Product",
                "is_storable": True,
            }
        )
        package = self.env["stock.package"].create({"name": "pack-128"})

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_in
        with picking_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 4
        with picking_form.move_ids.new() as move:
            move.product_id = product_without_barcode
            move.product_uom_qty = 4
        with picking_form.move_ids.new() as move:
            move.product_id = self.productlot1
            move.product_uom_qty = 6

        picking_receipt = picking_form.save()
        picking_receipt.action_confirm()
        picking_receipt.action_assign()

        url = self._get_client_action_url(picking_receipt.id)
        self.start_tour(
            url,
            "test_receipt_scan_package_and_location_after_group_of_product",
            login="admin",
            timeout=180,
        )
        self.assertEqual(picking_receipt.state, "done")
        (lot1, lot2, lot3) = self.env["product.trace"].search(
            [
                ("product_id", "=", self.productlot1.id),
                ("name", "in", ["lot-01", "lot-02", "lot-03"]),
            ]
        )
        move_lines = picking_receipt.move_line_ids.sorted(
            lambda ml: (ml.product_id.id, ml.location_dest_id.id)
        )
        self.assertRecordValues(
            move_lines,
            [
                {
                    "product_id": self.product1.id,
                    "location_dest_id": self.shelf3.id,
                    "qty_done": 2,
                    "trace_id": False,
                    "result_package_id": package.id,
                },
                {
                    "product_id": self.product1.id,
                    "location_dest_id": self.shelf1.id,
                    "qty_done": 2,
                    "trace_id": False,
                    "result_package_id": False,
                },
                {
                    "product_id": self.productlot1.id,
                    "location_dest_id": self.shelf3.id,
                    "qty_done": 2,
                    "trace_id": lot3.id,
                    "result_package_id": package.id,
                },
                {
                    "product_id": self.productlot1.id,
                    "location_dest_id": self.shelf1.id,
                    "qty_done": 2,
                    "trace_id": lot1.id,
                    "result_package_id": False,
                },
                {
                    "product_id": self.productlot1.id,
                    "location_dest_id": self.shelf1.id,
                    "qty_done": 1,
                    "trace_id": lot2.id,
                    "result_package_id": False,
                },
                {
                    "product_id": self.productlot1.id,
                    "location_dest_id": self.shelf2.id,
                    "qty_done": 1,
                    "trace_id": lot2.id,
                    "result_package_id": False,
                },
                {
                    "product_id": product_without_barcode.id,
                    "location_dest_id": self.shelf1.id,
                    "qty_done": 4,
                    "trace_id": False,
                    "result_package_id": False,
                },
            ],
        )

    def test_receipt_assign_sibling_reservation_no_empty_line(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_production_lot").id),
                ],
            }
        )

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_in
        with picking_form.move_ids.new() as move:
            move.product_id = self.productlot1
            move.product_uom_qty = 2

        picking_receipt = picking_form.save()
        picking_receipt.action_confirm()
        picking_receipt.action_assign()

        url = self._get_client_action_url(picking_receipt.id)
        self.start_tour(
            url,
            "test_receipt_assign_sibling_reservation_no_empty_line",
            login="admin",
            timeout=180,
        )

        self.assertEqual(picking_receipt.state, "done")
        (lot1, lot2) = self.env["product.trace"].search(
            [
                ("product_id", "=", self.productlot1.id),
                ("name", "in", ["lot-01", "lot-02"]),
            ]
        )
        move_lines = picking_receipt.move_line_ids.sorted(
            lambda ml: (ml.product_id.id, ml.trace_id.id)
        )
        self.assertRecordValues(
            move_lines,
            [
                {
                    "product_id": self.productlot1.id,
                    "location_dest_id": self.shelf1.id,
                    "qty_done": 1,
                    "trace_id": lot1.id,
                },
                {
                    "product_id": self.productlot1.id,
                    "location_dest_id": self.shelf1.id,
                    "qty_done": 1,
                    "trace_id": lot2.id,
                },
            ],
        )

    def test_picking_type_mandatory_scan_complete_flux(self):

        def create_picking(picking_type):
            picking_form = Form(self.env["stock.picking"])
            picking_form.picking_type_id = picking_type
            with picking_form.move_ids.new() as move:
                move.product_id = self.product1
                move.product_uom_qty = 2
            with picking_form.move_ids.new() as move:
                move.product_id = self.product2
                move.product_uom_qty = 1
            with picking_form.move_ids.new() as move:
                move.product_id = product_without_barcode
                move.product_uom_qty = 1
            with picking_form.move_ids.new() as move:
                move.product_id = self.productserial1
                move.product_uom_qty = 3
            with picking_form.move_ids.new() as move:
                move.product_id = self.productlot1
                move.product_uom_qty = 6
            return picking_form.save()

        product_without_barcode = self.env["product.product"].create(
            {
                "name": "Barcodeless Product",
                "is_storable": True,
            }
        )

        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_adv_location").id)]}
        )
        self.warehouse.reception_steps = "two_steps"
        self.warehouse.delivery_steps = "pick_pack_ship"

        reusable_type = self.env["stock.package.type"].create(
            {
                "name": "Reusable cluster",
                "package_use": "reusable",
            }
        )
        self.env["stock.package"].create(
            {
                "name": "cluster-pack-01",
                "package_type_id": reusable_type.id,
            }
        )
        self.env["stock.package"].create(
            {
                "name": "cluster-pack-02",
                "package_type_id": reusable_type.id,
            }
        )
        self._reset_package_sequence()

        self.picking_type_in.barcode_validation_full = False
        self.picking_type_in.restrict_put_in_pack = "no"
        internal_types = self.warehouse.qc_type_id | self.warehouse.store_type_id
        internal_types.barcode_validation_full = False
        internal_types.restrict_put_in_pack = "no"
        internal_types.restrict_scan_dest_location = "mandatory"
        internal_types.show_reserved_sns = True
        self.warehouse.pick_type_id.barcode_validation_full = False
        self.warehouse.pick_type_id.restrict_scan_source_location = "mandatory"
        self.warehouse.pick_type_id.restrict_put_in_pack = "mandatory"
        self.warehouse.pick_type_id.restrict_scan_tracking_number = "mandatory"
        self.warehouse.pick_type_id.restrict_scan_dest_location = "no"
        self.warehouse.pick_type_id.show_reserved_sns = True
        self.warehouse.pack_type_id.restrict_put_in_pack = "optional"
        self.warehouse.pack_type_id.restrict_scan_tracking_number = "mandatory"
        self.warehouse.pack_type_id.barcode_validation_all_product_packed = True
        self.warehouse.pick_type_id.restrict_scan_dest_location = "no"
        self.picking_type_out.restrict_put_in_pack = "optional"
        self.picking_type_out.restrict_scan_source_location = "no"
        self.picking_type_out.restrict_scan_tracking_number = "mandatory"
        self.picking_type_out.barcode_validation_all_product_packed = True
        self.picking_type_out.show_entire_packs = True

        picking_receipt = create_picking(self.picking_type_in)
        picking_receipt.action_confirm()
        picking_receipt.action_assign()

        picking_pick = create_picking(self.warehouse.pick_type_id)

        url = self._get_client_action_url(picking_receipt.id)
        self.start_tour(
            url,
            "test_picking_type_mandatory_scan_complete_flux_receipt",
            login="admin",
            timeout=180,
        )
        self.assertEqual(picking_receipt.state, "done")

        picking_internal = picking_receipt.move_ids.move_dest_ids.picking_id
        url = self._get_client_action_url(picking_internal.id)
        self.start_tour(
            url,
            "test_picking_type_mandatory_scan_complete_flux_internal",
            login="admin",
            timeout=180,
        )
        self.assertEqual(picking_internal.state, "done")
        picking_pick.action_confirm()
        picking_pick.action_assign()
        url = self._get_client_action_url(picking_pick.id)
        self.start_tour(
            url,
            "test_picking_type_mandatory_scan_complete_flux_pick",
            login="admin",
            timeout=180,
        )
        self.assertEqual(picking_pick.state, "done")

        picking_pack = self.env["stock.picking"].search(
            [
                (
                    "location_id",
                    "=",
                    self.warehouse.pack_type_id.default_location_src_id.id,
                )
            ]
        )
        picking_pack.action_confirm()
        picking_pack.action_assign()
        for move_line in picking_pack.move_line_ids:
            move_line.result_package_id = False
        url = self._get_client_action_url(picking_pack.id)
        self.start_tour(
            url,
            "test_picking_type_mandatory_scan_complete_flux_pack",
            login="admin",
            timeout=180,
        )
        self.assertEqual(picking_pack.state, "done")

        picking_delivery = self.env["stock.picking"].search(
            [
                (
                    "location_id",
                    "=",
                    self.warehouse.out_type_id.default_location_src_id.id,
                )
            ]
        )
        picking_delivery.action_confirm()
        picking_delivery.action_assign()
        url = self._get_client_action_url(picking_delivery.id)
        self.start_tour(
            url,
            "test_picking_type_mandatory_scan_complete_flux_delivery",
            login="admin",
            timeout=180,
        )
        self.assertEqual(picking_delivery.state, "done")

    def test_procurement_backorder(self):
        product_a, _product_b = self.env["product.product"].create(
            [
                {
                    "name": p_name,
                    "is_storable": True,
                    "barcode": p_name,
                }
                for p_name in ["PA", "PB"]
            ]
        )

        reference = self.env["stock.reference"].create(
            {"name": "test_procurement_backorder"}
        )

        procurement = self.env["stock.rule"].Procurement(
            product_a,
            1,
            product_a.uom_id,
            self.env.ref("stock.stock_location_customers"),
            product_a.name,
            "/",
            self.env.company,
            {
                "warehouse_id": self.warehouse,
                "reference_ids": reference,
            },
        )
        self.env["stock.rule"].run([procurement])

        move = self.env["stock.move"].search(
            [("product_id", "=", product_a.id)], limit=1
        )
        url = self._get_client_action_url(move.picking_id.id)
        self.start_tour(url, "test_procurement_backorder", login="admin", timeout=99)
        self.assertEqual(len(reference.move_ids), 2)

    def test_receipt_delete_button(self):
        receipt_picking = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "product_id": self.product1.id,
                "product_uom_id": self.product1.uom_id.id,
                "product_uom_qty": 1,
                "picking_id": receipt_picking.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        self.env["product.product"].create(
            {
                "name": "product3",
                "is_storable": True,
                "barcode": "product3",
            }
        )

        url = self._get_client_action_url(receipt_picking.id)
        receipt_picking.action_confirm()
        self.start_tour(url, "test_receipt_delete_button", login="admin", timeout=180)
        self.assertEqual(
            len(receipt_picking.move_line_ids),
            2,
            "2 lines expected: product1 + product2",
        )

    def test_scan_aggregate_barcode(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.env["ir.config_parameter"].set_param(
            "stock_barcode.barcode_separator_regex", "[,|]"
        )
        url = "/odoo/action-stock_barcode.stock_barcode_action_main_menu"
        self.start_tour(url, "test_scan_aggregate_barcode", login="admin", timeout=180)
        domain = [
            ("picking_type_id", "=", self.picking_type_in.id),
            ("state", "=", "done"),
        ]
        receipt = self.env["stock.picking"].search(domain, limit=1, order="id DESC")
        self.assertRecordValues(
            receipt.move_ids.sorted(lambda mv: mv.product_id),
            [
                {"product_id": self.product1.id, "quantity": 4},
                {"product_id": self.product2.id, "quantity": 2},
                {"product_id": self.productserial1.id, "quantity": 10},
            ],
        )
        tracked_move = receipt.move_ids.filtered(
            lambda mv: mv.product_id == self.productserial1
        )
        self.assertEqual(
            tracked_move.trace_ids.sorted(lambda sn: sn.name).mapped("name"),
            [
                "sn01",
                "sn02",
                "sn03",
                "sn04",
                "sn05",
                "sn06",
                "sn07",
                "sn08",
                "sn09",
                "sn10",
            ],
        )

    def test_scrap(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.env["product.trace"].create(
            [
                {
                    "name": "SN0001",
                    "product_id": self.productserial1.id,
                },
                {
                    "name": "SN0002",
                    "product_id": self.productserial1.id,
                },
            ]
        )
        receipt_form = Form(self.env["stock.picking"])
        receipt_form.picking_type_id = self.picking_type_in
        with receipt_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 1
        with receipt_form.move_ids.new() as move:
            move.product_id = self.productserial1
        receipt_picking = receipt_form.save()
        receipt_picking.action_confirm()
        receipt_picking.action_assign()
        receipt_picking.name = "receipt_scrap_test"

        delivery_form = Form(self.env["stock.picking"])
        delivery_form.picking_type_id = self.picking_type_out
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 1
        delivery_picking = delivery_form.save()
        delivery_picking.action_confirm()
        delivery_picking.action_assign()
        delivery_picking.name = "delivery_scrap_test"
        self.start_tour("/odoo/barcode", "test_scrap", login="admin", timeout=180)
        self.assertEqual(receipt_picking.state, "done")
        self.assertEqual(delivery_picking.state, "done")

    def test_scrap_change_source_location(self):
        self.env.user.group_ids = [
            Command.link(self.env.ref("stock.group_stock_multi_locations").id),
            Command.link(self.env.ref("stock.group_production_lot").id),
        ]
        dest_location = self.picking_type_out.default_location_dest_id
        self.product1.tracking = "lot"
        lot1 = self.env["product.trace"].create(
            {
                "name": "Lot1",
                "product_id": self.product1.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 25, trace_id=lot1
        )
        picking = self.env["stock.picking"].create(
            {
                "name": self.product1.name,
                "location_id": self.stock_location.id,
                "location_dest_id": dest_location.id,
                "picking_type_id": self.picking_type_internal.id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product1.id,
                "trace_ids": [Command.set(lot1.ids)],
                "product_uom_qty": 10.00,
                "quantity": 10.00,
                "picking_id": picking.id,
                "location_id": self.stock_location.id,
                "location_dest_id": dest_location.id,
            }
        )
        picking.action_confirm()
        url = self._get_client_action_url(picking.id)
        self.start_tour(url, "test_scrap_change_source_location", login="admin")
        scrap_location_id = self.env.company._get_scrap_location().id
        self.assertRecordValues(
            lot1.quant_ids,
            [
                {"location_id": self.shelf1.id, "quantity": 0},
                {"location_id": scrap_location_id, "quantity": 15},
                {"location_id": dest_location.id, "quantity": 10},
            ],
        )

    def test_show_entire_package(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )
        self.picking_type_out.show_entire_packs = True
        package1 = self.env["stock.package"].create({"name": "package001"})
        package2 = self.env["stock.package"].create({"name": "package002"})

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4, package_id=package1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4, package_id=package2
        )

        delivery_with_package_level = self.env["stock.picking"].create(
            {
                "name": "Delivery with Package Level",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "state": "draft",
            }
        )
        delivery_with_package_level.action_confirm()
        delivery_with_package_level.action_add_entire_packs(package1.id)
        delivery_with_package_level.action_assign()

        delivery_with_move = self.env["stock.picking"].create(
            {
                "name": "Delivery with Stock Move",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "state": "draft",
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "product_id": self.product1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 2,
                "picking_id": delivery_with_move.id,
            }
        )
        delivery_with_move.action_confirm()
        delivery_with_move.action_assign()

        self.start_tour(
            "/odoo/barcode", "test_show_entire_package", login="admin", timeout=180
        )

    def test_define_the_destination_package(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )

        pack01, pack02 = self.env["stock.package"].create(
            [
                {
                    "name": name,
                }
                for name in ("PACK01", "PACK02")
            ]
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 2, package_id=pack01
        )

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_out
        with picking_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 1
        delivery = picking_form.save()
        delivery.action_confirm()

        url = self._get_client_action_url(delivery.id)
        self.start_tour(
            url, "test_define_the_destination_package", login="admin", timeout=180
        )

        self.assertRecordValues(
            delivery.move_line_ids,
            [
                {
                    "product_id": self.product1.id,
                    "qty_done": 1,
                    "result_package_id": pack02.id,
                    "state": "done",
                },
            ],
        )

    def test_avoid_useless_line_creation(self):
        self.picking_type_out.use_create_lots = False
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        lot01 = self.env["product.trace"].create(
            {
                "name": "LOT01",
                "product_id": self.productlot1.id,
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 1, trace_id=lot01
        )

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_out
        delivery = picking_form.save()

        url = self._get_client_action_url(delivery.id)
        self.start_tour(
            url, "test_avoid_useless_line_creation", login="admin", timeout=180
        )

        self.assertRecordValues(
            delivery.move_ids,
            [
                {
                    "product_id": self.productlot1.id,
                    "trace_ids": lot01.ids,
                    "quantity": 1,
                },
            ],
        )

    def test_setting_barcode_allow_extra_product(self):
        self.picking_type_out.barcode_allow_extra_product = False
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": self.product1.id,
                "inventory_quantity": 1,
                "location_id": self.stock_location.id,
            }
        ).action_apply_inventory()
        delivery = self.env["stock.picking"].create(
            {
                "name": "delivery_test",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.supplier_location.id,
                "product_id": self.product1.id,
                "product_uom_qty": 1,
                "picking_id": delivery.id,
            }
        )
        delivery.action_confirm()
        delivery.action_assign()
        self.start_tour(
            "/odoo/barcode",
            "test_setting_barcode_allow_extra_product",
            login="admin",
            timeout=180,
        )
        self.assertEqual(delivery.state, "done")
        self.assertEqual(
            [(ml.product_id, ml.quantity) for ml in delivery.move_line_ids],
            [(self.product1, 1)],
            "a product the delivery does not reserve is refused",
        )

    def test_setting_barcode_allow_extra_product_with_packages(self):
        grp_pack = self.env.ref("stock.group_tracking_lot")
        self.env.user.write({"group_ids": [Command.link(grp_pack.id)]})
        self.picking_type_out.barcode_allow_extra_product = False
        picking_type_out_move_entire_package = self.picking_type_out.copy(
            {"show_entire_packs": True}
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 10
        )
        pack01, pack02, pack03, pack04 = self.env["stock.package"].create(
            [{"name": f"PACK0{i + 1}"} for i in range(4)]
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 10, package_id=pack01
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 10, package_id=pack02
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 10, package_id=pack03
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 10, package_id=pack04
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 5, package_id=pack04
        )

        deliveries = self.env["stock.picking"].create(
            [
                {
                    "name": "SBAEPWP",
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.customer_location.id,
                    "picking_type_id": self.picking_type_out.id,
                    "move_ids": [
                        Command.create(
                            {
                                "location_id": self.stock_location.id,
                                "location_dest_id": self.customer_location.id,
                                "product_id": self.product1.id,
                                "product_uom_qty": 5,
                            }
                        ),
                    ],
                },
                {
                    "name": "SBAEPWMEP",
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.customer_location.id,
                    "picking_type_id": picking_type_out_move_entire_package.id,
                },
            ]
        )
        deliveries[1].action_add_entire_packs(pack02.id)
        deliveries.action_confirm()

        self.start_tour(
            "/odoo/barcode",
            "test_setting_barcode_allow_extra_product_with_packages",
            login="admin",
        )

    def test_split_line_reservation(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_adv_location").id),
                ],
            }
        )

        lot01 = self.env["product.trace"].create(
            {
                "name": "LOT01",
                "product_id": self.productlot1.id,
            }
        )

        lot02 = self.env["product.trace"].create(
            {
                "name": "LOT02",
                "product_id": self.productlot1.id,
            }
        )

        lot03 = self.env["product.trace"].create(
            {
                "name": "LOT03",
                "product_id": self.productlot1.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 5, trace_id=lot01
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 5, trace_id=lot02
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 5
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 5
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.shelf1, 2, trace_id=lot02
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.shelf2, 2, trace_id=lot03
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 1
        )
        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_out
        with picking_form.move_ids.new() as move:
            move.product_id = self.productlot1
            move.product_uom_qty = 5
        with picking_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 4
        with picking_form.move_ids.new() as move:
            move.product_id = self.product2
            move.product_uom_qty = 3

        delivery = picking_form.save()
        delivery.action_confirm()
        delivery.action_assign()

        url = self._get_client_action_url(delivery.id)
        self.start_tour(url, "test_split_line_reservation", login="admin", timeout=180)
        productlot_mls = delivery.move_ids.filtered(
            lambda m: m.product_id.id == self.productlot1.id
        ).move_line_ids
        product1_mls = delivery.move_ids.filtered(
            lambda m: m.product_id.id == self.product1.id
        ).move_line_ids
        product2_mls = delivery.move_ids.filtered(
            lambda m: m.product_id.id == self.product2.id
        ).move_line_ids

        self.assertRecordValues(
            productlot_mls,
            [
                {
                    "quantity": 1,
                    "picked": True,
                    "trace_id": lot01.id,
                    "location_id": self.stock_location.id,
                },
                {
                    "quantity": 1,
                    "picked": True,
                    "trace_id": lot02.id,
                    "location_id": self.stock_location.id,
                },
                {
                    "quantity": 2,
                    "picked": True,
                    "trace_id": lot02.id,
                    "location_id": self.shelf1.id,
                },
                {
                    "quantity": 1,
                    "picked": True,
                    "trace_id": lot03.id,
                    "location_id": self.shelf2.id,
                },
            ],
        )
        self.assertRecordValues(
            product1_mls,
            [
                {"quantity": 2, "picked": True, "location_id": self.stock_location.id},
                {"quantity": 2, "picked": True, "location_id": self.shelf1.id},
            ],
        )
        self.assertRecordValues(
            product2_mls,
            [
                {"quantity": 2, "picked": True, "location_id": self.stock_location.id},
                {"quantity": 1, "picked": True, "location_id": self.shelf1.id},
            ],
        )

    def test_split_line_on_destination_scan(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        self.picking_type_internal.restrict_scan_dest_location = "mandatory"
        self.picking_type_internal.restrict_scan_source_location = "mandatory"
        receipt = self.env["stock.picking"].create(
            {
                "location_dest_id": self.picking_type_in.default_location_dest_id.id,
                "location_id": self.supplier_location.id,
                "name": "receipt_split_line_on_destination_scan",
                "picking_type_id": self.picking_type_in.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_dest_id": receipt.location_dest_id.id,
                "location_id": receipt.location_id.id,
                "picking_id": receipt.id,
                "product_id": self.product1.id,
                "product_uom_qty": 4,
            }
        )
        receipt.action_confirm()
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf1, 3
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf2, 4
        )
        internal = self.env["stock.picking"].create(
            {
                "location_dest_id": self.stock_location.id,
                "location_id": self.stock_location.id,
                "name": "internal_split_line_on_destination_scan",
                "picking_type_id": self.picking_type_internal.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_dest_id": internal.location_dest_id.id,
                "location_id": internal.location_id.id,
                "picking_id": internal.id,
                "product_id": self.product2.id,
                "product_uom_qty": 7,
            }
        )
        internal.action_confirm()
        self.start_tour(
            "/odoo/barcode", "test_split_line_on_destination_scan", login="admin"
        )
        self.assertRecordValues(
            receipt.move_line_ids,
            [
                {
                    "quantity": 2,
                    "picked": True,
                    "location_dest_id": receipt.location_dest_id.id,
                },
                {"quantity": 2, "picked": True, "location_dest_id": self.shelf1.id},
            ],
        )
        self.assertRecordValues(
            internal.move_line_ids,
            [
                {
                    "quantity": 2,
                    "picked": True,
                    "location_id": self.shelf1.id,
                    "location_dest_id": self.shelf3.id,
                },
                {
                    "quantity": 2,
                    "picked": True,
                    "location_id": self.shelf2.id,
                    "location_dest_id": self.shelf2.id,
                },
                {
                    "quantity": 1,
                    "picked": True,
                    "location_id": self.shelf1.id,
                    "location_dest_id": self.stock_location.id,
                },
                {
                    "quantity": 2,
                    "picked": True,
                    "location_id": self.shelf2.id,
                    "location_dest_id": self.shelf1.id,
                },
            ],
        )

    def test_split_line_on_exit_for_delivery(self):
        product3 = self.env["product.product"].create(
            {
                "name": "product3",
                "is_storable": True,
                "barcode": "product3",
            }
        )
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            [
                {
                    "product_id": product.id,
                    "inventory_quantity": qty,
                    "location_id": self.stock_location.id,
                }
                for product, qty in [
                    (self.product1, 4),
                    (self.product2, 4),
                    (product3, 2),
                ]
            ]
        ).action_apply_inventory()

        delivery = self.env["stock.picking"].create(
            {
                "name": "delivery_split_line_on_exit",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        self.env["stock.move"].create(
            [
                {
                    "location_dest_id": delivery.location_dest_id.id,
                    "location_id": delivery.location_id.id,
                    "picking_id": delivery.id,
                    "product_id": product.id,
                    "product_uom_qty": 4,
                }
                for product in [self.product1, self.product2, product3]
            ]
        )
        delivery.action_confirm()

        self.start_tour(
            "/odoo/barcode", "test_split_line_on_exit_for_delivery", login="admin"
        )
        self.assertRecordValues(
            delivery.move_ids,
            [
                {"product_id": self.product1.id, "quantity": 4, "picked": True},
                {"product_id": self.product2.id, "quantity": 4, "picked": True},
                {"product_id": product3.id, "quantity": 2, "picked": False},
            ],
        )
        self.assertRecordValues(
            delivery.move_line_ids,
            [
                {"product_id": self.product1.id, "quantity": 4, "picked": True},
                {"product_id": self.product2.id, "quantity": 2, "picked": True},
                {"product_id": product3.id, "quantity": 2, "picked": False},
                {"product_id": self.product2.id, "quantity": 2, "picked": False},
            ],
        )

    def test_split_line_on_exit_for_delivery_with_lot(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        lots = self.env["product.trace"].create(
            [
                {"name": "LOT001", "product_id": self.productlot1.id},
                {"name": "LOT002", "product_id": self.productlot1.id},
            ]
        )
        for lot in lots:
            self.env["stock.quant"]._update_available_quantity(
                self.productlot1, self.stock_location, 5, trace_id=lot
            )
        delivery = self.env["stock.picking"].create(
            {
                "name": "delivery_split_move_on_exit",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                            "product_id": self.productlot1.id,
                            "product_uom_qty": 3,
                        }
                    )
                ],
            }
        )
        delivery.action_confirm()
        self.assertRecordValues(
            delivery.move_ids,
            [
                {
                    "product_uom_qty": 3.0,
                    "quantity": 3.0,
                    "picked": False,
                    "trace_ids": lots[0].ids,
                }
            ],
        )
        self.assertRecordValues(
            delivery.move_line_ids,
            [{"quantity": 3.0, "picked": False, "trace_id": lots[0].id}],
        )

        action = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = f"/web#action={action.id}"
        self.start_tour(
            url, "test_split_line_on_exit_for_delivery_with_lot", login="admin"
        )
        self.assertRecordValues(
            delivery.move_line_ids.sorted("quantity"),
            [
                {"quantity": 1, "picked": True, "trace_id": lots[0].id},
                {"quantity": 2, "picked": True, "trace_id": lots[1].id},
            ],
        )

    def test_split_line_on_exit_for_receipt_with_grouped_lot(self):
        grouped_lot_group = self.env.ref("stock.group_production_lot")
        self.env.user.write({"group_ids": [Command.link(grouped_lot_group.id)]})
        receipt = self.env["stock.picking"].create(
            {
                "name": "SPLOEFRWGL",
                "location_id": self.stock_location.id,
                "location_dest_id": self.supplier_location.id,
                "picking_type_id": self.picking_type_in.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.supplier_location.id,
                            "location_dest_id": self.stock_location.id,
                            "product_id": self.productlot1.id,
                            "product_uom_qty": 3,
                        }
                    )
                ],
            }
        )
        receipt.action_confirm()
        self.assertRecordValues(
            receipt.move_ids,
            [{"product_uom_qty": 3.0, "quantity": 3.0, "picked": False}],
        )
        self.start_tour(
            "/odoo/barcode",
            "test_split_line_on_exit_for_receipt_with_grouped_lot",
            login="admin",
        )
        self.assertRecordValues(
            receipt.move_ids,
            [
                {"product_uom_qty": 3.0, "quantity": 3.0, "picked": True},
            ],
        )

    def test_split_line_on_exit_for_receipt(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )
        self._reset_package_sequence(1000)

        receipt = self.env["stock.picking"].create(
            {
                "name": "receipt_split_line_on_exit",
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_dest_id": receipt.location_dest_id.id,
                "location_id": receipt.location_id.id,
                "picking_id": receipt.id,
                "product_id": self.product1.id,
                "product_uom_qty": 4,
            }
        )
        self.env["stock.move"].create(
            {
                "location_dest_id": receipt.location_dest_id.id,
                "location_id": receipt.location_id.id,
                "picking_id": receipt.id,
                "product_id": self.product2.id,
                "product_uom_qty": 4,
            }
        )
        receipt.action_confirm()

        self.start_tour(
            "odoo/barcode/", "test_split_line_on_exit_for_receipt", login="admin"
        )
        self.assertRecordValues(
            receipt.move_ids,
            [
                {"product_id": self.product1.id, "quantity": 4, "picked": True},
                {"product_id": self.product2.id, "quantity": 4, "picked": True},
            ],
        )
        self.assertRecordValues(
            receipt.move_ids.move_line_ids,
            [
                {"product_id": self.product1.id, "quantity": 2, "picked": True},
                {"product_id": self.product1.id, "quantity": 1, "picked": False},
                {"product_id": self.product1.id, "quantity": 1, "picked": True},
                {"product_id": self.product2.id, "quantity": 1, "picked": True},
                {"product_id": self.product2.id, "quantity": 3, "picked": False},
            ],
        )

    def test_editing_done_picking(self):
        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_in
        with picking_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 69

        receipt = picking_form.save()
        receipt.action_confirm()
        receipt.move_ids.quantity = 69
        receipt.button_validate()

        url = self._get_client_action_url(receipt.id)
        self.start_tour(url, "test_editing_done_picking", login="admin", timeout=180)

    def test_sml_sort_order_by_product_category(self):
        product_categoryB = self.env["product.category"].create({"name": "TestB"})
        product_categoryA = self.env["product.category"].create({"name": "TestA"})
        productA = self.env["product.product"].create(
            {"name": "Product A", "categ_id": product_categoryB.id, "is_storable": True}
        )
        productB = self.env["product.product"].create(
            {"name": "Product B", "categ_id": product_categoryA.id, "is_storable": True}
        )
        productC = self.env["product.product"].create(
            {"name": "Product C", "categ_id": product_categoryB.id, "is_storable": True}
        )
        receipt = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        self.env["stock.move.line"].create(
            [
                {
                    "product_id": productA.id,
                    "product_uom_id": productA.uom_id.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.stock_location.id,
                    "qty_done": 1,
                    "picking_id": receipt.id,
                },
                {
                    "product_id": productB.id,
                    "product_uom_id": productB.uom_id.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.stock_location.id,
                    "qty_done": 1,
                    "picking_id": receipt.id,
                },
                {
                    "product_id": productC.id,
                    "product_uom_id": productC.uom_id.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.stock_location.id,
                    "qty_done": 1,
                    "picking_id": receipt.id,
                },
            ]
        )
        url = self._get_client_action_url(receipt.id)
        self.start_tour(
            url, "test_sml_sort_order_by_product_category", login="admin", timeout=180
        )

    def test_create_backorder_after_qty_modified(self):
        receipt = self.env["stock.picking"].create(
            {
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        self.env["stock.move"].create(
            {
                "picking_id": receipt.id,
                "product_id": self.product1.id,
                "product_uom_qty": 2.0,
                "product_uom_id": self.product1.uom_id.id,
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
            }
        )
        receipt.action_confirm()

        url = self._get_client_action_url(receipt.id)
        self.start_tour(
            url, "test_create_backorder_after_qty_modified", login="admin", timeout=180
        )

        backorder = self.env["stock.picking"].search(
            [("backorder_id", "=", receipt.id)]
        )
        self.assertEqual(backorder.move_ids[0].product_uom_qty, 1.0)
        self.assertEqual(receipt.move_ids[0].product_uom_qty, 1.0)

    def test_open_picking_dont_override_assigned_user(self):
        bob = self.env["res.users"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "Bob"}).id,
                "login": "bob",
            }
        )
        receipt_picking = self.env["stock.picking"].create(
            {
                "name": "test_responsible_receipt",
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
                "user_id": bob.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "location_id": self.supplier_location.id,
                            "location_dest_id": self.stock_location.id,
                            "product_id": self.product1.id,
                            "product_uom_id": self.uom_unit.id,
                            "product_uom_qty": 2,
                        },
                    )
                ],
            }
        )
        receipt_picking.action_confirm()
        url = "/odoo/action-stock_barcode.stock_barcode_action_main_menu"
        self.start_tour(
            url, "test_open_picking_dont_override_assigned_user", login="admin"
        )
        self.assertEqual(
            receipt_picking.user_id.id,
            bob.id,
            "Picking responsible should be unchanged after click when previously set",
        )

    def test_multi_company_record_access_in_barcode(self):
        company2 = self.env["res.company"].create({"name": "second company"})
        self.env["stock.picking.type"].search(
            [
                ("code", "=", "incoming"),
                ("company_id", "=", company2.id),
            ],
            limit=1,
        ).barcode = "company2_receipt"
        self.env.user.company_ids = [Command.link(company2.id)]

        self.product1.write(
            {
                "company_id": self.env.company.id,
                "barcode": "company1_product",
            }
        )
        self.product2.write(
            {
                "company_id": company2.id,
                "barcode": "company2_product",
            }
        )

        cids = "-".join(str(cid) for cid in self.env.user.company_ids.ids)
        url = "/odoo/action-stock_barcode.stock_barcode_action_main_menu"
        self.start_tour(
            url,
            "test_multi_company_record_access_in_barcode",
            login="admin",
            timeout=180,
            cookies={"cids": cids},
        )

        self.assertTrue(
            self.env["stock.picking"].search(
                [
                    ("company_id", "=", company2.id),
                    ("product_id", "in", self.product2.ids),
                ],
                limit=1,
            )
        )

    def test_no_zero_demand_new_line_from_split(self):
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 1
        )
        picking = self.env["stock.picking"].create(
            {
                "name": "TNZDNLFS picking",
                "picking_type_id": self.picking_type_internal.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product1.id,
                            "product_uom_qty": 1,
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.stock_location.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()

        url = "/odoo/action-stock_barcode.stock_barcode_action_main_menu"
        self.start_tour(
            url, "test_no_zero_demand_new_line_from_split", login="admin", timeout=180
        )

        self.assertRecordValues(
            picking.move_ids, [{"quantity": 1, "product_uom_qty": 1, "picked": False}]
        )
        self.assertRecordValues(
            picking.move_line_ids, [{"picked": False, "quantity": 1}]
        )

    def test_barcode_pack_lot(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        warehouse = self.picking_type_out.warehouse_id
        warehouse.out_type_id.write(
            {
                "show_reserved_sns": True,
                "restrict_scan_source_location": "no",
            }
        )
        product = self.env["product.product"].create(
            {
                "name": "Lovely product",
                "is_storable": True,
                "tracking": "lot",
                "uom_id": self.uom_unit.id,
            }
        )

        lot_1, lot_2 = self.env["product.trace"].create(
            [
                {"name": "LOT004", "product_id": product.id},
                {"name": "LOT005", "product_id": product.id},
            ]
        )
        self.env["stock.quant"]._update_available_quantity(
            product, warehouse.lot_stock_id, 4, trace_id=lot_1
        )
        self.env["stock.quant"]._update_available_quantity(
            product, warehouse.lot_stock_id, 2, trace_id=lot_2
        )

        delivery = self.env["stock.picking"].create(
            {
                "name": "Lovely delivery",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                            "product_id": product.id,
                            "product_uom_id": product.uom_id.id,
                            "product_uom_qty": 4,
                        }
                    )
                ],
            }
        )
        delivery.action_confirm()
        self.assertEqual(delivery.move_line_ids.trace_id, lot_1)
        url = self._get_client_action_url(delivery.id)
        self.start_tour(url, "test_barcode_pack_lot_tour", login="admin", timeout=180)
        self.assertEqual(delivery.state, "done")
        self.assertRecordValues(
            delivery.move_line_ids,
            [
                {"quantity": 1.0, "trace_id": lot_1.id},
                {"quantity": 1.0, "trace_id": lot_1.id},
                {"quantity": 1.0, "trace_id": lot_2.id},
                {"quantity": 1.0, "trace_id": lot_2.id},
            ],
        )
        self.assertEqual(len(delivery.move_line_ids.result_package_id), 4)

    def test_barcode_picking_return(self):
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 5
        )

        delivery_form = Form(self.env["stock.picking"])
        delivery_form.picking_type_id = self.picking_type_out
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product2
            move.product_uom_qty = 5
        delivery = delivery_form.save()
        delivery.action_confirm()
        delivery.action_assign()
        delivery.button_validate()

        url = self._get_client_action_url(delivery.id)
        self.start_tour(url, "test_barcode_picking_return", login="admin", timeout=180)
        return_picking = delivery.return_ids
        self.assertEqual(return_picking.state, "done")
        self.assertEqual(
            [
                (ml.product_id, ml.quantity, ml.location_dest_id)
                for ml in return_picking.move_line_ids
            ],
            [(self.product1, 1, self.stock_location)],
            "the unreturned product2 line is dropped, the scanned product1 is returned",
        )

    def test_scan_location_destination_for_internal_transfers(self):
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

        location_dest = self.env["stock.location"].create(
            {
                "name": "Lovely Location",
                "location_id": self.stock_location.location_id.id,
                "barcode": "WH-LOVE",
            }
        )
        self.product1.name = "Lovely Product"
        action_id = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = "/web#action=" + str(action_id.id)
        self.start_tour(
            url,
            "test_scan_location_destination_for_internal_transfers",
            login="admin",
            timeout=180,
        )
        internal_transfer = self.env["stock.picking"].search(
            [("picking_type_id", "=", self.picking_type_internal.id)], limit=1
        )
        self.assertRecordValues(
            internal_transfer.move_ids.move_line_ids,
            [
                {
                    "product_id": self.product1.id,
                    "location_dest_id": location_dest.id,
                }
            ],
        )

    def test_scan_product_when_in_form_view(self):
        grp_multi_loc = self.env.ref("stock.group_stock_multi_locations")
        self.env.user.write({"group_ids": [Command.link(grp_multi_loc.id)]})
        self.picking_type_internal.active = True
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf3, 5
        )
        self.start_tour(
            "/odoo/barcode", "test_scan_product_when_in_form_view", login="admin"
        )
        internal = self._last_picking(self.picking_type_internal)
        self.assertEqual(internal.state, "done")
        self.assertEqual(
            [
                (ml.product_id, ml.quantity, ml.location_id)
                for ml in internal.move_line_ids
            ],
            [(self.product1, 5, self.shelf3)],
            "a scan while the line form is open adds nothing",
        )

    def test_split_uncomplete_moves_on_exit(self):
        reference = self.env["stock.reference"].create(
            {
                "name": "custom procurement",
            }
        )
        warehouse = self.picking_type_out.warehouse_id
        mto_product = self.product1
        self.env["stock.quant"]._update_available_quantity(
            mto_product, warehouse.lot_stock_id, 4
        )
        warehouse.delivery_steps = "pick_ship"
        final_destination = self.env.ref("stock.stock_location_customers")
        origin = "custom origin"
        self.env["stock.rule"].run(
            [
                self.env["stock.rule"].Procurement(
                    mto_product,
                    4.0,
                    mto_product.uom_id,
                    final_destination,
                    mto_product.name,
                    origin,
                    self.picking_type_out.company_id,
                    {"warehouse_id": warehouse, "reference_ids": reference},
                )
            ]
        )
        pick = self.env["stock.picking"].search(
            [("reference_ids", "in", reference.ids)], limit=1
        )
        pick.button_validate()
        ship = (
            self.env["stock.picking"].search(
                [("reference_ids", "in", reference.ids)], limit=2
            )
            - pick
        )
        mts_product = self.product2
        self.env["stock.quant"]._update_available_quantity(
            mts_product, ship.location_id, 5
        )
        self.env["stock.move"].create(
            {
                "product_id": mts_product.id,
                "product_uom_qty": 5,
                "product_uom_id": mts_product.uom_id.id,
                "picking_id": ship.id,
                "location_id": ship.location_id.id,
                "location_dest_id": ship.location_dest_id.id,
            }
        )
        ship.action_assign()
        self.assertRecordValues(
            ship.move_ids.sorted("quantity"),
            [
                {"quantity": 4.0, "picked": False, "procure_method": "make_to_order"},
                {"quantity": 5.0, "picked": False, "procure_method": "make_to_stock"},
            ],
        )
        url = self._get_client_action_url(ship.id)
        self.start_tour(
            url, "test_split_uncomplete_moves_on_exit", login="admin", timeout=180
        )
        self.assertRecordValues(
            ship.move_ids.sorted("quantity"),
            [
                {"product_id": mto_product.id, "quantity": 4.0, "picked": True},
                {"product_id": mts_product.id, "quantity": 5.0, "picked": True},
            ],
        )
        self.assertRecordValues(
            ship.move_line_ids.filtered(lambda m: m.product_id == mto_product).sorted(
                "quantity"
            ),
            [
                {"quantity": 1.0, "picked": True},
                {"quantity": 3.0, "picked": False},
            ],
        )
        self.assertRecordValues(
            ship.move_line_ids.filtered(lambda m: m.product_id == mts_product).sorted(
                "quantity"
            ),
            [
                {"quantity": 1.0, "picked": True},
                {"quantity": 4.0, "picked": False},
            ],
        )

    def test_split_uncomplete_manually_assigned_moves_on_exit(self):
        grp_multi_loc = self.env.ref("stock.group_stock_multi_locations")
        self.env.user.write({"group_ids": [Command.link(grp_multi_loc.id)]})
        self.picking_type_out.write(
            {
                "reservation_method": "manual",
                "restrict_scan_source_location": "no",
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 5
        )
        delivery = self.env["stock.picking"].create(
            {
                "name": "SUMAMOE",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                            "product_id": self.product1.id,
                            "product_uom_id": self.product1.uom_id.id,
                            "product_uom_qty": 3,
                        }
                    )
                ],
            }
        )
        delivery.action_confirm()
        delivery.action_assign()
        url = self._get_client_action_url(delivery.id)
        self.start_tour(
            url, "test_split_uncomplete_manually_assigned_moves_on_exit", login="admin"
        )
        self.assertRecordValues(
            delivery.move_ids,
            [
                {"quantity": 3.0, "picked": True},
            ],
        )
        self.assertRecordValues(
            delivery.move_line_ids.sorted("quantity"),
            [
                {"quantity": 1.0, "picked": True},
                {"quantity": 2.0, "picked": False},
            ],
        )

    def test_split_uncomplete_moves_on_exit_with_neutral_changes(self):

        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.picking_type_out.show_reserved_sns = True

        lots = self.env["product.trace"].create(
            [
                {"name": "LN001", "product_id": self.productlot1.id},
                {"name": "LN002", "product_id": self.productlot1.id},
            ]
        )
        for lot in lots:
            self.env["stock.quant"]._update_available_quantity(
                self.productlot1, self.stock_location, 2, trace_id=lot
            )
        delivery = self.env["stock.picking"].create(
            {
                "name": "SUMOEWNC",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                            "product_id": self.productlot1.id,
                            "product_uom_qty": 4,
                        }
                    )
                ],
            }
        )
        delivery.action_confirm()
        self.assertRecordValues(
            delivery.move_ids,
            [
                {
                    "product_uom_qty": 4.0,
                    "quantity": 4.0,
                    "picked": False,
                    "trace_ids": lots.ids,
                },
            ],
        )
        self.assertRecordValues(
            delivery.move_line_ids,
            [
                {"quantity": 2.0, "picked": False, "trace_id": lots[0].id},
                {"quantity": 2.0, "picked": False, "trace_id": lots[1].id},
            ],
        )

        action = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = f"/web#action={action.id}"
        self.start_tour(
            url,
            "test_split_uncomplete_moves_on_exit_with_neutral_changes",
            login="admin",
        )
        self.assertRecordValues(
            delivery.move_ids,
            [
                {
                    "product_uom_qty": 4.0,
                    "quantity": 4.0,
                    "picked": False,
                    "trace_ids": lots.ids,
                },
            ],
        )
        self.assertRecordValues(
            delivery.move_line_ids,
            [
                {"quantity": 2.0, "picked": False, "trace_id": lots[1].id},
                {"quantity": 2.0, "picked": False, "trace_id": lots[0].id},
            ],
        )

    def test_barcode_create_serials_in_batch_with_single_scan(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        self.picking_type_out.write(
            {
                "show_reserved_sns": True,
                "restrict_scan_source_location": "no",
                "use_create_lots": True,
            }
        )

        self1 = self
        get_specific_barcode_data_orig = (
            StockBarcodeController.get_specific_barcode_data
        )

        @http.route(
            "/stock_barcode/get_specific_barcode_data", type="jsonrpc", auth="user"
        )
        def mocked_data_batch_method(self, **kwargs):
            if self1.call_count == 0:
                self1.assertTrue("barcodes_by_model" in kwargs)
                self1.assertFalse("barcodes" in kwargs)
            elif self1.call_count == 1:
                self1.assertFalse("barcodes_by_model" in kwargs)
                self1.assertTrue("barcodes" in kwargs)
            self1.call_count += 1
            return get_specific_barcode_data_orig(self, **kwargs)

        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 1500
        )
        delivery = self.env["stock.picking"].create(
            {
                "name": "Lovely delivery",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                            "product_id": self.productlot1.id,
                            "product_uom_id": self.productlot1.uom_id.id,
                            "product_uom_qty": 1000,
                        }
                    )
                ],
            }
        )
        delivery.action_confirm()
        self.assertFalse(delivery.move_line_ids.trace_id)
        url = self._get_client_action_url(delivery.id)
        with patch.object(
            StockBarcodeController,
            "get_specific_barcode_data",
            mocked_data_batch_method,
        ):
            self.start_tour(
                url,
                "test_barcode_create_serials_in_batch_with_single_scan",
                login="admin",
            )
            self.assertEqual(self.call_count, 2)

    def test_quant_selection_delivery_picking(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )
        package = self.env["stock.package"].create({"name": "package001"})

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 10, package_id=package
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 2
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 10
        )

        delivery_picking = self.env["stock.picking"].create(
            {
                "name": "Delivery with Stock Move",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                            "product_id": self.product1.id,
                            "product_uom_id": self.uom_unit.id,
                            "product_uom_qty": 2,
                        }
                    )
                ],
            }
        )
        delivery_picking.action_confirm()
        delivery_picking.action_assign()

        url = self._get_client_action_url(delivery_picking.id)
        self.start_tour(
            url, "test_quant_selection_delivery_picking", login="admin", timeout=180
        )
        self.assertRecordValues(
            delivery_picking.move_ids.move_line_ids,
            [
                {
                    "product_id": self.product1.id,
                    "qty_done": 2,
                    "location_id": self.stock_location.id,
                    "trace_id": False,
                    "package_id": package.id,
                    "state": "done",
                }
            ],
        )

    def test_confirmation_location_delivery_picking(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )
        package = self.env["stock.package"].create({"name": "package001"})

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 10, package_id=package
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 5
        )

        delivery_picking = self.env["stock.picking"].create(
            {
                "name": "Delivery with Stock Move",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                            "product_id": self.product1.id,
                            "product_uom_id": self.uom_unit.id,
                            "product_uom_qty": 1,
                        }
                    )
                ],
            }
        )
        delivery_picking.action_confirm()
        delivery_picking.action_assign()

        url = self._get_client_action_url(delivery_picking.id)
        self.start_tour(
            url,
            "test_confirmation_location_delivery_picking",
            login="admin",
            timeout=180,
        )
        self.assertRecordValues(
            delivery_picking.move_ids.move_line_ids,
            [
                {
                    "product_id": self.product1.id,
                    "qty_done": 1,
                    "location_id": self.shelf2.id,
                    "trace_id": False,
                    "package_id": package.id,
                    "state": "done",
                }
            ],
        )

    def test_barcode_lazy_cache_scan_two_lots(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_tracking_owner").id),
                ]
            }
        )
        self.picking_type_in.write({"use_existing_lots": True})

        sn1, _ = self.env["product.trace"].create(
            [
                {"name": "SN-001", "product_id": self.productlot1.id},
                {"name": "SN-002", "product_id": self.productlot1.id},
            ]
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 1, trace_id=sn1
        )

        receipt = self.env["stock.picking"].create(
            {
                "name": "Lovely Receipt",
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.supplier_location.id,
                            "location_dest_id": self.stock_location.id,
                            "product_id": self.productlot1.id,
                            "product_uom_id": self.productlot1.uom_id.id,
                            "product_uom_qty": 10,
                        }
                    )
                ],
            }
        )
        receipt.action_confirm()
        url = self._get_client_action_url(receipt.id)
        self.start_tour(url, "test_barcode_lazy_cache_scan_two_lots", login="admin")

    def test_fetch_archived_records_in_lazy_barcode_cache(self):
        warehouse = self.shelf2.warehouse_id
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 10
        )
        floor_location = self.env["stock.location"].create(
            {
                "name": "floor1",
                "usage": "internal",
                "location_id": self.shelf2.id,
            }
        )
        transfer = self.env["stock.picking"].create(
            {
                "name": "Lovely Transfer",
                "location_id": self.shelf1.id,
                "location_dest_id": self.shelf2.id,
                "picking_type_id": warehouse.int_type_id.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.shelf1.id,
                            "location_dest_id": floor_location.id,
                            "product_id": self.product1.id,
                            "product_uom_qty": 3,
                        }
                    )
                ],
            }
        )
        transfer.action_confirm()
        self.shelf2.action_archive()
        self.assertFalse(self.shelf2.active)
        url = self._get_client_action_url(transfer.id)
        self.start_tour(
            url, "test_fetch_archived_records_in_lazy_barcode_cache", login="admin"
        )
        self.assertEqual(transfer.state, "done")

    def test_validate_uncomplete_return(self):
        self.env["stock.picking"].create(
            {
                "name": "TEST/IN/0001",
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.supplier_location.id,
                            "location_dest_id": self.stock_location.id,
                            "product_id": self.product1.id,
                            "product_uom_id": self.product1.uom_id.id,
                            "product_uom_qty": 2,
                        }
                    )
                ],
            }
        ).action_confirm()
        self.start_tour(
            "/odoo/barcode", "test_validate_uncomplete_return", login="admin"
        )
        receipt = self.env["stock.picking"].search([("name", "=", "TEST/IN/0001")])
        return_picking = receipt.return_ids
        self.assertEqual(return_picking.state, "done")
        self.assertEqual(return_picking.move_line_ids.mapped("quantity"), [1])
        self.assertFalse(
            self.env["stock.picking"].search([("backorder_id", "=", return_picking.id)])
        )

    def test_scan_package_with_different_uom(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.ref("stock.group_tracking_lot")),
                    Command.link(self.ref("base.group_uom")),
                ]
            }
        )
        uom_kg = self.env.ref("base.product_uom_kgm")
        uom_g = self.env.ref("base.product_uom_gram")
        self.product1.uom_id = uom_kg
        self.product2.uom_id = uom_g
        package1, package2 = self.env["stock.package"].create(
            [
                {"name": "package001"},
                {"name": "package002"},
            ]
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 10, package_id=package1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 10000, package_id=package2
        )
        picking = self.env["stock.picking"].create(
            {
                "name": "test picking",
                "picking_type_id": self.picking_type_out.id,
                "location_id": self.picking_type_out.default_location_src_id.id,
                "location_dest_id": self.picking_type_out.default_location_dest_id.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_uom_id": uom.id,
                            "product_uom_qty": qty,
                            "location_id": self.picking_type_out.default_location_src_id.id,
                            "location_dest_id": self.picking_type_out.default_location_dest_id.id,
                        }
                    )
                    for (product, qty, uom) in [
                        (self.product1, 10000, uom_g),
                        (self.product2, 8, uom_kg),
                    ]
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        url = self._get_client_action_url(picking.id)
        self.start_tour(url, "test_scan_package_with_different_uom", login="admin")

    def test_scan_packaging_on_picking_with_mixed_uom(self):
        self.env.user.write({"group_ids": [Command.link(self.ref("base.group_uom"))]})
        self.uom_dozen.action_unarchive()
        unit, pack_of_6 = (
            self.ref("base.product_uom_unit"),
            self.ref("base.product_uom_pack_6"),
        )
        lovely_product = self.env["product.product"].create(
            {
                "name": "Lovely product",
                "is_storable": True,
                "barcode": "love",
                "uom_id": self.ref("base.product_uom_unit"),
                "uom_ids": [Command.link(pack_of_6), Command.link(self.uom_dozen.id)],
                "product_uom_ids": [
                    Command.create(
                        {
                            "uom_id": pack_of_6,
                            "barcode": "6love",
                        }
                    ),
                    Command.create(
                        {
                            "uom_id": self.uom_dozen.id,
                            "barcode": "12love",
                        }
                    ),
                ],
            }
        )
        receipt_1, receipt_2, receipt_3 = self.env["stock.picking"].create(
            [
                {
                    "name": "SPOPWMU1",
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "picking_type_id": self.picking_type_in.id,
                    "move_ids": [
                        Command.create(
                            {
                                "location_id": self.supplier_location.id,
                                "location_dest_id": self.stock_location.id,
                                "product_id": lovely_product.id,
                                "product_uom_qty": 2,
                                "product_uom_id": pack_of_6,
                            }
                        ),
                    ],
                },
                {
                    "name": "SPOPWMU2",
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "picking_type_id": self.picking_type_in.id,
                    "move_ids": [
                        Command.create(
                            {
                                "location_id": self.supplier_location.id,
                                "location_dest_id": self.stock_location.id,
                                "product_id": lovely_product.id,
                                "product_uom_qty": 12,
                            }
                        )
                    ],
                },
                {
                    "name": "SPOPWMU3",
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "picking_type_id": self.picking_type_in.id,
                    "move_ids": [
                        Command.create(
                            {
                                "location_id": self.supplier_location.id,
                                "location_dest_id": self.stock_location.id,
                                "product_id": lovely_product.id,
                                "product_uom_qty": 10,
                            }
                        ),
                        Command.create(
                            {
                                "location_id": self.supplier_location.id,
                                "location_dest_id": self.stock_location.id,
                                "product_id": lovely_product.id,
                                "product_uom_qty": 1,
                                "product_uom_id": pack_of_6,
                            }
                        ),
                    ],
                },
            ]
        )
        receipt_2.move_ids.packaging_uom_id = pack_of_6
        (receipt_1 | receipt_2 | receipt_3).action_confirm()
        self.assertRecordValues(
            receipt_1.move_ids,
            [
                {
                    "product_uom_qty": 2.0,
                    "quantity": 2.0,
                    "picked": False,
                    "product_uom_id": pack_of_6,
                }
            ],
        )
        self.assertRecordValues(
            receipt_2.move_ids,
            [
                {
                    "product_uom_qty": 12.0,
                    "quantity": 12.0,
                    "picked": False,
                    "quantity_packaging_uom": 2,
                    "packaging_uom_id": pack_of_6,
                }
            ],
        )
        self.assertRecordValues(
            receipt_3.move_ids,
            [
                {
                    "product_uom_qty": 10.0,
                    "quantity": 10.0,
                    "product_uom_id": unit,
                    "picked": False,
                },
                {
                    "product_uom_qty": 1.0,
                    "quantity": 1.0,
                    "product_uom_id": pack_of_6,
                    "picked": False,
                },
            ],
        )

        action = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = f"/web#action={action.id}"
        self.start_tour(
            url, "test_scan_packaging_on_picking_with_mixed_uom", login="admin"
        )
        self.assertRecordValues(
            receipt_1.move_ids,
            [
                {
                    "product_uom_qty": 2.0,
                    "quantity": 2,
                    "product_uom_id": pack_of_6,
                    "state": "done",
                },
            ],
        )
        self.assertRecordValues(
            receipt_2.move_ids,
            [
                {
                    "product_uom_qty": 12.0,
                    "quantity": 32.0,
                    "product_uom_id": unit,
                    "packaging_uom_id": pack_of_6,
                    "state": "done",
                }
            ],
        )
        self.assertRecordValues(
            receipt_3.move_ids,
            [
                {
                    "product_uom_qty": 10.0,
                    "quantity": 25.0,
                    "product_uom_id": unit,
                    "state": "done",
                },
                {
                    "product_uom_qty": 1.0,
                    "quantity": 1.0,
                    "product_uom_id": pack_of_6,
                    "state": "done",
                },
            ],
        )

    def test_remove_sublines_and_scan_serial_again(self):
        grp_lot = self.env.ref("stock.group_production_lot")
        self.env.user.write({"group_ids": [Command.link(grp_lot.id)]})
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_in.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.productserial1.id,
                            "product_uom_qty": 3,
                        }
                    )
                ],
            }
        )
        picking.action_assign()
        url = self._get_client_action_url(picking.id)
        self.start_tour(
            url, "test_remove_sublines_and_scan_serial_again", login="admin"
        )
        self.assertEqual(picking.state, "done")
        self.assertEqual(
            sorted(ml.trace_id.name for ml in picking.move_line_ids),
            ["abc1", "abc2", "abc3"],
        )

    def test_split_line_preserve_package(self):
        grp_pack = self.env.ref("stock.group_tracking_lot")
        grp_multi_loc = self.env.ref("stock.group_stock_multi_locations")
        self.env.user.write(
            {"group_ids": [Command.link(grp_pack.id), Command.link(grp_multi_loc.id)]}
        )
        self.picking_type_out.restrict_scan_source_location = "no"

        pack1, pack2 = self.env["stock.package"].create(
            [
                {
                    "name": name,
                }
                for name in ["THEPACK1", "THEPACK2"]
            ]
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, quantity=100, package_id=pack1
        )
        delivery_form = Form(self.env["stock.picking"])
        delivery_form.picking_type_id = self.picking_type_out
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 50
        delivery_with_move = delivery_form.save()
        delivery_with_move.action_confirm()
        delivery_with_move.action_assign()
        url = self._get_client_action_url(delivery_with_move.id)
        self.start_tour(url, "test_split_line_preserve_package", login="admin")
        self.assertEqual(delivery_with_move.move_line_ids[0].package_id, pack1)
        self.assertEqual(delivery_with_move.move_line_ids[1].result_package_id, pack2)
        self.assertEqual(delivery_with_move.move_line_ids[1].package_id, pack1)

    def test_gs1_delivery_ambiguous_lot_number(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("base.group_uom").id)]}
        )
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        product_a, product_b = self.env["product.product"].create(
            [
                {
                    "name": name,
                    "is_storable": True,
                    "barcode": barcode,
                    "tracking": "lot",
                }
                for (name, barcode) in [
                    ("Product A", "22222220"),
                    ("Product B", "44444440"),
                ]
            ]
        )
        lot_b, lot_a = self.env["product.trace"].create(
            [
                {"name": "12345", "product_id": product.id}
                for product in [product_b, product_a]
            ]
        )
        packaging = self.env["uom.uom"].create(
            {
                "name": "Packaging - Product A x1",
                "relative_factor": 1,
                "relative_uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )
        product_a.uom_ids = packaging
        self.env["product.uom"].create(
            {
                "product_id": product_a.id,
                "uom_id": packaging.id,
                "barcode": "10000000240489",
            }
        )
        for [product, lot] in [[product_b, lot_b], [product_a, lot_a]]:
            self.env["stock.quant"].with_context(inventory_mode=True).create(
                {
                    "product_id": product.id,
                    "inventory_quantity": 1,
                    "trace_id": lot.id,
                    "location_id": self.stock_location.id,
                }
            ).action_apply_inventory()
        self.start_tour(
            "/odoo/barcode",
            "test_gs1_delivery_ambiguous_lot_number",
            login="admin",
            timeout=180,
        )
        self.assertEqual(self._last_picking(self.picking_type_out).state, "cancel")
        receipt = self._last_picking(self.picking_type_in)
        self.assertEqual(receipt.state, "done")
        self.assertEqual(
            receipt.move_line_ids.trace_id,
            lot_a,
            "product B's homonym lot was not taken",
        )

    def test_gs1_delivery_ambiguous_serial_number(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        product_a, product_b = self.env["product.product"].create(
            [
                {
                    "name": f"product{i}",
                    "is_storable": True,
                    "barcode": barcode,
                    "tracking": "serial",
                }
                for i, barcode in enumerate(["05711544001952", "05711544001969"])
            ]
        )
        lot_b, lot_a = self.env["product.trace"].create(
            [
                {"name": "304", "product_id": product.id}
                for product in [product_b, product_a]
            ]
        )
        for [product, lot] in [[product_b, lot_b], [product_a, lot_a]]:
            self.env["stock.quant"].with_context(inventory_mode=True).create(
                {
                    "product_id": product.id,
                    "inventory_quantity": 1,
                    "trace_id": lot.id,
                    "location_id": self.stock_location.id,
                }
            ).action_apply_inventory()
        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": product_a.id,
                "product_uom_qty": 1,
                "product_uom_id": product_a.uom_id.id,
                "picking_id": delivery_picking.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
            }
        )
        delivery_picking.action_confirm()
        delivery_picking.action_assign()
        url = self._get_client_action_url(delivery_picking.id)
        self.start_tour(
            url, "test_gs1_delivery_ambiguous_serial_number", login="admin", timeout=180
        )
        self.assertEqual(delivery_picking.move_line_ids.trace_id, lot_a)
        self.assertEqual(delivery_picking.move_line_ids.product_id, product_a)

    def test_gs1_reserved_delivery(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )

        product_gtin_8 = self.env["product.product"].create(
            {
                "name": "PRO_GTIN_8",
                "is_storable": True,
                "barcode": "11011019",
                "uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            product_gtin_8, self.stock_location, 99
        )

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_out
        with picking_form.move_ids.new() as move:
            move.product_id = product_gtin_8
            move.product_uom_qty = 10

        delivery = picking_form.save()
        delivery.action_confirm()
        delivery.action_assign()

        url = self._get_client_action_url(delivery.id)
        self.start_tour(url, "test_gs1_reserved_delivery", login="admin", timeout=180)

        self.assertEqual(delivery.state, "done")
        self.assertEqual(len(delivery.move_ids), 1)
        self.assertEqual(delivery.move_ids.product_uom_qty, 10, "10 units was reserved")
        self.assertEqual(delivery.move_ids.quantity, 14, "14 units was processed")
        self.assertEqual(len(delivery.move_line_ids), 2)
        self.assertEqual(delivery.move_line_ids[0].quantity, 10)
        self.assertEqual(delivery.move_line_ids[1].quantity, 4)

    def test_gs1_receipt_conflicting_barcodes(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )

        product_gtin_8 = self.env["product.product"].create(
            {
                "name": "PRO_GTIN_8",
                "is_storable": True,
                "barcode": "11011019",
                "uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )

        product_gtin_12 = self.env["product.product"].create(
            {
                "name": "PRO_GTIN_12",
                "is_storable": True,
                "barcode": "000011011019",
                "uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_in
        with picking_form.move_ids.new() as move:
            move.product_id = product_gtin_8
            move.product_uom_qty = 1

        receipt_1 = picking_form.save()
        receipt_1.action_confirm()
        receipt_1.action_assign()

        url = self._get_client_action_url(receipt_1.id)
        self.start_tour(
            url, "test_gs1_receipt_conflicting_barcodes_1", login="admin", timeout=180
        )

        self.assertEqual(receipt_1.state, "done")
        self.assertEqual(len(receipt_1.move_line_ids), 1)
        self.assertEqual(receipt_1.move_line_ids.product_id.id, product_gtin_8.id)

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_in
        with picking_form.move_ids.new() as move:
            move.product_id = product_gtin_12
            move.product_uom_qty = 1

        receipt_2 = picking_form.save()
        receipt_2.action_confirm()
        receipt_2.action_assign()

        url = self._get_client_action_url(receipt_2.id)
        self.start_tour(
            url, "test_gs1_receipt_conflicting_barcodes_2", login="admin", timeout=180
        )

        self.assertEqual(receipt_2.state, "done")
        self.assertEqual(len(receipt_2.move_line_ids), 1)
        self.assertEqual(receipt_2.move_line_ids.product_id.id, product_gtin_12.id)

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_in
        with picking_form.move_ids.new() as move:
            move.product_id = product_gtin_8
            move.product_uom_qty = 1
        with picking_form.move_ids.new() as move:
            move.product_id = product_gtin_12
            move.product_uom_qty = 1

        receipt_3 = picking_form.save()
        receipt_3.action_confirm()
        receipt_3.action_assign()

        self.assertEqual(len(receipt_3.move_line_ids), 2)
        url = self._get_client_action_url(receipt_3.id)
        self.start_tour(
            url, "test_gs1_receipt_conflicting_barcodes_3", login="admin", timeout=180
        )

        self.assertEqual(receipt_3.state, "done")
        self.assertEqual(len(receipt_3.move_line_ids), 3)
        self.assertEqual(receipt_3.move_line_ids[0].product_id.id, product_gtin_8.id)
        self.assertEqual(receipt_3.move_line_ids[0].qty_done, 1)
        self.assertEqual(receipt_3.move_line_ids[1].product_id.id, product_gtin_12.id)
        self.assertEqual(receipt_3.move_line_ids[1].qty_done, 1)
        self.assertEqual(receipt_3.move_line_ids[2].product_id.id, product_gtin_8.id)
        self.assertEqual(receipt_3.move_line_ids[2].qty_done, 1)

    def test_gs1_receipt_conflicting_barcodes_mistaken_as_gs1(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        self.env["product.product"].create(
            {
                "name": "Product AI 21",
                "is_storable": True,
                "barcode": "21000000000003",
                "uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )
        self.env["product.product"].create(
            {
                "name": "Product AI 30",
                "is_storable": True,
                "barcode": "3000000015",
                "uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )
        self.env["stock.package"].create({"name": "21-Chouette-MegaPack"})
        self.start_tour(
            "/odoo/barcode",
            "test_gs1_receipt_conflicting_barcodes_mistaken_as_gs1",
            login="admin",
            timeout=180,
        )

    def test_gs1_receipt_lot_serial(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_in
        with picking_form.move_ids.new() as move:
            move.product_id = self.product_tln_gtn8
            move.product_uom_qty = 40

        receipt = picking_form.save()
        receipt.action_confirm()
        receipt.action_assign()

        url = self._get_client_action_url(receipt.id)
        self.start_tour(url, "test_gs1_receipt_lot_serial", login="admin", timeout=180)

        self.assertEqual(receipt.state, "done")
        self.assertEqual(len(receipt.move_line_ids), 5)
        self.assertEqual(
            receipt.move_line_ids.trace_id.mapped("name"),
            ["b1-b001", "b1-b002", "b1-b003", "b1-b004", "b1-b005"],
        )
        for move_line in receipt.move_line_ids:
            self.assertEqual(move_line.quantity, 8)
            self.assertTrue(move_line.picked)

    def test_gs1_receipt_quantity_with_uom(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("base.group_uom").id)]}
        )
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        uom_g = self.env.ref("base.product_uom_gram")
        uom_kg = self.env.ref("base.product_uom_kgm")
        uom_unit = self.env["uom.uom"].create(
            {
                "name": "Units",
                "relative_factor": 1.0,
                "relative_uom_id": uom_kg.id,
            }
        )
        self.env["barcode.rule"].search(
            [("sequence", "=", 305)]
        ).associated_uom_id = uom_unit
        product_by_units = self.env["product.product"].create(
            {
                "name": "Product by Units",
                "is_storable": True,
                "barcode": "15264329",
                "uom_id": uom_unit.id,
            }
        )
        product_by_g = self.env["product.product"].create(
            {
                "name": "Product by g",
                "is_storable": True,
                "barcode": "15264893",
                "uom_id": uom_g.id,
            }
        )
        product_by_kg = self.env["product.product"].create(
            {
                "name": "Product by kg",
                "is_storable": True,
                "barcode": "15264879",
                "uom_id": uom_kg.id,
            }
        )
        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_in
        receipt = picking_form.save()
        url = self._get_client_action_url(receipt.id)
        self.start_tour(
            url, "test_gs1_receipt_quantity_with_uom", login="admin", timeout=180
        )
        self.assertRecordValues(
            receipt.move_ids,
            [
                {
                    "picked": True,
                    "product_id": product_by_units.id,
                    "product_uom_id": uom_kg.id,
                    "quantity": 14,
                },
                {
                    "picked": True,
                    "product_id": product_by_kg.id,
                    "product_uom_id": uom_kg.id,
                    "quantity": 11,
                },
                {
                    "picked": True,
                    "product_id": product_by_g.id,
                    "product_uom_id": uom_kg.id,
                    "quantity": 1.25,
                },
            ],
        )

    def test_gs1_receipt_scan_not_gs1_multi_barcode(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        self.start_tour(
            "/odoo/barcode",
            "test_gs1_receipt_scan_not_gs1_multi_barcode",
            login="admin",
        )
        receipt = self._last_picking(self.picking_type_in)
        self.assertEqual(receipt.state, "done")
        self.assertEqual(
            sorted(ml.trace_id.name for ml in receipt.move_line_ids),
            [f"sn{i}" for i in range(1, 9)],
        )

    def test_gs1_package_receipt_and_delivery(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )

        self._reset_package_sequence(123)

        product1, product2 = self.env["product.product"].create(
            [
                {
                    "name": "PRO_GTIN_8",
                    "is_storable": True,
                    "barcode": "82655853",
                    "uom_id": self.env.ref("base.product_uom_unit").id,
                },
                {
                    "name": "PRO_GTIN_12",
                    "is_storable": True,
                    "barcode": "584687955629",
                    "uom_id": self.env.ref("base.product_uom_unit").id,
                },
            ]
        )
        wooden_chest_package_type, iron_chest_package_type = self.env[
            "stock.package.type"
        ].create(
            [
                {
                    "name": "Wooden Chest",
                    "barcode": "WOODC",
                },
                {
                    "name": "Iron Chest",
                    "barcode": "IRONC",
                },
            ]
        )

        self.start_tour("/odoo/barcode", "test_gs1_package_receipt", login="admin")
        package = self.env["stock.package"].search(
            [("name", "=", "546879213579461324")]
        )
        package2 = self.env["stock.package"].search(
            [("name", "=", "130406658041178543")]
        )
        package3 = self.env["stock.package"].search([("name", "=", "PACK0000123")])
        self.assertEqual(len(package), 1)
        self.assertEqual(len(package.quant_ids), 2)
        self.assertEqual(package.package_type_id.id, wooden_chest_package_type.id)
        self.assertEqual(package.quant_ids[0].product_id.id, product1.id)
        self.assertEqual(package.quant_ids[1].product_id.id, product2.id)
        self.assertEqual(package.location_id.id, self.stock_location.id)
        self.assertEqual(package2.package_type_id.id, iron_chest_package_type.id)
        self.assertEqual(package2.quant_ids.product_id.id, product1.id)
        self.assertEqual(package3.package_type_id.id, iron_chest_package_type.id)
        self.assertEqual(package3.quant_ids.product_id.id, product2.id)

        self.start_tour("/odoo/barcode", "test_gs1_package_delivery", login="admin")
        self.assertEqual(package.location_id.id, self.customer_location.id)

    def test_gs1_receipt_packaging(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("base.group_uom").id)]}
        )
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )

        product = self.env["product.product"].create(
            {
                "name": "Bottle",
                "is_storable": True,
                "barcode": "1113",
                "uom_ids": [Command.link(self.env.ref("base.product_uom_dozen").id)],
                "product_uom_ids": [
                    Command.create(
                        {
                            "uom_id": self.env.ref("base.product_uom_dozen").id,
                            "barcode": "2226",
                        }
                    )
                ],
            }
        )

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_in
        receipt = picking_form.save()

        url = self._get_client_action_url(receipt.id)
        self.start_tour(url, "test_gs1_receipt_packaging", login="admin", timeout=180)

        move = receipt.move_ids
        self.assertEqual(move.product_id, product)
        self.assertEqual(move.quantity, 5)
        self.assertEqual(move.picked, True)

    def test_gs1_tracked_packaging(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("base.group_uom").id),
                ],
            }
        )
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )

        self.productlot1.uom_ids = self.env.ref("base.product_uom_dozen")
        self.env["product.uom"].create(
            {
                "barcode": "12653256",
                "product_id": self.productlot1.id,
                "uom_id": self.env.ref("base.product_uom_dozen").id,
            }
        )

        self.start_tour(
            "/odoo/barcode", "test_gs1_tracked_packaging", login="admin", timeout=180
        )
        lot = self.env["product.trace"].search([("name", "=", "lot-001")])
        move_lines = self.env["stock.move.line"].search(
            [("product_id", "=", self.productlot1.id)]
        )
        self.assertRecordValues(
            move_lines,
            [
                {
                    "quantity": 1,
                    "trace_id": lot.id,
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                },
                {
                    "quantity": 1,
                    "trace_id": lot.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.customer_location.id,
                },
            ],
        )

    def test_serial_product_packaging(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("base.group_uom").id),
                ],
            }
        )
        pack_4 = self.env["uom.uom"].create(
            {
                "name": "Pack of 4",
                "relative_factor": 4,
                "relative_uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )
        self.productserial1.uom_ids = pack_4
        self.env["product.uom"].create(
            {
                "uom_id": pack_4.id,
                "product_id": self.productserial1.id,
                "barcode": "PCK4",
            }
        )

        self.start_tour(
            "/odoo/barcode", "test_serial_product_packaging", login="admin", timeout=180
        )

    def test_split_line_on_scan(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 5
        )
        pack1 = self.env["stock.package"].create(
            {
                "name": "THEPACK1",
            }
        )
        pack2 = self.env["stock.package"].create(
            {
                "name": "THEPACK2",
            }
        )

        delivery_form = Form(self.env["stock.picking"])
        delivery_form.picking_type_id = self.picking_type_out
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product2
            move.product_uom_qty = 5
        delivery_with_move = delivery_form.save()
        delivery_with_move.action_confirm()
        delivery_with_move.action_assign()

        url = self._get_client_action_url(delivery_with_move.id)
        self.start_tour(url, "test_split_line_on_scan", login="admin", timeout=180)

        self.assertEqual(len(pack1.quant_ids), 1)
        self.assertEqual(len(pack2.quant_ids), 1)
        self.assertEqual(len(delivery_with_move.move_line_ids), 2)

    def test_barcode_signature_flow(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_sign_delivery").id)
                ]
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 5
        )

        partner = self.env["res.partner"].create({"name": "My partner"})

        def create_delivery_picking(picking_name):
            delivery = self.env["stock.picking"].create(
                {
                    "name": picking_name,
                    "picking_type_id": self.picking_type_out.id,
                    "location_id": self.stock_location.id,
                    "location_dest_id": self.customer_location.id,
                    "partner_id": partner.id,
                    "user_id": False,
                    "move_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product1.id,
                                "product_uom_id": self.product1.uom_id.id,
                                "product_uom_qty": 1,
                                "procure_method": "make_to_stock",
                                "location_id": self.stock_location.id,
                                "location_dest_id": self.customer_location.id,
                            },
                        )
                    ],
                }
            )
            delivery.action_confirm()
            delivery.action_assign()
            return delivery

        delivery1 = create_delivery_picking("Delivery Order 1")
        delivery2 = create_delivery_picking("Delivery Order 2")

        self.assertFalse(delivery2.signature)

        url = "/odoo/action-stock_barcode.stock_picking_type_action_kanban"
        self.start_tour(url, "test_barcode_signature_flow", login="admin")

        self.assertTrue(delivery2.signature)
        self.assertEqual(delivery1.state, "done")
        self.assertEqual(delivery2.state, "done")

    def test_select_with_same_product_and_lot(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        ref = self.env["stock.reference"].create({"name": "ProcurementGroup"})
        lot_xyz = self.env["product.trace"].create(
            {
                "name": "lot_xyz",
                "product_id": self.productlot1.id,
                "company_id": self.env.company.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 4, trace_id=lot_xyz
        )
        self.picking_type_out.show_reserved_sns = True
        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.productlot1.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 2,
                "picking_id": delivery_picking.id,
                "reference_ids": ref.ids,
            }
        )
        delivery_picking.action_confirm()
        second_move = self.env["stock.move"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.productlot1.id,
                "product_uom_id": self.uom_unit.id,
                "quantity": 2,
                "picking_id": delivery_picking.id,
                "reference_ids": ref.ids,
            }
        )
        second_move.move_line_ids.trace_id = lot_xyz
        self.assertEqual(len(delivery_picking.move_ids), 2)
        url = self._get_client_action_url(delivery_picking.id)
        self.start_tour(
            url, "test_select_with_same_product_and_lot", login="admin", timeout=180
        )

    def test_description_picking_tour(self):
        product = self.env["product.product"].create(
            {
                "name": "test_product",
                "description_pickingin": "receipt",
                "barcode": "test_product",
            }
        )
        action_id = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = "/web#action=" + str(action_id.id)
        self.start_tour(
            url, "test_description_picking_tour", login="admin", timeout=180
        )
        picking = self.env["stock.picking"].search(
            [("move_ids.product_id.id", "=", product.id), ("state", "=", "done")]
        )

        self.assertEqual(picking.move_ids.description_picking, "receipt")

    def test_no_validate_no_dest_package(self):
        grp_multi_loc = self.env.ref("stock.group_stock_multi_locations")
        grp_pack = self.env.ref("stock.group_tracking_lot")
        self.env.user.write(
            {"group_ids": [Command.link(grp_pack.id), Command.link(grp_multi_loc.id)]}
        )
        self.picking_type_internal.write(
            {
                "restrict_scan_source_location": "mandatory",
                "restrict_scan_dest_location": "mandatory",
                "active": True,
            }
        )
        pack1 = self.env["stock.package"].create(
            {
                "name": "Pack1",
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 5, package_id=pack1
        )
        action_id = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = "/web#action=" + str(action_id.id)
        self.start_tour(url, "test_no_validate_no_dest_package", login="admin")
        internal = self._last_picking(self.picking_type_internal)
        self.assertNotEqual(internal.state, "done")
        self.assertFalse(internal.move_line_ids.filtered("picked"))

    def test_qty_after_uom_update_picking_tour(self):
        self.env.user.group_ids += self.env.ref("base.group_uom")
        product = self.env["product.product"].create(
            {
                "name": "test_product_uom_update",
                "barcode": "test_product_uom_update",
                "uom_ids": [Command.link(self.env.ref("base.product_uom_dozen").id)],
            }
        )
        receipt = self.env["stock.picking"].create(
            {
                "name": "receipt_test",
                "location_id": self.customer_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_uom_qty": 10,
                            "product_uom_id": self.env.ref("base.product_uom_dozen").id,
                            "location_id": self.customer_location.id,
                            "location_dest_id": self.stock_location.id,
                        }
                    )
                ],
            }
        )
        receipt.action_confirm()
        self.start_tour(
            "/odoo/barcode", "test_qty_after_uom_update_picking_tour", login="admin"
        )
        self.assertEqual(
            [(ml.quantity, ml.product_uom_id) for ml in receipt.move_line_ids],
            [(1, self.uom_unit)],
        )
        self.assertEqual(receipt.move_ids.product_uom_qty, 10)

    def test_stock_quant_ids_computed_by_product_update(self):
        self.env["stock.quant"].create(
            {
                "product_id": self.product1.id,
                "location_id": self.stock_location.id,
                "quantity": 10,
            }
        )
        internal_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_internal.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.stock_location.id,
                            "product_id": self.product1.id,
                            "location_dest_id": self.stock_location.id,
                            "product_uom_id": self.uom_unit.id,
                            "product_uom_qty": 1,
                        }
                    )
                ],
            }
        )
        internal_picking.action_confirm()
        self.assertEqual(
            internal_picking.move_ids.move_line_ids.product_stock_quant_ids.quantity,
            10.0,
        )

    def test_quantity_distribution_sublines_same_lot(self):
        grp_lot = self.env.ref("stock.group_production_lot")
        self.env.user.write({"group_ids": [Command.link(grp_lot.id)]})
        lot_1 = self.env["product.trace"].create(
            {
                "name": "lot 1",
                "product_id": self.productlot1.id,
                "company_id": self.env.company.id,
            }
        )
        self.env["stock.quant"].create(
            [
                {
                    "product_id": self.productlot1.id,
                    "inventory_quantity": 2,
                    "trace_id": lot_1.id,
                    "location_id": self.stock_location.id,
                },
            ]
        ).action_apply_inventory()

        delivery_picking = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.productlot1.id,
                            "product_uom_qty": 1,
                            "price_unit": i,
                            "product_uom_id": self.productlot1.uom_id.id,
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                        }
                    )
                    for i in (1, 3)
                ],
            }
        )
        delivery_picking.action_confirm()
        delivery_picking.action_assign()
        url = self._get_client_action_url(delivery_picking.id)
        self.start_tour(
            url, "test_quantity_distribution_sublines_same_lot", login="admin"
        )
        self.assertEqual(len(delivery_picking.backorder_ids), 0)
        self.assertRecordValues(
            delivery_picking.move_ids,
            [
                {
                    "quantity": 1.0,
                    "product_uom_qty": 1.0,
                    "trace_ids": [lot_1.id],
                    "picked": True,
                },
                {
                    "quantity": 1.0,
                    "product_uom_qty": 1.0,
                    "trace_ids": [lot_1.id],
                    "picked": True,
                },
            ],
        )

    def test_rental_partial_reception(self):
        if not self.env["ir.module.module"].search(
            [("name", "=", "sale_stock_renting"), ("state", "=", "installed")]
        ):
            self.skipTest(
                "sale_stock_renting is not installed, so there is no rental orders to test"
            )

        self.env["res.config.settings"].create(
            {"group_rental_stock_picking": True}
        ).execute()

        product = self.env["product.product"].create(
            {"name": "Rental", "rent_ok": True, "is_storable": True, "barcode": "RNT01"}
        )
        self.env["stock.quant"]._update_available_quantity(
            product, self.stock_location, 4
        )
        rental = (
            self.env["sale.order"]
            .with_context(in_rental_app=True)
            .create(
                {
                    "partner_id": self.owner.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": product.id,
                                "product_qty": 4,
                            }
                        )
                    ],
                }
            )
        )
        rental.action_confirm()
        delivery = rental.picking_ids.filtered(
            lambda p: p.picking_type_id == rental.warehouse_id.out_type_id
        )
        receipt = rental.picking_ids - delivery
        delivery.button_validate()

        url = self._get_client_action_url(receipt.id)
        self.start_tour(
            url, "test_rental_partial_reception", login="admin", timeout=180
        )

        self.assertTrue(receipt.backorder_ids)
        self.assertEqual(receipt.backorder_ids.move_ids.product_uom_qty, 3.0)

    def test_no_validate_multiple_times(self):
        grp_multi_loc = self.env.ref("stock.group_stock_multi_locations")
        self.env.user.write({"group_ids": [Command.link(grp_multi_loc.id)]})
        self.picking_type_internal.action_unarchive()
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 1
        )
        self.start_tour(
            "/odoo/barcode", "test_no_validate_multiple_times", login="admin"
        )

        quant = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product2.id),
                ("location_id", "=", self.shelf1.id),
            ],
            limit=1,
        )
        self.assertEqual(quant.quantity, 1)
