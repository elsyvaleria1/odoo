from odoo import Command
from odoo.tests import tagged

from odoo.addons.stock_barcode.tests.test_barcode_client_action import (
    TestBarcodeClientAction,
)


@tagged("post_install", "-at_install")
class TestBarcodeClientActionPicking(TestBarcodeClientAction):
    def test_operation_quality_check_barcode(self):

        product3 = self.env["product.product"].create(
            {
                "name": "product3",
                "is_storable": True,
                "barcode": "product3",
            }
        )
        quality_points = self.env["quality.point"].create(
            [
                {
                    "title": "check product 1",
                    "measure_on": "operation",
                    "product_ids": [Command.link(self.product1.id)],
                    "picking_type_ids": [Command.link(self.picking_type_in.id)],
                },
                {
                    "title": "check product 2",
                    "measure_on": "operation",
                    "product_ids": [Command.link(self.product2.id)],
                    "picking_type_ids": [Command.link(self.picking_type_in.id)],
                },
                {
                    "title": "check product 3",
                    "measure_on": "operation",
                    "product_ids": [Command.link(product3.id)],
                    "picking_type_ids": [Command.link(self.picking_type_in.id)],
                },
            ]
        )

        self.start_tour(
            "/odoo/barcode", "test_operation_quality_check_barcode", login="admin"
        )

        quality_checks = self.env["quality.check"].search(
            [("point_id", "in", quality_points.ids)]
        )
        self.assertRecordValues(
            quality_checks.sorted("title"),
            [
                {"title": "check product 1", "quality_state": "pass"},
                {"title": "check product 2", "quality_state": "fail"},
                {"title": "check product 3", "quality_state": "none"},
            ],
        )
        self.assertEqual(quality_checks.picking_id[0].state, "done")
        self.assertEqual(quality_checks.picking_id[1].state, "assigned")

    def test_operation_quality_check_delivery_barcode(self):

        quality_points = self.env["quality.point"].create(
            [
                {
                    "title": "check product 1",
                    "measure_on": "operation",
                    "product_ids": [Command.link(self.product1.id)],
                    "picking_type_ids": [Command.link(self.picking_type_out.id)],
                },
                {
                    "title": "check product 2",
                    "measure_on": "operation",
                    "product_ids": [Command.link(self.product2.id)],
                    "picking_type_ids": [Command.link(self.picking_type_out.id)],
                },
            ]
        )
        action_id = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = "/web#action=" + str(action_id.id)

        self.start_tour(
            url, "test_operation_quality_check_delivery_barcode", login="admin"
        )

        quality_checks = self.env["quality.check"].search(
            [("point_id", "in", quality_points.ids)]
        )
        self.assertRecordValues(
            quality_checks.sorted("title"),
            [
                {"title": "check product 1", "quality_state": "pass"},
                {"title": "check product 2", "quality_state": "fail"},
            ],
        )
        self.assertEqual(quality_checks.picking_id.state, "done")

    def test_quality_check_partial_reception_barcode(self):
        self.env["quality.point"].create(
            [
                {
                    "title": f"check on {measure_on}",
                    "measure_on": measure_on,
                    "product_ids": [Command.link(product.id)],
                    "picking_type_ids": [Command.link(self.picking_type_in.id)],
                }
                for measure_on, product in (
                    ("product", self.product1),
                    ("move_line", self.productserial1),
                )
            ]
        )

        picking_in = self.env["stock.picking"].create(
            {
                "name": "WHINQCPRB",
                "picking_type_id": self.picking_type_in.id,
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_uom_id": product.uom_id.id,
                            "product_uom_qty": 2,
                            "location_id": self.supplier_location.id,
                            "location_dest_id": self.stock_location.id,
                        }
                    )
                    for product in (self.product1, self.productserial1)
                ],
            }
        )
        picking_in.action_confirm()
        self.assertRecordValues(
            picking_in.check_ids.sorted(lambda qc: qc.point_id.id),
            [
                {"product_id": self.product1.id, "measure_on": "product"},
                {"product_id": self.productserial1.id, "measure_on": "move_line"},
                {"product_id": self.productserial1.id, "measure_on": "move_line"},
            ],
        )
        self.start_tour(
            "/odoo/barcode",
            "test_quality_check_partial_reception_barcode",
            login="admin",
        )
        self.assertEqual(picking_in.state, "done")
        self.assertRecordValues(
            picking_in.check_ids,
            [
                {
                    "product_id": self.productserial1.id,
                    "measure_on": "move_line",
                    "quality_state": "pass",
                    "lot_name": "SN001",
                },
            ],
        )

    def test_quality_check_packages_lots_tour(self):
        grp_lot = self.env.ref("stock.group_tracking_lot")
        self.env.user.write({"group_ids": [Command.link(grp_lot.id)]})
        product_lot = self.productlot1
        self.env["quality.point"].create(
            {
                "product_ids": [Command.link(product_lot.id)],
                "picking_type_ids": [Command.link(self.picking_type_in.id)],
                "measure_on": "move_line",
            }
        )
        receipt = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_in.id,
                "partner_id": self.owner.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": product_lot.id,
                            "product_uom_qty": 4,
                            "product_uom_id": product_lot.uom_id.id,
                            "location_id": self.supplier_location.id,
                            "location_dest_id": self.stock_location.id,
                        }
                    )
                ],
            }
        )
        receipt.action_confirm()
        self.start_tour(
            self._get_client_action_url(receipt.id),
            "test_quality_check_packages_lots_tour",
            login="admin",
        )
