from odoo import Command
from odoo.tests import tagged

from odoo.addons.repair.tests.test_repair import TestRepairCommon


@tagged("post_install", "-at_install")
class TestQualityRepair(TestRepairCommon):
    def test_repair_w_lot_and_quality_check(self):

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
        qc = repair.quality_check_ids
        lot_1 = repair.trace_id
        self.assertEqual(len(qc), 1)
        self.assertEqual(lot_1.ids, qc.trace_ids.ids)
        self.assertFalse(qc.hide_repair_id)
        self.assertTrue(qc.hide_picking_id)
        if "hide_production_id" in qc._fields:
            self.assertTrue(qc.hide_production_id)

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

        repair.trace_id = False
        self.assertFalse(qc.trace_ids)
        repair.action_repair_start()
        repair.action_generate_serial()
        lot_2 = repair.trace_id
        self.assertNotEqual(lot_1, lot_2)
        self.assertEqual(lot_2.ids, qc.trace_ids.ids)

        qc.do_pass()
        self.assertEqual(qc.quality_state, "pass")
        repair.action_repair_end()
        self.assertEqual(repair.state, "done")

    def test_repair_multi_record_create_write(self):
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
