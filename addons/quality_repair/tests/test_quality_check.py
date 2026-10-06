from odoo import Command
from odoo.tests import tagged

from odoo.addons.repair.tests.test_repair import TestRepairCommon


@tagged("post_install", "-at_install")
class TestQualityRepair(TestRepairCommon):
    def test_repair_w_lot_and_quality_check(self):
        """Test quality check creation and flow on repair order"""

        self.env["quality.point"].create(
            {
                "name": "QP1",
                "measure_on": "product",
                "picking_type_ids": [
                    Command.set([self.stock_warehouse.repair_type_id.id])
                ],
            }
        )
        repair = self.env["repair.order"].create(
            {
                "product_id": self.product_storable_lot.id,
                "partner_id": self.res_partner_1.id,
            }
        )
        quant = self.create_quant(self.product_storable_lot, 1)
        quant.action_apply_inventory()
        repair.trace_id = quant.trace_id
        repair.action_validate()
        self.assertEqual(repair.state, "confirmed")
        # Quality check should be created at repair confirmation
        qc = repair.quality_check_ids
        lot_1 = repair.trace_id
        self.assertEqual(len(qc), 1)
        self.assertEqual(lot_1.ids, qc.trace_ids.ids)
        # The form links a check to one business document and hides the rest.
        # This assertion lives here rather than in `quality_mrp`, which cannot
        # see `hide_repair_id` at all.
        self.assertFalse(qc.hide_repair_id)
        self.assertTrue(qc.hide_picking_id)
        # quality_repair does not depend on quality_mrp, which declares
        # hide_production_id.
        if "hide_production_id" in qc._fields:
            self.assertTrue(qc.hide_production_id)

        # An operation-level check grades the transfer, not a lot, and the
        # creation path never gives it one.  A later `trace_id` write used to,
        # so a check carried a lot only if the lot changed after confirmation
        # -- and `stock.lot.quality_check_qty` counts by `trace_ids`.
        operation_point = self.env["quality.point"].create(
            {
                "name": "QP-op",
                "measure_on": "operation",
                "picking_type_ids": [
                    Command.set([self.stock_warehouse.repair_type_id.id])
                ],
            }
        )
        self.assertTrue(operation_point)
        second = self.env["repair.order"].create(
            {
                "product_id": self.product_storable_lot.id,
                "partner_id": self.res_partner_1.id,
                "trace_id": lot_1.id,
                "picking_type_id": self.stock_warehouse.repair_type_id.id,
                "state": "confirmed",
            }
        )
        operation_checks = second.quality_check_ids.filtered(
            lambda c: c.measure_on == "operation"
        )
        self.assertTrue(operation_checks)
        self.assertFalse(operation_checks.trace_ids)
        second.trace_id = quant.trace_id
        self.assertFalse(
            operation_checks.trace_ids,
            "an operation check must not pick up the repair's lot",
        )

        # Reset repair lot
        repair.trace_id = False
        self.assertFalse(qc.trace_ids)
        repair.action_repair_start()
        repair.action_generate_serial()
        lot_2 = repair.trace_id
        self.assertNotEqual(lot_1, lot_2)
        self.assertEqual(lot_2.ids, qc.trace_ids.ids)

        # 'Pass' Quality Checks of repair order.
        qc.do_pass()
        self.assertEqual(qc.quality_state, "pass")
        repair.action_repair_end()
        self.assertEqual(repair.state, "done")

    def test_repair_multi_record_create_write(self):
        """Test that creating and writing multiple repair orders works as expected."""
        repairs = self.env["repair.order"].create(
            [
                {
                    "product_id": self.product_storable_lot.id,
                    "partner_id": self.res_partner_1.id,
                },
                {
                    "product_id": self.product_storable_lot.id,
                    "partner_id": self.res_partner_1.id,
                },
            ]
        )
        self.assertEqual(len(repairs), 2, "Model should create two repair orders.")

        repairs.write({"name": "test"})
        self.assertEqual(
            set(repairs.mapped("name")),
            {"test"},
            "Model should write the name on both records.",
        )
