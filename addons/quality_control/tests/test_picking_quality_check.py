from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .test_common import TestQualityCommon
from odoo.addons.stock.tests.common import generate_lot_lines


@tagged("-at_install", "post_install")
class TestQualityCheck(TestQualityCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.receipt = cls.env["stock.picking"].create(
            {
                "picking_type_id": cls.picking_type_id,
                "location_id": cls.location_id,
                "location_dest_id": cls.location_dest_id,
            }
        )

        cls.product_move, cls.product2_move = cls.env["stock.move"].create(
            [
                {
                    "product_id": cls.product.id,
                    "product_uom_qty": 2,
                    "picking_id": cls.receipt.id,
                    "location_id": cls.receipt.location_id.id,
                    "location_dest_id": cls.receipt.location_dest_id.id,
                },
                {
                    "product_id": cls.product_2.id,
                    "product_uom_qty": 2,
                    "picking_id": cls.receipt.id,
                    "location_id": cls.receipt.location_id.id,
                    "location_dest_id": cls.receipt.location_dest_id.id,
                },
            ]
        )

    def test_00_picking_quality_check(self):

        self.qality_point_test = self.env["quality.point"].create(
            {
                "product_ids": [(4, self.product.id)],
                "picking_type_ids": [(4, self.picking_type_id)],
            }
        )

        self.assertTrue(
            self.qality_point_test,
            "First Quality Point not created for Laptop Customized.",
        )

        self.picking_in = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )

        self.assertTrue(self.picking_in, "Incoming shipment not created.")

        self.picking_in.action_confirm()

        self.assertEqual(len(self.picking_in.check_ids), 1)
        self.assertEqual(self.picking_in.check_ids.quality_state, "none")

        self.picking_in.check_ids.do_pass()

        self.picking_in.button_validate()

        self.assertEqual(self.picking_in.check_ids.quality_state, "pass")

    def test_01_picking_quality_check_type_text(self):
        self.qality_point_test = self.env["quality.point"].create(
            {
                "product_ids": [(4, self.product.id)],
                "picking_type_ids": [(4, self.picking_type_id)],
                "test_type_id": self.env.ref("quality.test_type_instructions").id,
            }
        )

        self.assertTrue(self.qality_point_test, "Quality Point not created")

        self.picking_in = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )

        self.assertTrue(self.picking_in, "Incoming shipment not created.")

        self.picking_in.action_confirm()

        self.assertEqual(len(self.picking_in.check_ids), 1)
        self.assertEqual(self.picking_in.check_ids.quality_state, "none")

        self.assertEqual(self.picking_in.check_ids[0].test_type, "instructions")

    def test_02_picking_quality_check_type_picture(self):
        self.qality_point_test = self.env["quality.point"].create(
            {
                "product_ids": [(4, self.product.id)],
                "picking_type_ids": [(4, self.picking_type_id)],
                "test_type_id": self.env.ref("quality.test_type_picture").id,
            }
        )
        self.assertTrue(self.qality_point_test, "Quality Point not created")
        self.picking_in = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.assertTrue(self.picking_in, "Incoming shipment not created.")
        self.picking_in.action_confirm()
        self.assertEqual(len(self.picking_in.check_ids), 1)
        self.assertEqual(self.picking_in.check_ids.quality_state, "none")

        self.assertEqual(self.picking_in.check_ids[0].test_type, "picture")

    def test_03_lot_quality_check(self):
        product_tracked_by_lot = self.env["product.product"].create(
            {
                "name": "Product tracked by lot",
                "is_storable": True,
                "tracking": "lot",
            }
        )

        product = self.env["product.product"].create(
            {
                "name": "Product",
                "tracking": "none",
            }
        )

        self.quality_point_test1 = self.env["quality.point"].create(
            {
                "product_ids": [product_tracked_by_lot.id],
                "picking_type_ids": [self.picking_type_id],
                "test_type_id": self.env.ref("quality_control.test_type_measure").id,
                "testing_percentage_within_lot": 10.02,
                "measure_on": "move_line",
                "norm": 5.0,
                "tolerance_min": 4.0,
                "tolerance_max": 6.0,
            }
        )

        self.quality_point_test2 = self.env["quality.point"].create(
            {
                "picking_type_ids": [self.picking_type_id],
                "test_type_id": self.env.ref("quality_control.test_type_measure").id,
                "measure_on": "move_line",
            }
        )

        self.quality_point_test3 = self.env["quality.point"].create(
            {
                "product_ids": [product.id],
                "picking_type_ids": [self.picking_type_id],
                "test_type_id": self.env.ref("quality_control.test_type_measure").id,
                "measure_on": "move_line",
            }
        )

        self.assertTrue(self.quality_point_test1, "Quality Point not created")
        self.assertTrue(self.quality_point_test2, "Quality Point not created")
        self.assertTrue(self.quality_point_test3, "Quality Point not created")

        self.picking_in = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )

        move = self.env["stock.move"].create(
            {
                "product_id": product_tracked_by_lot.id,
                "product_uom_qty": 11,
                "product_uom_id": product_tracked_by_lot.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )

        self.assertTrue(self.picking_in, "Incoming shipment not created.")

        generate_lot_lines(move, first_lot="1", count=1, quantity=10)
        self.assertTrue(
            len(move.move_line_ids) == 10,
            "Not all move lines are created with _generate_serial_number",
        )

        self.assertTrue(
            len(move.move_line_ids.check_ids) == 20,
            "Wrong number of Quality Checks created on the move lines",
        )

        move_line_vals = move._prepare_move_line_vals()
        move_line = self.env["stock.move.line"].create(move_line_vals)
        move_line.quantity = 1.0
        self.assertTrue(
            len(move.move_line_ids.check_ids) == 22,
            "Wrong number of Quality Checks created on the move lines",
        )

        move.move_line_ids[0].quantity = 2
        check_line1 = move.move_line_ids[0].check_ids[0]
        check_line2 = move.move_line_ids[1].check_ids[0]

        self.assertAlmostEqual(
            check_line1.qty_to_test,
            0.21,
            msg="Quantity to test within lot not well calculated (check rounding)",
        )
        self.assertAlmostEqual(
            check_line2.qty_to_test,
            0.11,
            msg="Quantity to test within lot not well calculated (check rounding)",
        )

        check_line1.measure = 3.0
        check_line2.measure = 4.5
        check_line1.do_measure()
        check_line2.do_measure()
        self.assertTrue(
            check_line1.quality_state == "fail",
            "Quality Check of type 'measure' not failing on move line",
        )
        self.assertTrue(
            check_line2.quality_state == "pass",
            "Quality Check of type 'measure' not passing on move line",
        )

        move_without_tracking1 = self.env["stock.move"].create(
            {
                "product_id": product.id,
                "product_uom_qty": 1,
                "quantity": 1,
                "product_uom_id": product.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.assertTrue(
            len(move_without_tracking1.move_line_ids.check_ids) == 2,
            "Wrong number of Quality Checks created on the move lines",
        )

        move_without_tracking2 = self.env["stock.move"].create(
            {
                "product_id": product.id,
                "product_uom_qty": 1,
                "quantity": 0,
                "product_uom_id": product.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        move_without_tracking2.quantity = 1
        self.assertTrue(
            len(move_without_tracking2.move_line_ids.check_ids) == 2,
            "Wrong number of Quality Checks created on the move lines",
        )

    def test_04_picking_quality_check_creation_no_products_no_categories(self):
        self.quality_point_test = self.env["quality.point"].create(
            {
                "picking_type_ids": [(4, self.picking_type_id)],
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
            }
        )
        self.assertTrue(self.quality_point_test, "Quality Point not created.")
        self.picking_in = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.assertTrue(self.picking_in, "Incoming shipment not created.")
        self.picking_in.action_confirm()
        self.assertEqual(len(self.picking_in.check_ids), 1)

    def test_05_picking_quality_check_creation_with_product_no_categories(self):
        self.quality_point_test = self.env["quality.point"].create(
            {
                "product_ids": [(4, self.product.id)],
                "picking_type_ids": [(4, self.picking_type_id)],
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
            }
        )
        self.assertTrue(self.quality_point_test, "Quality Point not created.")
        self.picking_in = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product_2.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product_2.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.assertTrue(self.picking_in, "Incoming shipment not created.")
        self.picking_in.action_confirm()
        self.assertEqual(len(self.picking_in.check_ids), 1)
        self.assertEqual(
            len(
                self.picking_in.check_ids.filtered(
                    lambda c: c.product_id.id == self.product.id
                )
            ),
            1,
        )
        self.assertEqual(
            len(
                self.picking_in.check_ids.filtered(
                    lambda c: c.product_id.id == self.product_2.id
                )
            ),
            0,
        )

    def test_06_picking_quality_check_creation_no_product_with_categories(self):
        self.quality_point_test = self.env["quality.point"].create(
            {
                "product_category_ids": [(4, self.product_category_base.id)],
                "picking_type_ids": [(4, self.picking_type_id)],
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
            }
        )
        self.assertTrue(self.quality_point_test, "Quality Point not created.")
        self.picking_in = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product_2.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product_2.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.assertTrue(self.picking_in, "Incoming shipment not created.")
        self.picking_in.action_confirm()
        self.assertEqual(len(self.picking_in.check_ids), 1)
        self.assertEqual(
            len(
                self.picking_in.check_ids.filtered(
                    lambda c: c.product_id.id == self.product.id
                )
            ),
            1,
        )
        self.assertEqual(
            len(
                self.picking_in.check_ids.filtered(
                    lambda c: c.product_id.id == self.product_2.id
                )
            ),
            0,
        )

    def test_07_picking_quality_check_creation_with_product_and_categories(self):
        self.quality_point_test = self.env["quality.point"].create(
            {
                "product_ids": [(4, self.product_2.id), (4, self.product_4.id)],
                "product_category_ids": [(4, self.product_category_base.id)],
                "picking_type_ids": [(4, self.picking_type_id)],
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
            }
        )
        self.assertTrue(self.quality_point_test, "Quality Point not created.")
        self.picking_in = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product_2.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product_2.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product_3.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product_3.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product_4.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product_4.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.assertTrue(self.picking_in, "Incoming shipment not created.")
        self.picking_in.action_confirm()
        self.assertEqual(len(self.picking_in.check_ids), 3)
        self.assertEqual(
            len(
                self.picking_in.check_ids.filtered(
                    lambda c: c.product_id.id == self.product.id
                )
            ),
            1,
        )
        self.assertEqual(
            len(
                self.picking_in.check_ids.filtered(
                    lambda c: c.product_id.id == self.product_2.id
                )
            ),
            1,
        )
        self.assertEqual(
            len(
                self.picking_in.check_ids.filtered(
                    lambda c: c.product_id.id == self.product_3.id
                )
            ),
            0,
        )
        self.assertEqual(
            len(
                self.picking_in.check_ids.filtered(
                    lambda c: c.product_id.id == self.product_4.id
                )
            ),
            1,
        )

    def test_08_on_product_creation_with_product_and_categories(self):
        self.quality_point_test = self.env["quality.point"].create(
            {
                "product_ids": [(4, self.product_2.id), (4, self.product_4.id)],
                "product_category_ids": [(4, self.product_category_base.id)],
                "picking_type_ids": [(4, self.picking_type_id)],
                "measure_on": "move_line",
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
            }
        )
        self.picking_in = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product_2.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product_2.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product_3.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product_3.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product_4.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product_4.uom_id.id,
                "picking_id": self.picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.picking_in.action_confirm()
        self.picking_in.move_ids.picked = True

        self.assertEqual(len(self.picking_in.check_ids), 3)
        self.assertEqual(
            len(
                self.picking_in.check_ids.filtered(
                    lambda c: c.product_id.id == self.product.id
                )
            ),
            1,
        )
        self.assertEqual(
            len(
                self.picking_in.check_ids.filtered(
                    lambda c: c.product_id.id == self.product_2.id
                )
            ),
            1,
        )
        self.assertEqual(
            len(
                self.picking_in.check_ids.filtered(
                    lambda c: c.product_id.id == self.product_3.id
                )
            ),
            0,
        )
        self.assertEqual(
            len(
                self.picking_in.check_ids.filtered(
                    lambda c: c.product_id.id == self.product_4.id
                )
            ),
            1,
        )

    def test_09_quality_check_on_operations(self):
        quality_point_operation_type = self.env["quality.point"].create(
            {
                "picking_type_ids": [(4, self.picking_type_id)],
                "measure_on": "operation",
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
            }
        )
        receipt = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            [
                {
                    "product_id": product.id,
                    "product_uom_qty": 1,
                    "product_uom_id": product.uom_id.id,
                    "picking_id": receipt.id,
                    "location_id": self.location_id,
                    "location_dest_id": self.location_dest_id,
                }
                for product in (self.product, self.product_2)
            ]
        )
        receipt.action_confirm()
        receipt.with_context(default_picking_id=receipt.id).write(
            {
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product_3.id,
                            "product_uom_qty": 1,
                            "location_id": self.location_id,
                            "location_dest_id": self.location_dest_id,
                        }
                    )
                ],
            }
        )
        self.assertEqual(len(receipt.check_ids), 1)
        self.assertEqual(receipt.check_ids.point_id, quality_point_operation_type)
        self.assertEqual(receipt.check_ids.picking_id, receipt)

        with self.assertRaises(UserError):
            receipt._action_done()

        receipt.check_ids.do_pass()
        receipt._action_done()

    def test_check_no_serial(self):
        self.product.write(
            {
                "tracking": "serial",
                "is_storable": True,
            }
        )
        picking_type_without_lot = (
            self.env["stock.picking.type"]
            .browse(self.picking_type_id)
            .copy(
                {
                    "use_create_lots": False,
                    "use_existing_lots": False,
                }
            )
        )
        self.env["quality.point"].create(
            {
                "picking_type_ids": [
                    Command.link(self.picking_type_id),
                    Command.link(picking_type_without_lot.id),
                ],
                "measure_on": "move_line",
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
            }
        )
        receipts = self.env["stock.picking"].create(
            [
                {
                    "picking_type_id": picking_type,
                    "location_id": self.location_id,
                    "location_dest_id": self.location_dest_id,
                    "move_ids": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "product_uom_qty": 5,
                                "product_uom_id": self.product.uom_id.id,
                                "location_id": self.location_id,
                                "location_dest_id": self.location_dest_id,
                            }
                        )
                    ],
                }
                for picking_type in (self.picking_type_id, picking_type_without_lot.id)
            ]
        )
        receipts.action_confirm()
        receipt, receipt_wihtout_lot = receipts

        move = receipt.move_ids
        self.assertFalse(move.move_line_ids.trace_id)
        self.assertEqual(move.move_line_ids.mapped("lot_name"), [False] * 5)
        self.assertEqual(receipt.check_quality(), True)

        move.move_line_ids[0].lot_name = "test_sn1"
        qc_wizard = Form.from_action(self.env, receipt.check_quality())
        quality_check = qc_wizard.save()
        self.assertTrue(quality_check.is_last_check)

        self.assertRecordValues(
            receipt_wihtout_lot.move_line_ids,
            [
                {"trace_id": False, "lot_name": False},
            ],
        )
        qc_wizard = Form.from_action(self.env, receipt_wihtout_lot.check_quality())
        quality_check = qc_wizard.save()
        self.assertTrue(quality_check.is_last_check)

    def test_checks_removal_on_SM_cancellation(self):
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        warehouse.reception_steps = "two_steps"

        p01, p02 = self.env["product.product"].create(
            [
                {
                    "name": name,
                    "is_storable": True,
                }
                for name in ("SuperProduct01", "SuperProduct02")
            ]
        )

        self.env["quality.point"].create(
            [
                {
                    "product_ids": [(4, product.id)],
                    "picking_type_ids": [(4, warehouse.store_type_id.id)],
                }
                for product in (p01, p02)
            ]
        )

        receipt = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": warehouse.wh_input_stock_loc_id.id,
            }
        )
        self.env["stock.move"].create(
            [
                {
                    "product_id": product.id,
                    "product_uom_qty": 1,
                    "product_uom_id": product.uom_id.id,
                    "picking_id": receipt.id,
                    "location_id": self.location_id,
                    "location_dest_id": warehouse.wh_input_stock_loc_id.id,
                }
                for product in (p01, p02)
            ]
        )
        receipt.action_confirm()
        receipt.move_ids.quantity = 1
        receipt.button_validate()

        storage_transfer = self.env["stock.picking"].search(
            [
                ("location_id", "=", warehouse.wh_input_stock_loc_id.id),
                ("picking_type_id", "=", warehouse.store_type_id.id),
            ],
            order="id desc",
            limit=1,
        )
        self.assertEqual(storage_transfer.check_ids.product_id, p01 + p02)

        receipt = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": warehouse.wh_input_stock_loc_id.id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": p01.id,
                "product_uom_qty": 1,
                "product_uom_id": p01.uom_id.id,
                "picking_id": receipt.id,
                "location_id": self.location_id,
                "location_dest_id": warehouse.wh_input_stock_loc_id.id,
            }
        )
        receipt.action_confirm()
        receipt.move_ids.quantity = 1
        receipt.button_validate()

        self.assertRecordValues(
            storage_transfer.move_ids,
            [
                {"product_id": p01.id, "product_uom_qty": 1},
                {"product_id": p02.id, "product_uom_qty": 1},
            ],
        )
        self.assertEqual(storage_transfer.check_ids.product_id, p01 + p02)

        second_transfer = self.env["stock.picking"].search(
            [
                ("location_id", "=", warehouse.wh_input_stock_loc_id.id),
                ("picking_type_id", "=", warehouse.store_type_id.id),
                ("id", "!=", storage_transfer.id),
            ],
            order="id desc",
            limit=1,
        )
        self.assertTrue(
            second_transfer, "the second receipt gets its own storage transfer"
        )
        self.assertRecordValues(
            second_transfer.move_ids,
            [
                {"product_id": p01.id, "product_uom_qty": 1},
            ],
        )
        self.assertEqual(
            second_transfer.check_ids.product_id,
            p01,
            "and its own quality check, for the product it moves",
        )

    def test_propagate_sml_lot_name(self):
        self.env["quality.point"].create(
            {
                "picking_type_ids": [(4, self.picking_type_id)],
                "measure_on": "move_line",
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
            }
        )
        self.product.write(
            {
                "is_storable": True,
                "tracking": "serial",
            }
        )

        receipt = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 1,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": receipt.id,
                "location_id": receipt.location_id.id,
                "location_dest_id": receipt.location_dest_id.id,
            }
        )
        receipt.action_confirm()
        ml = move.move_line_ids

        ml.write(
            {
                "quantity": 1,
                "lot_name": "1457",
            }
        )
        self.assertEqual(ml.check_ids.lot_name, "1457")

        ml.lot_name = "1458"
        self.assertEqual(ml.check_ids.lot_name, "1458")
        ml.check_ids.do_pass()
        receipt.button_validate()
        self.assertEqual(ml.check_ids.trace_line_id, ml.trace_id)
        self.assertEqual(ml.check_ids.trace_ids, ml.trace_id)

        self.assertEqual(
            ml.check_ids._get_check_action_name(),
            "Quality Check : Office Chair - 1.0 Units - 1458",
        )
        ml.lot_name = False
        self.assertEqual(
            ml.check_ids._get_check_action_name(),
            "Quality Check : Office Chair - 1.0 Units - 1458",
        )

    def test_update_sml_done_qty(self):
        self.env["quality.point"].create(
            {
                "product_ids": [(4, self.product.id)],
                "picking_type_ids": [(4, self.picking_type_id)],
                "measure_on": "move_line",
            }
        )

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": picking.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        picking.action_confirm()

        move.quantity = 1.0
        self.assertEqual(picking.check_ids.qty_line, 1)

        move.quantity = 0.0
        self.assertEqual(picking.check_ids.qty_line, 0)

        move.quantity = 2.0
        self.assertEqual(picking.check_ids.qty_line, 2)

    def test_quality_check_with_backorder(self):
        user = self.env["res.users"].create(
            {
                "name": "Inventory Manager",
                "login": "test",
                "email": "test@test.com",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("stock.group_stock_user").id,
                            self.env.ref("quality.group_quality_user").id,
                        ],
                    )
                ],
            }
        )

        receipt_type = self.env["stock.picking.type"].create(
            {
                "name": "Quality receipts",
                "code": "incoming",
                "sequence_code": "QCIN",
                "warehouse_id": self.env.ref("stock.picking_type_in").warehouse_id.id,
            }
        )
        self.env["quality.point"].create(
            [
                {
                    "product_ids": [(4, self.product.id)],
                    "picking_type_ids": [(4, receipt_type.id)],
                    "measure_on": "operation",
                },
                {
                    "picking_type_ids": [(4, receipt_type.id)],
                    "measure_on": "move_line",
                },
            ]
        )

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": receipt_type.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": picking.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        picking.action_confirm()
        move.quantity = 1.0
        self.assertEqual(len(picking.check_ids), 2)
        for check in picking.check_ids:
            check.do_pass()
        Form.from_action(self.env, picking.button_validate()).save().with_user(
            user
        ).process()

        self.assertEqual(picking.state, "done")
        backorder = picking.backorder_ids
        self.assertEqual(backorder.state, "assigned")
        self.assertEqual(len(backorder.check_ids), 2)
        for check in backorder.check_ids:
            check.do_pass()
        backorder.move_ids.quantity = 1.0
        backorder.with_user(user).button_validate()
        self.assertEqual(backorder.state, "done")

    def test_failure_location_move_line(self):
        self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "move_line",
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
                "failure_location_ids": [Command.link(self.failure_location.id)],
            }
        )

        self.receipt.action_confirm()
        self.assertEqual(len(self.receipt.check_ids), 2)
        action = self.receipt.check_ids.action_view_quality_check_wizard()
        wizard = (
            self.env[action["res_model"]].with_context(action["context"]).create({})
        )
        self.assertEqual(len(wizard.check_ids), 2)
        self.assertEqual(
            wizard.current_check_id.move_line_id, self.product_move.move_line_ids
        )
        action = wizard.do_pass()
        wizard = (
            self.env[action["res_model"]].with_context(action["context"]).create({})
        )
        self.assertEqual(
            wizard.current_check_id.move_line_id, self.product2_move.move_line_ids
        )
        action = wizard.do_fail()
        wizard = (
            self.env[action["res_model"]]
            .with_context(action["context"])
            .browse(action["res_id"])
        )

        self.assertEqual(wizard.qty_failed, 2)
        wizard.qty_failed = 1
        wizard.failure_location_id = self.failure_location.id
        wizard.confirm_fail()
        self.assertEqual(len(self.receipt.check_ids), 3)
        self.assertEqual(len(self.receipt.move_ids), 3)
        self.assertRecordValues(
            self.receipt.check_ids,
            [
                {
                    "quality_state": "pass",
                    "product_id": self.product.id,
                    "qty_line": 2,
                    "failure_location_id": False,
                },
                {
                    "quality_state": "fail",
                    "product_id": self.product_2.id,
                    "qty_line": 1,
                    "failure_location_id": self.failure_location.id,
                },
                {
                    "quality_state": "pass",
                    "product_id": self.product_2.id,
                    "qty_line": 1,
                    "failure_location_id": False,
                },
            ],
        )

    def test_failure_location_product(self):
        self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "product",
                "product_ids": [Command.link(self.product_2.id)],
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
                "failure_location_ids": [Command.link(self.failure_location.id)],
            }
        )

        self.receipt.action_confirm()
        self.assertEqual(len(self.receipt.check_ids), 1)
        action = self.receipt.check_ids.action_view_quality_check_wizard()
        wizard = (
            self.env[action["res_model"]].with_context(action["context"]).create({})
        )
        self.assertEqual(len(wizard.check_ids), 1)
        self.assertEqual(wizard.check_ids.product_id, self.product_2)
        action = wizard.do_fail()
        wizard = (
            self.env[action["res_model"]]
            .with_context(action["context"])
            .browse(action["res_id"])
        )

        wizard.failure_location_id = self.failure_location.id
        wizard.confirm_fail()
        self.assertRecordValues(
            self.receipt.check_ids,
            [
                {
                    "quality_state": "fail",
                    "product_id": self.product_2.id,
                    "failure_location_id": self.failure_location.id,
                },
            ],
        )
        self.assertRecordValues(
            self.receipt.move_ids,
            [
                {
                    "product_id": self.product.id,
                    "location_dest_id": self.receipt.location_dest_id.id,
                },
                {
                    "product_id": self.product_2.id,
                    "location_dest_id": self.failure_location.id,
                },
            ],
        )

    def test_failure_location_operation(self):
        self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "operation",
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
                "failure_location_ids": [Command.link(self.failure_location.id)],
            }
        )

        self.receipt.action_confirm()
        self.assertEqual(len(self.receipt.check_ids), 1)
        action = self.receipt.check_ids.action_view_quality_check_wizard()
        wizard = (
            self.env[action["res_model"]].with_context(action["context"]).create({})
        )
        self.assertEqual(len(wizard.check_ids), 1)
        action = wizard.do_fail()
        wizard = (
            self.env[action["res_model"]]
            .with_context(action["context"])
            .browse(action["res_id"])
        )

        wizard.failure_location_id = self.failure_location.id
        wizard.confirm_fail()
        self.assertEqual(len(self.receipt.move_ids), 2)
        self.assertEqual(self.receipt.location_dest_id.id, self.location_dest_id)
        self.assertEqual(self.receipt.move_ids.location_dest_id, self.failure_location)
        self.assertRecordValues(
            self.receipt.check_ids,
            [
                {
                    "quality_state": "fail",
                    "product_id": False,
                    "picking_id": self.receipt.id,
                    "failure_location_id": self.failure_location.id,
                },
            ],
        )

    def test_failure_location_lot(self):
        product_lot = self.env["product.product"].create(
            {
                "name": "product lot",
                "is_storable": True,
                "tracking": "lot",
            }
        )
        self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "measure_on": "move_line",
                "product_ids": [Command.link(product_lot.id)],
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
                "failure_location_ids": [Command.link(self.failure_location.id)],
            }
        )
        receipt = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "product_id": product_lot.id,
                "product_uom_qty": 4,
                "picking_id": receipt.id,
                "location_id": receipt.location_id.id,
                "location_dest_id": receipt.location_dest_id.id,
            }
        )

        receipt.action_confirm()
        self.assertEqual(len(receipt.check_ids), 1)
        move.quantity = 0
        move.move_line_ids = [
            Command.create(
                {
                    "product_id": product_lot.id,
                    "product_uom_id": product_lot.uom_id.id,
                    "quantity": 2,
                    "picking_id": receipt.id,
                    "lot_name": "lot1",
                }
            ),
            Command.create(
                {
                    "product_id": product_lot.id,
                    "product_uom_id": product_lot.uom_id.id,
                    "quantity": 2,
                    "picking_id": receipt.id,
                    "lot_name": "lot2",
                }
            ),
        ]

        self.assertEqual(len(receipt.check_ids), 2)
        action = receipt.check_ids.action_view_quality_check_wizard()
        wizard = Form.from_action(
            self.env, receipt.check_ids.action_view_quality_check_wizard()
        ).save()
        self.assertEqual(len(wizard.check_ids), 2)
        self.assertEqual(wizard.current_check_id.move_line_id, move.move_line_ids[0])
        action = wizard.do_pass()
        wizard = (
            self.env[action["res_model"]].with_context(action["context"]).create({})
        )
        self.assertEqual(wizard.current_check_id.move_line_id, move.move_line_ids[1])
        action = wizard.do_fail()
        wizard = (
            self.env[action["res_model"]]
            .with_context(action["context"])
            .browse(action["res_id"])
        )

        self.assertEqual(wizard.qty_failed, 2)
        wizard.failure_location_id = self.failure_location.id
        wizard.confirm_fail()
        self.assertEqual(len(receipt.check_ids), 2)
        self.assertEqual(len(receipt.move_ids), 2)
        self.assertRecordValues(
            receipt.move_ids,
            [
                {
                    "product_id": product_lot.id,
                    "product_uom_qty": 2,
                    "quantity": 2,
                    "location_dest_id": receipt.location_dest_id.id,
                },
                {
                    "product_id": product_lot.id,
                    "product_uom_qty": 2,
                    "quantity": 2,
                    "location_dest_id": self.failure_location.id,
                },
            ],
        )
        self.assertRecordValues(
            receipt.check_ids,
            [
                {
                    "quality_state": "pass",
                    "product_id": product_lot.id,
                    "qty_line": 2,
                    "failure_location_id": False,
                },
                {
                    "quality_state": "fail",
                    "product_id": product_lot.id,
                    "qty_line": 2,
                    "failure_location_id": self.failure_location.id,
                },
            ],
        )
        self.assertRecordValues(
            receipt.move_ids,
            [
                {
                    "picked": False,
                    "product_id": product_lot.id,
                    "quantity": 2,
                    "location_dest_id": receipt.location_dest_id.id,
                },
                {
                    "picked": False,
                    "product_id": product_lot.id,
                    "quantity": 2,
                    "location_dest_id": self.failure_location.id,
                },
            ],
        )
        receipt.button_validate()
        self.assertEqual(receipt.state, "done")
        self.assertEqual(receipt.move_ids.mapped("state"), ["done", "done"])

    def test_qp_with_product_ctg(self):
        product_cat_2 = self.product_category_base.copy({"name": "cat2"})
        product_a = self.env["product.product"].create(
            {
                "name": "Product A",
                "is_storable": True,
                "categ_id": product_cat_2.id,
            }
        )
        product_b = self.env["product.product"].create(
            {
                "name": "Product B",
                "is_storable": True,
                "categ_id": self.product_category_base.id,
            }
        )
        self.env["quality.point"].create(
            {
                "title": "QP1",
                "product_category_ids": [
                    (4, product_cat_2.id),
                    (4, self.product_category_base.id),
                ],
                "picking_type_ids": [(4, self.picking_type_id)],
                "measure_on": "move_line",
            }
        )
        self.env["quality.point"].create(
            {
                "title": "QP2",
                "product_category_ids": [(4, self.product_category_base.id)],
                "picking_type_ids": [(4, self.picking_type_id)],
                "measure_on": "move_line",
            }
        )
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": product_a.id,
                "product_uom_qty": 1,
                "picking_id": picking.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": product_b.id,
                "product_uom_qty": 1,
                "picking_id": picking.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        picking.action_confirm()
        self.assertEqual(len(picking.check_ids), 3)

    def test_qc_with_partial_reception(self):
        self.env["quality.point"].create(
            {
                "picking_type_ids": [self.picking_type_id],
                "test_type_id": self.env.ref("quality_control.test_type_measure").id,
                "measure_on": "move_line",
            }
        )
        (self.product_2 | self.product_3 | self.product_4).is_storable = True
        (self.product_2 | self.product_4).tracking = "serial"
        picking_in = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        move_tracked_product_a = self.env["stock.move"].create(
            {
                "product_id": self.product_2.id,
                "product_uom_qty": 1,
                "product_uom_id": self.product_2.uom_id.id,
                "picking_id": picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        move_untracked = self.env["stock.move"].create(
            {
                "product_id": self.product_3.id,
                "product_uom_qty": 1,
                "product_uom_id": self.product_3.uom_id.id,
                "picking_id": picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        move_tracked_product_b = self.env["stock.move"].create(
            {
                "product_id": self.product_4.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product_4.uom_id.id,
                "picking_id": picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        picking_in.action_confirm()
        self.assertEqual(len(picking_in.check_ids), 4)
        self.assertTrue(picking_in.quality_check_todo)
        move_untracked.quantity = 1
        move_untracked.picked = True
        untracked_check_ids = picking_in.check_ids.filtered(
            lambda qc: qc.product_id == self.product_3
        )
        untracked_check_ids.do_pass()
        self.assertEqual(untracked_check_ids.quality_state, "pass")
        move_tracked_product_a.quantity = 0
        move_tracked_product_b.quantity = 2
        for index, line in enumerate(move_tracked_product_b.move_line_ids, start=1):
            line.lot_name = str(index)
        tracked_check_ids_to_do = picking_in.check_ids.filtered(
            lambda qc: qc.product_id == self.product_4
        )
        self.env.invalidate_all()
        qc_wizard = Form.from_action(self.env, picking_in.check_quality()).save()
        self.assertEqual(qc_wizard.check_ids, tracked_check_ids_to_do)
        tracked_check_ids_to_do[0].do_pass()
        self.assertEqual(tracked_check_ids_to_do[0].quality_state, "pass")
        tracked_check_ids_to_do = tracked_check_ids_to_do.filtered(
            lambda qc: qc.quality_state == "none"
        )
        qc_wizard = Form.from_action(self.env, picking_in.check_quality()).save()
        self.assertEqual(qc_wizard.check_ids, tracked_check_ids_to_do)

        move_tracked_product_b.picked = True
        move_tracked_product_a.quantity = 1
        move_tracked_product_a.move_line_ids.lot_name = "1"
        self.assertFalse(move_tracked_product_a.picked)
        qc_wizard = Form.from_action(self.env, picking_in.check_quality()).save()
        self.assertEqual(
            qc_wizard.check_ids,
            picking_in.check_ids.filtered(lambda qc: qc.quality_state == "none"),
        )

        wizard = Form.from_action(self.env, picking_in.button_validate()).save()
        qc_wizard = Form.from_action(self.env, wizard.process()).save()
        self.assertEqual(qc_wizard.check_ids, tracked_check_ids_to_do)
        qc_wizard.do_pass()
        backorder = picking_in.backorder_ids
        self.assertEqual(picking_in.state, "done")
        self.assertEqual(len(backorder.check_ids), 1)
        backorder.check_ids.do_pass()
        self.assertEqual(backorder.check_ids.quality_state, "pass")

    def test_quality_check_with_scrapped_moves(self):
        self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "test_type_id": self.env.ref("quality_control.test_type_measure").id,
                "measure_on": "operation",
            }
        )
        self.product_3.is_storable = True
        picking_in = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product_3.id,
                "product_uom_qty": 2,
                "product_uom_id": self.product_3.uom_id.id,
                "picking_id": picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        picking_in.action_confirm()
        self.assertEqual(len(picking_in.check_ids), 1)
        action = picking_in.check_ids.action_view_quality_check_wizard()
        wizard = Form(
            self.env[action["res_model"]].with_context(action["context"])
        ).save()
        self.assertEqual(len(wizard.check_ids), 1)
        wizard.do_fail()
        self.assertEqual(picking_in.check_ids.quality_state, "fail")

        scrap = self.env["stock.scrap"].create(
            {
                "picking_id": picking_in.id,
                "product_id": self.product_3.id,
                "product_uom_id": self.product_3.uom_id.id,
                "scrap_qty": 5.0,
            }
        )
        scrap._action_done()
        self.assertEqual(len(picking_in.move_ids), 2)
        self.assertEqual(len(picking_in.check_ids), 1)

    def test_qc_by_product_with_partial_reception(self):
        self.env["quality.point"].create(
            {
                "picking_type_ids": [self.picking_type_id],
                "test_type_id": self.env.ref("quality_control.test_type_measure").id,
                "measure_on": "product",
            }
        )
        picking_in = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "product_id": self.product_2.id,
                "product_uom_qty": 10,
                "product_uom_id": self.product_2.uom_id.id,
                "picking_id": picking_in.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        picking_in.action_confirm()
        self.assertEqual(len(picking_in.check_ids), 1)
        self.assertTrue(picking_in.quality_check_todo)
        move.quantity = 5
        move.picked = True
        action_quality_check = (
            Form.from_action(self.env, picking_in.button_validate()).save().process()
        )
        Form.from_action(self.env, action_quality_check).save().do_pass()
        self.assertEqual(len(picking_in.check_ids), 1)
        self.assertEqual(picking_in.check_ids.quality_state, "pass")
        backorder = picking_in.backorder_ids
        self.assertEqual(len(backorder.check_ids), 1)
        backorder.move_ids.quantity = 3
        backorder.move_ids.picked = True
        backorder.action_split_transfer()
        self.assertEqual(len(backorder.check_ids), 1)
        backorder.check_ids.do_pass()
        self.assertEqual(backorder.check_ids.quality_state, "pass")
        backorder_2 = backorder.backorder_ids
        self.assertEqual(len(backorder_2.check_ids), 1)
        self.assertNotIn(backorder_2.check_ids, (picking_in + backorder).check_ids)

    def test_quality_check_on_receipt_with_additional_move_lines(self):
        self.env["quality.point"].create(
            [
                {
                    "title": "Check product 2",
                    "measure_on": "operation",
                    "product_ids": [Command.link(self.product_2.id)],
                    "picking_type_ids": [Command.link(self.picking_type_id)],
                },
            ]
        )

        receipt = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 2,
                            "product_uom_id": self.product.uom_id.id,
                            "location_id": self.location_id,
                            "location_dest_id": self.location_dest_id,
                        }
                    )
                ],
            }
        )
        receipt.action_confirm()
        self.assertRecordValues(
            receipt,
            [
                {
                    "state": "assigned",
                    "quality_check_todo": False,
                }
            ],
        )
        self.env["stock.move.line"].create(
            {
                "product_id": self.product_2.id,
                "picking_id": receipt.id,
                "quantity": 3,
            }
        )
        self.assertRecordValues(
            receipt.move_ids.sorted("quantity"),
            [
                {"product_id": self.product.id, "quantity": 2.0, "state": "assigned"},
                {"product_id": self.product_2.id, "quantity": 3.0, "state": "assigned"},
            ],
        )
        receipt.invalidate_recordset()
        self.assertRecordValues(
            receipt,
            [
                {
                    "state": "assigned",
                    "quality_check_todo": True,
                }
            ],
        )
        self.assertEqual(len(receipt.check_ids), 1)
        receipt.check_ids.do_pass()
        receipt.button_validate()
        self.assertEqual(len(receipt.check_ids), 1)

    def test_quality_check_on_delivery_with_additional_move_lines(self):
        out_type_id = self.env.ref("stock.warehouse0").out_type_id
        self.env["quality.point"].create(
            [
                {
                    "title": "Check product 2",
                    "measure_on": "operation",
                    "product_ids": [Command.link(self.product_2.id)],
                    "picking_type_ids": [Command.link(out_type_id.id)],
                },
            ]
        )

        delivery = self.env["stock.picking"].create(
            {
                "picking_type_id": out_type_id.id,
                "location_id": self.location_dest_id,
                "location_dest_id": self.ref("stock.stock_location_customers"),
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 2,
                            "product_uom_id": self.product.uom_id.id,
                            "location_id": self.location_dest_id,
                            "location_dest_id": self.ref(
                                "stock.stock_location_customers"
                            ),
                        }
                    )
                ],
            }
        )
        delivery.action_confirm()
        self.assertRecordValues(
            delivery,
            [
                {
                    "state": "assigned",
                    "quality_check_todo": False,
                }
            ],
        )
        self.env["stock.move.line"].create(
            {
                "product_id": self.product_2.id,
                "picking_id": delivery.id,
                "quantity": 3,
            }
        )
        self.assertRecordValues(
            delivery.move_ids.sorted("quantity"),
            [
                {"product_id": self.product.id, "quantity": 2.0, "state": "assigned"},
                {"product_id": self.product_2.id, "quantity": 3.0, "state": "assigned"},
            ],
        )
        delivery.invalidate_recordset()
        self.assertRecordValues(
            delivery,
            [
                {
                    "state": "assigned",
                    "quality_check_todo": True,
                }
            ],
        )
        self.assertEqual(len(delivery.check_ids), 1)
        delivery.check_ids.do_pass()
        delivery.button_validate()
        self.assertEqual(len(delivery.check_ids), 1)

    def test_zero_qty_failed_quantity_check(self):
        self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "product_ids": [Command.link(self.product.id)],
                "measure_on": "move_line",
                "test_type_id": self.env.ref("quality_control.test_type_passfail").id,
            }
        )

        self.receipt.action_confirm()
        self.assertEqual(len(self.receipt.check_ids), 1)
        action = self.receipt.check_ids.action_view_quality_check_wizard()
        wizard = (
            self.env[action["res_model"]].with_context(action["context"]).create({})
        )
        self.assertEqual(
            wizard.current_check_id.move_line_id, self.product_move.move_line_ids
        )
        action = wizard.do_fail()
        wizard = (
            self.env[action["res_model"]]
            .with_context(action["context"])
            .browse(action["res_id"])
        )

        self.assertEqual(wizard.qty_failed, 2)
        wizard.qty_failed = 0
        wizard.confirm_fail()
        self.assertEqual(len(self.receipt.check_ids), 1)
        self.assertEqual(len(self.receipt.move_ids), 2)
        self.assertRecordValues(
            self.receipt.check_ids,
            [
                {"quality_state": "pass", "product_id": self.product.id, "qty_line": 2},
            ],
        )

    def test_quality_check_creation_multi_company(self):
        out_picking_type = self.env["stock.picking.type"].search(
            [("company_id", "=", self.env.company.id), ("code", "=", "outgoing")],
            limit=1,
        )
        self.env["quality.point"].create(
            [
                {
                    "title": "Delivery QCP",
                    "picking_type_ids": out_picking_type.ids,
                },
                {
                    "measure_on": "move_line",
                    "title": "Delivery QCP",
                    "picking_type_ids": out_picking_type.ids,
                },
            ]
        )
        customer_location = self.env["stock.location"].search(
            [("usage", "=", "customer")], limit=1
        )
        picking_out = self.env["stock.picking"].create(
            {
                "picking_type_id": out_picking_type.id,
                "partner_id": self.partner_id,
                "location_id": out_picking_type.default_location_src_id.id,
                "location_dest_id": customer_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 2,
                            "product_uom_id": self.product.uom_id.id,
                            "location_id": out_picking_type.default_location_src_id.id,
                            "location_dest_id": customer_location.id,
                        }
                    )
                ],
            }
        )
        new_company = self.env["res.company"].create(
            {
                "name": "New Company",
            }
        )
        picking_out.with_company(new_company).action_confirm()
        self.assertRecordValues(
            picking_out,
            [
                {
                    "state": "assigned",
                    "quality_check_todo": True,
                }
            ],
        )
        self.assertTrue(picking_out.check_ids)

    def test_receipt_validation_triggers_serial_number_label_print(self):
        self.env.user.group_ids |= self.env.ref("stock.group_production_lot")
        picking_type = self.env["stock.picking.type"].browse(self.picking_type_id)
        picking_type.auto_print_lot_labels = True
        self.product.write(
            {
                "is_storable": True,
                "tracking": "serial",
            }
        )
        self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(picking_type.id)],
                "product_ids": [Command.link(self.product.id)],
                "measure_on": "product",
                "test_type_id": self.ref("quality_control.test_type_passfail"),
            }
        )
        receipts = self.env["stock.picking"].create(
            [
                {
                    "picking_type_id": picking_type.id,
                    "location_id": self.location_id,
                    "location_dest_id": self.location_dest_id,
                    "move_ids": [
                        Command.create(
                            {
                                "product_id": product.id,
                                "product_uom_qty": 1,
                                "product_uom_id": product.uom_id.id,
                            }
                        )
                    ],
                }
                for product in [self.product, self.product_2]
            ]
        )
        receipts[0].action_confirm()

        ml = receipts[0].move_ids.move_line_ids
        ml.write(
            {
                "quantity": 1,
                "lot_name": "1457",
            }
        )
        self.assertEqual(ml.lot_name, "1457")

        action_quality_check = Form.from_action(
            self.env, receipts.button_validate()
        ).save()
        validate_res = action_quality_check.do_pass()

        self.assertEqual(validate_res.get("type"), "ir.actions.client")
        self.assertEqual(validate_res.get("tag", False), "do_multi_print")

        self.assertRecordValues(receipts, [{"state": "done"}, {"state": "done"}])

    def test_product_quality_point_smart_button_count(self):
        quality_point = self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
            }
        )

        self.assertEqual(self.product.quality_control_point_qty, 1)

        quality_point.active = False
        self.product.invalidate_recordset(fnames=["quality_control_point_qty"])
        self.assertEqual(self.product.quality_control_point_qty, 0)

    def test_quality_point_stat_button_from_product_view(self):
        quality_point = self.env["quality.point"].create(
            {
                "product_ids": [Command.link(self.product.id)],
                "measure_on": "product",
                "product_category_ids": [Command.link(self.product_category_base.id)],
            }
        )
        action = self.product.action_view_quality_control_points()
        self.assertTrue(action["views"][0][0])
        result = self.env["quality.point"].search(action["domain"])
        self.assertEqual(result, quality_point)

    def test_fail_quality_check_per_qty_for_serial_product(self):
        self.product.write(
            {
                "is_storable": True,
                "tracking": "serial",
            }
        )
        self.env["quality.point"].create(
            {
                "picking_type_ids": [Command.link(self.picking_type_id)],
                "product_ids": self.product.ids,
                "measure_on": "move_line",
                "test_type_id": self.ref("quality_control.test_type_passfail"),
            }
        )
        self.receipt.action_confirm()
        self.assertEqual(len(self.receipt.check_ids), 2)

        wizard = self.receipt.check_ids.action_view_quality_check_wizard()
        quality_check = Form.from_action(self.env, wizard).save()
        next_wizard = quality_check.do_fail()
        next_quality_check = Form.from_action(self.env, next_wizard).save()
        next_quality_check.do_fail()

        self.assertRecordValues(
            self.receipt.check_ids,
            [
                {
                    "quality_state": "fail",
                    "product_id": self.product.id,
                    "qty_failed": 1.0,
                },
                {
                    "quality_state": "fail",
                    "product_id": self.product.id,
                    "qty_failed": 1.0,
                },
            ],
        )
