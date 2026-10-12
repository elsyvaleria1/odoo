from odoo import Command
from odoo.tests import Form, tagged

from odoo.addons.stock_barcode.tests.test_barcode_client_action import (
    TestBarcodeClientAction,
)


@tagged("post_install", "-at_install")
class TestBarcodeBatchClientAction(TestBarcodeClientAction):
    def setUp(self):
        super().setUp()

        self.env.ref("base.user_admin").write(
            {
                "email": "mitchell.admin@example.com",
            }
        )

        self.product3 = self.env["product.product"].create(
            {
                "name": "product3",
                "is_storable": True,
                "barcode": "product3",
            }
        )
        self.product4 = self.env["product.product"].create(
            {
                "name": "product4",
                "is_storable": True,
                "barcode": "product4",
            }
        )
        self.product5 = self.env["product.product"].create(
            {
                "name": "product5",
                "is_storable": True,
                "barcode": "product5",
            }
        )

        self.shelf5 = self.env["stock.location"].create(
            {
                "name": "Section 5",
                "location_id": self.stock_location.id,
                "barcode": "shelf5",
            }
        )

        self.package1 = self.env["stock.package"].create({"name": "p5pack01"})
        self.package2 = self.env["stock.package"].create({"name": "p5pack02"})

        Quant = self.env["stock.quant"]
        quants = Quant.with_context(inventory_mode=True).create(
            {
                "product_id": self.product1.id,
                "location_id": self.shelf1.id,
                "inventory_quantity": 2,
            }
        )
        quants |= Quant.with_context(inventory_mode=True).create(
            {
                "product_id": self.product2.id,
                "location_id": self.shelf2.id,
                "inventory_quantity": 1,
            }
        )
        quants |= Quant.with_context(inventory_mode=True).create(
            {
                "product_id": self.product2.id,
                "location_id": self.shelf3.id,
                "inventory_quantity": 1,
            }
        )
        quants |= Quant.with_context(inventory_mode=True).create(
            {
                "product_id": self.product3.id,
                "location_id": self.shelf3.id,
                "inventory_quantity": 2,
            }
        )
        quants |= Quant.with_context(inventory_mode=True).create(
            {
                "product_id": self.product4.id,
                "location_id": self.shelf1.id,
                "inventory_quantity": 1,
            }
        )
        quants |= Quant.with_context(inventory_mode=True).create(
            {
                "product_id": self.product4.id,
                "location_id": self.shelf4.id,
                "inventory_quantity": 1,
            }
        )
        quants |= Quant.with_context(inventory_mode=True).create(
            {
                "product_id": self.product5.id,
                "location_id": self.shelf5.id,
                "package_id": self.package1.id,
                "inventory_quantity": 4,
            }
        )
        quants |= Quant.with_context(inventory_mode=True).create(
            {
                "product_id": self.product5.id,
                "location_id": self.shelf5.id,
                "inventory_quantity": 4,
            }
        )
        quants.action_apply_inventory()

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_in
        with picking_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 1
        with picking_form.move_ids.new() as move:
            move.product_id = self.productserial1
            move.product_uom_qty = 2
        self.picking_receipt_1 = picking_form.save()
        self.picking_receipt_1.action_confirm()

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_in
        with picking_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 3
        with picking_form.move_ids.new() as move:
            move.product_id = self.productlot1
            move.product_uom_qty = 8
        self.picking_receipt_2 = picking_form.save()
        self.picking_receipt_2.action_confirm()

        self.picking_receipt_1.name = "picking_receipt_1"
        self.picking_receipt_2.name = "picking_receipt_2"

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_out
        with picking_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 1
        with picking_form.move_ids.new() as move:
            move.product_id = self.product2
            move.product_uom_qty = 2
        self.picking_delivery_1 = picking_form.save()
        self.picking_delivery_1.action_confirm()
        self.picking_delivery_1.action_assign()

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_out
        with picking_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 1
        with picking_form.move_ids.new() as move:
            move.product_id = self.product3
            move.product_uom_qty = 2
        with picking_form.move_ids.new() as move:
            move.product_id = self.product4
            move.product_uom_qty = 2
        self.picking_delivery_2 = picking_form.save()
        self.picking_delivery_2.action_confirm()
        self.picking_delivery_2.action_assign()

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_out
        with picking_form.move_ids.new() as move:
            move.product_id = self.product5
            move.product_uom_qty = 8
        self.picking_delivery_package = picking_form.save()
        self.picking_delivery_package.action_confirm()
        self.picking_delivery_package.action_assign()

        Quant.with_context(inventory_mode=True).create(
            {
                "product_id": self.product5.id,
                "location_id": self.shelf5.id,
                "package_id": self.package2.id,
                "inventory_quantity": 4,
            }
        ).action_apply_inventory()

        self.picking_delivery_1.name = "picking_delivery_1"
        self.picking_delivery_2.name = "picking_delivery_2"
        self.picking_delivery_package.name = "picking_delivery_package"

    def _get_batch_client_action_url(self, batch_id):
        return f"/odoo/{batch_id}/action-stock_barcode_picking_batch.stock_barcode_picking_batch_client_action"

    def test_barcode_batch_receipt_1(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )
        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_in
        with picking_form.move_ids.new() as move:
            move.product_id = self.productlot1
            move.product_uom_qty = 4
        picking_receipt_3 = picking_form.save()
        picking_receipt_3.action_confirm()
        picking_receipt_3.name = "picking_receipt_3"
        picking_receipt_3.user_id = False

        batch_form = Form(self.env["stock.picking.batch"])
        batch_form.picking_ids.add(self.picking_receipt_1)
        batch_form.picking_ids.add(self.picking_receipt_2)
        batch_form.picking_ids.add(picking_receipt_3)
        batch_receipt = batch_form.save()
        self.assertEqual(
            batch_receipt.picking_type_id.id,
            self.picking_receipt_1.picking_type_id.id,
            "Batch picking must take the picking type of its sub-pickings",
        )
        batch_receipt.action_confirm()
        self.assertEqual(len(batch_receipt.move_ids), 5)
        self.assertEqual(len(batch_receipt.move_line_ids), 6)
        self.assertEqual(batch_receipt.user_id.id, False)
        self.assertEqual(picking_receipt_3.user_id.id, False)

        url = self._get_batch_client_action_url(batch_receipt.id)
        self.start_tour(url, "test_barcode_batch_receipt_1", login="admin", timeout=180)
        self.assertEqual(batch_receipt.user_id.id, self.env.user.id)
        self.assertEqual(picking_receipt_3.user_id.id, self.env.user.id)

    def test_barcode_batch_delivery_1(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        batch_form = Form(self.env["stock.picking.batch"])
        sn1 = self.env["product.trace"].create(
            {"name": "sn1", "product_id": self.productserial1.id}
        )
        sn2 = self.env["product.trace"].create(
            {"name": "sn2", "product_id": self.productserial1.id}
        )
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": self.productserial1.id,
                "inventory_quantity": 1,
                "trace_id": sn1.id,
                "location_id": self.shelf1.id,
            }
        ).action_apply_inventory()
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": self.productserial1.id,
                "inventory_quantity": 1,
                "trace_id": sn2.id,
                "location_id": self.shelf1.id,
            }
        ).action_apply_inventory()

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_out
        with picking_form.move_ids.new() as move:
            move.product_id = self.productserial1
            move.product_uom_qty = 1
        picking_delivery_sn = picking_form.save()
        picking_delivery_sn.name = "picking_delivery_sn"
        picking_delivery_sn.action_confirm()
        picking_delivery_sn.action_assign()

        batch_form.picking_ids.add(self.picking_delivery_1)
        batch_form.picking_ids.add(self.picking_delivery_2)
        batch_form.picking_ids.add(self.picking_delivery_package)
        batch_form.picking_ids.add(picking_delivery_sn)
        batch_delivery = batch_form.save()
        self.assertEqual(
            batch_delivery.picking_type_id.id,
            self.picking_delivery_1.picking_type_id.id,
            "Batch picking must take the picking type of its sub-pickings",
        )
        batch_delivery.action_confirm()
        self.assertEqual(len(batch_delivery.move_ids), 7)
        self.assertEqual(len(batch_delivery.move_line_ids), 10)
        packaged_move_lines = batch_delivery.move_line_ids.filtered(
            lambda ml: ml.product_id.id == self.product5.id
        )
        self.assertEqual(len(packaged_move_lines), 2)
        self.assertEqual(packaged_move_lines.package_id.id, self.package1.id)

        url = self._get_batch_client_action_url(batch_delivery.id)
        self.start_tour(
            url, "test_barcode_batch_delivery_1", login="admin", timeout=180
        )

    def test_barcode_batch_delivery_2_move_entire_package(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )
        self.picking_type_out.show_entire_packs = True

        pack1 = self.env["stock.package"].create({"name": "pack1"})
        pack2 = self.env["stock.package"].create({"name": "pack2"})
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": self.product1.id,
                "inventory_quantity": 10,
                "package_id": pack1.id,
                "location_id": self.stock_location.id,
            }
        ).action_apply_inventory()
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": self.product2.id,
                "inventory_quantity": 10,
                "package_id": pack2.id,
                "location_id": self.stock_location.id,
            }
        ).action_apply_inventory()
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": self.product3.id,
                "inventory_quantity": 10,
                "package_id": pack1.id,
                "location_id": self.stock_location.id,
            }
        ).action_apply_inventory()

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_out
        with picking_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 10
        with picking_form.move_ids.new() as move:
            move.product_id = self.product2
            move.product_uom_qty = 5
        with picking_form.move_ids.new() as move:
            move.product_id = self.product3
            move.product_uom_qty = 10
        delivery_1 = picking_form.save()
        delivery_1.action_confirm()
        delivery_1.action_assign()

        picking_form = Form(self.env["stock.picking"])
        picking_form.picking_type_id = self.picking_type_out
        with picking_form.move_ids.new() as move:
            move.product_id = self.product2
            move.product_uom_qty = 5
        delivery_2 = picking_form.save()
        delivery_2.action_confirm()
        delivery_2.action_assign()

        delivery_1.name = "delivery_1"
        delivery_2.name = "delivery_2"

        batch_form = Form(self.env["stock.picking.batch"])
        batch_form.picking_ids.add(delivery_1)
        batch_form.picking_ids.add(delivery_2)
        batch_delivery = batch_form.save()
        batch_delivery.action_confirm()

        url = self._get_batch_client_action_url(batch_delivery.id)
        self.start_tour(
            url,
            "test_barcode_batch_delivery_2_move_entire_package",
            login="admin",
            timeout=180,
        )

    def test_barcode_batch_operation_buttons_count(self):
        company = self.env["res.company"].create({"name": "Company Test"})
        self.env.user.write(
            {
                "company_ids": [Command.link(company.id)],
                "company_id": company.id,
            }
        )

        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", company.id)]
        )
        warehouse.code = "TEST"
        picking_type_in = warehouse.in_type_id
        picking_type_in.auto_batch = False
        picking_type_out = warehouse.out_type_id
        src_location = picking_type_out.default_location_src_id
        self.env["stock.quant"]._update_available_quantity(
            self.product3, src_location, 99
        )

        pickings = self.env["stock.picking"]
        for ptype in ([picking_type_in] * 2) + ([picking_type_out] * 3):
            pickings |= self.env["stock.picking"].create(
                {
                    "location_id": ptype.default_location_src_id.id,
                    "location_dest_id": ptype.default_location_dest_id.id,
                    "picking_type_id": ptype.id,
                    "move_ids": [
                        Command.create(
                            {
                                "location_id": ptype.default_location_src_id.id,
                                "location_dest_id": ptype.default_location_dest_id.id,
                                "product_id": self.product3.id,
                                "product_uom_id": self.uom_unit.id,
                                "product_uom_qty": 1,
                            }
                        )
                    ],
                }
            )
        pickings.action_confirm()
        self.start_tour(
            "odoo/barcode/", "test_barcode_batch_operation_buttons_count", login="admin"
        )

    def test_barcode_batch_scan_lots(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        common_vals = {
            "product_id": self.productlot1.id,
            "company_id": self.env.company.id,
        }
        lot1 = self.env["product.trace"].create({**common_vals, "name": "lot1"})
        lot2 = self.env["product.trace"].create({**common_vals, "name": "lot2"})
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 3, trace_id=lot1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 3, trace_id=lot2
        )

        receipt_form = Form(self.env["stock.picking"])
        receipt_form.picking_type_id = self.picking_type_in
        with receipt_form.move_ids.new() as move:
            move.product_id = self.productlot1
            move.product_uom_qty = 4
        receipt_1 = receipt_form.save()
        receipt_1.action_confirm()
        receipt_1.name = "receipt_1"

        receipt_2 = receipt_1.copy()
        receipt_2.action_confirm()
        receipt_2.name = "receipt_2"

        batch_form = Form(self.env["stock.picking.batch"])
        batch_form.picking_ids.add(receipt_1)
        batch_form.picking_ids.add(receipt_2)
        batch_receipt = batch_form.save()
        batch_receipt.action_confirm()
        batch_receipt.name = "test_barcode_batch_scan_lots - receipt"

        delivery_form = Form(self.env["stock.picking"])
        delivery_form.picking_type_id = self.picking_type_out
        with delivery_form.move_ids.new() as move:
            move.product_id = self.productlot1
            move.product_uom_qty = 3
        delivery_1 = delivery_form.save()
        delivery_1.action_confirm()
        delivery_1.name = "delivery_1"

        delivery_2 = delivery_1.copy()
        delivery_2.action_confirm()
        delivery_2.name = "delivery_2"

        batch_form = Form(self.env["stock.picking.batch"])
        batch_form.picking_ids.add(delivery_1)
        batch_form.picking_ids.add(delivery_2)
        batch_delivery = batch_form.save()
        batch_delivery.action_confirm()
        batch_delivery.name = "test_barcode_batch_scan_lots - delivery"

        self.start_tour(
            "/odoo/action-stock_barcode.stock_barcode_action_main_menu",
            "test_barcode_batch_scan_lots",
            login="admin",
            timeout=180,
        )

        lot1, lot2, lot3 = (
            batch_receipt | batch_delivery
        ).move_line_ids.trace_id.sorted("name")
        self.assertRecordValues(
            receipt_1.move_line_ids,
            [
                {
                    "trace_id": lot1.id,
                    "lot_name": "lot1",
                    "quantity": 3,
                    "picked": True,
                },
                {
                    "trace_id": lot2.id,
                    "lot_name": "lot2",
                    "quantity": 1,
                    "picked": True,
                },
            ],
        )
        self.assertRecordValues(
            receipt_2.move_line_ids,
            [
                {
                    "trace_id": lot2.id,
                    "lot_name": "lot2",
                    "quantity": 2,
                    "picked": True,
                },
                {
                    "trace_id": lot3.id,
                    "lot_name": "lot3",
                    "quantity": 2,
                    "picked": True,
                },
            ],
        )
        self.assertRecordValues(
            delivery_1.move_line_ids,
            [
                {"trace_id": lot2.id, "quantity": 2, "picked": True},
                {"trace_id": lot3.id, "quantity": 1, "picked": True},
            ],
        )
        self.assertRecordValues(
            delivery_2.move_line_ids,
            [
                {"trace_id": lot2.id, "quantity": 1, "picked": True},
                {"trace_id": lot1.id, "quantity": 1, "picked": True},
                {"trace_id": lot3.id, "quantity": 1, "picked": True},
            ],
        )

    def test_barcode_batch_scan_other_reserved_lost(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        self.picking_type_out.show_reserved_sns = True
        common_vals = {
            "product_id": self.productlot1.id,
            "company_id": self.env.company.id,
        }
        lots = self.env["product.trace"].create(
            [{**common_vals, "name": f"lot{i}"} for i in range(1, 4)]
        )
        for lot in lots:
            self.env["stock.quant"]._update_available_quantity(
                self.productlot1, self.stock_location, 3, trace_id=lot
            )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 1, trace_id=False
        )
        delivery = self.env["stock.picking"].create(
            {
                "name": "delivery with lots",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "picking_type_id": self.picking_type_out.id,
                "move_ids": [
                    Command.create(
                        {
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                            "product_id": self.productlot1.id,
                            "product_uom_id": self.uom_unit.id,
                            "product_uom_qty": 10,
                        }
                    )
                ],
            }
        )
        batch = self.env["stock.picking.batch"].create(
            {
                "picking_ids": [Command.link(delivery.id)],
            }
        )
        batch.name = "delivery batch"
        batch.action_confirm()
        self.start_tour(
            "/odoo/barcode",
            "test_barcode_batch_scan_other_reserved_lost",
            login="admin",
            timeout=180,
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

        self.picking_type_internal.restrict_scan_dest_location = "no"
        self.picking_type_internal.restrict_scan_source_location = "mandatory"

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
        internal_picking2 = self.env["stock.picking"].create(
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
                "product_id": self.product2.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 2,
                "picking_id": internal_picking2.id,
            }
        )

        internal_picking.action_confirm()
        internal_picking.action_assign()
        internal_picking2.action_confirm()
        internal_picking2.action_assign()

        batch_form = Form(self.env["stock.picking.batch"])
        batch_form.picking_ids.add(internal_picking)
        batch_form.picking_ids.add(internal_picking2)
        batch_internal = batch_form.save()

        batch_internal.action_confirm()
        self.assertEqual(len(batch_internal.move_ids), 2)

        url = self._get_batch_client_action_url(batch_internal.id)

        self.start_tour(
            url, "test_put_in_pack_from_multiple_pages", login="admin", timeout=180
        )

        pack = self.env["stock.package"].search(
            [("location_id", "=", self.stock_location.id)], limit=1
        )
        self.assertEqual(len(pack.quant_ids), 2)
        self.assertEqual(sum(pack.quant_ids.mapped("quantity")), 4)

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
        internal_picking2 = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_internal.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_id": self.shelf3.id,
                "location_dest_id": self.shelf4.id,
                "product_id": self.product2.id,
                "product_uom_id": self.uom_unit.id,
                "product_uom_qty": 1,
                "picking_id": internal_picking2.id,
            }
        )

        internal_picking.action_confirm()
        internal_picking.action_assign()
        internal_picking2.action_confirm()
        internal_picking2.action_assign()

        batch_form = Form(self.env["stock.picking.batch"])
        batch_form.picking_ids.add(internal_picking)
        batch_form.picking_ids.add(internal_picking2)
        batch_internal = batch_form.save()

        batch_internal.action_confirm()
        self.assertEqual(len(batch_internal.move_ids), 2)

        url = self._get_batch_client_action_url(batch_internal.id)

        self.start_tour(url, "test_put_in_pack_before_dest", login="admin", timeout=180)
        pack = self.env["stock.package"].search(
            [("location_id", "=", self.shelf2.id)], limit=1
        )
        self.assertEqual(len(pack.quant_ids), 2)
        self.assertEqual(pack.location_id, self.shelf2)

    def test_put_in_pack_scan_suggested_package(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        self.picking_type_out.barcode_validation_all_product_packed = True

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 2
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf2, 2
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product3, self.shelf1, 1
        )

        delivery_form = Form(self.env["stock.picking"])
        delivery_form.picking_type_id = self.picking_type_out
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 1
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product2
            move.product_uom_qty = 1
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product3
            move.product_uom_qty = 1
        delivery_1 = delivery_form.save()
        delivery_1.action_confirm()
        delivery_1.action_assign()

        delivery_form = Form(self.env["stock.picking"])
        delivery_form.picking_type_id = self.picking_type_out
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product1
            move.product_uom_qty = 1
        with delivery_form.move_ids.new() as move:
            move.product_id = self.product2
            move.product_uom_qty = 1
        delivery_2 = delivery_form.save()
        delivery_2.action_confirm()
        delivery_2.action_assign()

        delivery_1.name = "test_delivery_1"
        delivery_2.name = "test_delivery_2"

        batch_form = Form(self.env["stock.picking.batch"])
        batch_form.picking_ids.add(delivery_1)
        batch_form.picking_ids.add(delivery_2)
        batch_delivery = batch_form.save()
        batch_delivery.action_confirm()
        self.assertEqual(len(batch_delivery.move_ids), 5)
        self.assertEqual(len(batch_delivery.move_line_ids), 5)
        self._reset_package_sequence()

        url = self._get_batch_client_action_url(batch_delivery.id)
        self.start_tour(
            url, "test_put_in_pack_scan_suggested_package", login="admin", timeout=180
        )

        self.assertEqual(batch_delivery.state, "done")
        self.assertEqual(len(batch_delivery.move_line_ids), 5)
        for move_line in delivery_1.move_line_ids:
            self.assertEqual(move_line.result_package_id.name, "PACK0000001")
        for move_line in delivery_2.move_line_ids:
            self.assertEqual(move_line.result_package_id.name, "PACK0000002")

    def test_batch_create(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        batches_before = self.env["stock.picking.batch"].search([])
        self.start_tour(
            "/odoo/barcode", "test_batch_create", login="admin", timeout=180
        )
        self.assertEqual(
            self.env["stock.picking.batch"].search([]) - batches_before,
            self.picking_delivery_1.batch_id,
            "the only batch the tour leaves is the one it confirmed",
        )
        self.assertEqual(
            self.picking_delivery_1.batch_id, self.picking_delivery_2.batch_id
        )
        batch_delivery = self.picking_delivery_1.batch_id
        self.assertEqual(len(batch_delivery.move_ids), 5)
        self.assertEqual(len(batch_delivery.move_line_ids), 7)

    def test_pack_and_same_product_several_sml(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )

        package02 = self.package.copy({"name": "P00002"})
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 10, package_id=self.package
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf1, 100, package_id=package02
        )

        pickings = self.env["stock.picking"].create(
            [
                {
                    "location_id": self.shelf1.id,
                    "location_dest_id": self.shelf2.id,
                    "picking_type_id": self.picking_type_internal.id,
                    "move_ids": [
                        (
                            0,
                            0,
                            {
                                "location_id": self.shelf1.id,
                                "location_dest_id": self.shelf2.id,
                                "product_id": product.id,
                                "product_uom_id": self.uom_unit.id,
                                "product_uom_qty": qty,
                            },
                        )
                        for product, qty in picking_lines
                    ],
                }
                for picking_lines in [
                    [(self.product1, 3), (self.product2, 25)],
                    [(self.product1, 7), (self.product2, 30)],
                ]
            ]
        )
        pickings.action_confirm()
        pickings.action_assign()

        batch_form = Form(self.env["stock.picking.batch"])
        batch_form.picking_ids.add(pickings[0])
        batch_form.picking_ids.add(pickings[1])
        batch = batch_form.save()
        batch.action_confirm()

        url = self._get_batch_client_action_url(batch.id)
        self.start_tour(
            url, "test_pack_and_same_product_several_sml", login="admin", timeout=180
        )

        self.assertRecordValues(
            pickings.move_ids,
            [
                {
                    "picking_id": pickings[0].id,
                    "product_id": self.product1.id,
                    "state": "done",
                    "quantity": 3,
                    "picked": True,
                },
                {
                    "picking_id": pickings[0].id,
                    "product_id": self.product2.id,
                    "state": "done",
                    "quantity": 70,
                    "picked": True,
                },
                {
                    "picking_id": pickings[1].id,
                    "product_id": self.product1.id,
                    "state": "done",
                    "quantity": 7,
                    "picked": True,
                },
                {
                    "picking_id": pickings[1].id,
                    "product_id": self.product2.id,
                    "state": "done",
                    "quantity": 30,
                    "picked": True,
                },
            ],
        )

    def test_setting_group_lines_by_product(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_production_lot").id),
                ],
            }
        )
        self.picking_type_in.group_lines_by_product = True

        receipt1 = self.env["stock.picking"].create(
            {
                "name": "receipt1",
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
                "state": "draft",
            }
        )
        receipt2 = self.env["stock.picking"].create(
            {
                "name": "receipt2",
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        receipt3 = self.env["stock.picking"].create(
            {
                "name": "receipt3",
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        self.env["stock.move"].create(
            [
                {
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "product_id": self.product1.id,
                    "product_uom_qty": 1,
                    "picking_id": receipt1.id,
                },
                {
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "product_id": self.productlot1.id,
                    "product_uom_qty": 4,
                    "picking_id": receipt1.id,
                },
                {
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "product_id": self.productlot1.id,
                    "product_uom_qty": 2,
                    "product_uom_id": self.productlot1.uom_id.id,
                    "picking_id": receipt2.id,
                },
                {
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "product_id": self.product1.id,
                    "product_uom_qty": 2,
                    "product_uom_id": self.product1.uom_id.id,
                    "picking_id": receipt2.id,
                },
                {
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "product_id": self.product2.id,
                    "product_uom_qty": 5,
                    "picking_id": receipt2.id,
                },
                {
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "product_id": self.product1.id,
                    "product_uom_qty": 3,
                    "picking_id": receipt3.id,
                    "state": "draft",
                },
                {
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.shelf2.id,
                    "product_id": self.product1.id,
                    "product_uom_qty": 2,
                    "picking_id": receipt3.id,
                    "state": "draft",
                },
            ]
        )
        receipts = receipt1 | receipt2 | receipt3
        receipts.action_confirm()
        receipts.action_assign()

        batch_receipts = self.env["stock.picking.batch"].create(
            {
                "name": "batch receipts test",
                "picking_ids": receipts.ids,
            }
        )
        batch_receipts.action_confirm()

        url = self._get_batch_client_action_url(batch_receipts.id)
        self.start_tour(
            url, "test_setting_group_lines_by_product", login="admin", timeout=180
        )

    def test_setting_group_lines_by_product_when_tracking_is_off(self):
        self.env.ref("base.group_user").write(
            {
                "implied_ids": [
                    Command.unlink(self.env.ref("stock.group_production_lot").id)
                ]
            }
        )
        self.picking_type_in.group_lines_by_product = True

        receipt_1 = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_in.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product1.id,
                            "product_uom_qty": 3,
                            "location_id": self.picking_type_in.default_location_src_id.id,
                            "location_dest_id": self.picking_type_in.default_location_dest_id.id,
                        }
                    )
                ],
            }
        )
        receipt_2 = receipt_1.copy()
        (receipt_1 | receipt_2).action_confirm()

        batch_receipt = self.env["stock.picking.batch"].create(
            {
                "picking_ids": [Command.link(receipt_1.id), Command.link(receipt_2.id)],
            }
        )
        batch_receipt.action_confirm()

        url = self._get_batch_client_action_url(batch_receipt.id)
        self.start_tour(
            url,
            "test_setting_group_lines_by_product_when_tracking_is_off",
            login="admin",
        )

    def test_split_line_on_exit_for_batch(self):
        batch_receipts = self.env["stock.picking.batch"].create(
            {
                "name": "batch_split_line_on_exit",
                "picking_type_id": self.picking_type_in.id,
            }
        )

        receipt1 = self.env["stock.picking"].create(
            {
                "batch_id": batch_receipts.id,
                "name": "receipt1",
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_dest_id": receipt1.location_dest_id.id,
                "location_id": receipt1.location_id.id,
                "picking_id": receipt1.id,
                "product_id": self.product1.id,
                "product_uom_qty": 4,
            }
        )
        receipt2 = self.env["stock.picking"].create(
            {
                "batch_id": batch_receipts.id,
                "name": "receipt2",
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_in.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_dest_id": receipt2.location_dest_id.id,
                "location_id": receipt2.location_id.id,
                "picking_id": receipt2.id,
                "product_id": self.product2.id,
                "product_uom_qty": 4,
            }
        )
        batch_receipts.action_confirm()

        self.start_tour(
            "odoo/barcode/", "test_split_line_on_exit_for_batch", login="admin"
        )
        self.assertRecordValues(
            receipt1.move_ids,
            [
                {"product_id": self.product1.id, "quantity": 4, "picked": True},
            ],
        )
        self.assertRecordValues(
            receipt1.move_line_ids,
            [
                {"quantity": 2, "picked": True},
                {"quantity": 2, "picked": False},
            ],
        )
        self.assertRecordValues(
            receipt2.move_ids,
            [
                {"product_id": self.product2.id, "quantity": 4, "picked": True},
            ],
        )
        self.assertRecordValues(
            receipt2.move_line_ids,
            [
                {"quantity": 1, "picked": True},
                {"quantity": 3, "picked": False},
            ],
        )

    def test_scan_can_change_destination_location(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, quantity=2
        )
        self.picking_type_internal.write(
            {
                "restrict_scan_source_location": "mandatory",
                "restrict_scan_product": True,
                "restrict_scan_dest_location": "mandatory",
            }
        )

        internal_picking_1 = self.env["stock.picking"].create(
            {
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
                "picking_type_id": self.picking_type_internal.id,
            }
        )
        self.env["stock.move"].create(
            {
                "location_dest_id": internal_picking_1.location_dest_id.id,
                "location_id": internal_picking_1.location_id.id,
                "picking_id": internal_picking_1.id,
                "product_id": self.product1.id,
                "product_uom_qty": 1,
            }
        )
        internal_picking_2 = internal_picking_1.copy()

        internal_picking_1.name = "test_int_picking_1"
        internal_picking_2.name = "test_int_picking_2"

        batch_form = Form(self.env["stock.picking.batch"])
        batch_form.picking_type_id = self.picking_type_internal
        batch_form.picking_ids.add(internal_picking_1)
        batch_form.picking_ids.add(internal_picking_2)
        batch = batch_form.save()
        batch.action_confirm()

        url = self._get_batch_client_action_url(batch.id)
        self.start_tour(url, "test_scan_can_change_destination_location", login="admin")

        move_lines = internal_picking_1.move_line_ids + internal_picking_2.move_line_ids
        self.assertEqual(move_lines.mapped("location_dest_id"), self.shelf3)

    def test_barcode_batch_partial_receipt_leave_reopen(self):
        self.picking_receipt_1.move_ids.filtered(
            lambda m: m.product_id == self.product1
        ).product_uom_qty = 5
        batch = self.env["stock.picking.batch"].create(
            {
                "picking_ids": [
                    Command.link(self.picking_receipt_1.id),
                    Command.link(self.picking_receipt_2.id),
                ],
            }
        )
        batch.action_confirm()
        self.assertEqual(len(batch.move_ids), 4)
        self.assertEqual(len(batch.move_line_ids), 5)

        url = self._get_batch_client_action_url(batch.id)
        self.start_tour(
            url,
            "test_barcode_batch_partial_receipt_leave_reopen",
            login="admin",
            timeout=180,
        )
        self.assertEqual(len(batch.move_ids), 4)
        self.assertEqual(len(batch.move_line_ids), 7)

    def test_pack_batch_in_multiple_packages(self):
        grp_pack = self.env.ref("stock.group_tracking_lot")
        self.env.user.write({"group_ids": [Command.link(grp_pack.id)]})
        batch_receipts = self.env["stock.picking.batch"].create(
            {
                "name": "test_pack_batch_in_multiple_packages",
                "picking_type_id": self.picking_type_in.id,
            }
        )
        products = self.product1 | self.product2
        receipts = self.env["stock.picking"].create(
            [
                {
                    "batch_id": batch_receipts.id,
                    "name": f"Lovely receipt {i + 1}",
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "picking_type_id": self.picking_type_in.id,
                    "move_ids": [
                        Command.create(
                            {
                                "location_id": self.supplier_location.id,
                                "location_dest_id": self.stock_location.id,
                                "product_id": product.id,
                                "product_uom_qty": 2 + i,
                            }
                        )
                        for product in products
                    ],
                }
                for i in range(2)
            ]
        )
        batch_receipts.action_confirm()
        url = self._get_batch_client_action_url(batch_receipts.id)
        self.start_tour(url, "test_pack_batch_in_multiple_packages", login="admin")
        self.assertFalse(receipts.backorder_ids)
        packages = (
            receipts[1]
            .move_line_ids.sorted(lambda ml: ml.product_id.id)
            .result_package_id
        )
        self.assertRecordValues(
            receipts.move_line_ids.sorted(
                lambda ml: (ml.picking_id.id, ml.product_id.id, ml.quantity)
            ),
            [
                {
                    "picking_id": receipts.ids[0],
                    "result_package_id": packages.ids[1],
                    "product_id": products.ids[0],
                    "quantity": 1.0,
                },
                {
                    "picking_id": receipts.ids[0],
                    "result_package_id": packages.ids[0],
                    "product_id": products.ids[0],
                    "quantity": 1.0,
                },
                {
                    "picking_id": receipts.ids[0],
                    "result_package_id": packages.ids[1],
                    "product_id": products.ids[1],
                    "quantity": 2.0,
                },
                {
                    "picking_id": receipts.ids[1],
                    "result_package_id": packages.ids[0],
                    "product_id": products.ids[0],
                    "quantity": 3.0,
                },
                {
                    "picking_id": receipts.ids[1],
                    "result_package_id": packages.ids[1],
                    "product_id": products.ids[1],
                    "quantity": 3.0,
                },
            ],
        )
