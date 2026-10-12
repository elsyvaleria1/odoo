from odoo import Command
from odoo.tests import Form

from odoo.addons.mrp_workorder.tests.common import TestMrpWorkorderCommon


class TestWorkOrderDependencies(TestMrpWorkorderCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.wkct1 = cls.env["mrp.workcenter"].create(
            {
                "name": "Workcenter#1",
            }
        )
        cls.wkct2 = cls.env["mrp.workcenter"].create(
            {
                "name": "Workcenter#2",
            }
        )
        cls.wkct3 = cls.env["mrp.workcenter"].create(
            {
                "name": "Workcenter#3",
            }
        )
        cls.finished = cls.env["product.product"].create(
            {
                "name": "Finished Product",
                "is_storable": True,
            }
        )
        cls.component1 = cls.env["product.product"].create(
            {
                "name": "Component#1",
                "is_storable": True,
            }
        )
        cls.component2 = cls.env["product.product"].create(
            {
                "name": "Component#2",
                "is_storable": True,
            }
        )
        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_id": cls.finished.id,
                "product_tmpl_id": cls.finished.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    Command.create({"product_id": cls.component1.id, "product_qty": 1}),
                    Command.create({"product_id": cls.component2.id, "product_qty": 2}),
                ],
                "operation_ids": [
                    Command.create(
                        {"name": "Operation#A", "workcenter_id": cls.wkct1.id}
                    ),
                    Command.create(
                        {"name": "Operation#B", "workcenter_id": cls.wkct2.id}
                    ),
                    Command.create(
                        {"name": "Operation#C", "workcenter_id": cls.wkct3.id}
                    ),
                ],
                "allow_operation_dependencies": True,
            }
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.component1, cls.stock_location, 100
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.component2, cls.stock_location, 100
        )

    def _workorders_by_operation(self, mo):
        return tuple(
            mo.workorder_ids.filtered_domain([("operation_id", "=", operation.id)])
            for operation in self.bom.operation_ids
        )

    def test_parallel_workorders(self):

        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.finished
        mo_form.product_qty = 2.0
        mo = mo_form.save()
        mo.action_confirm()

        self.assertEqual(
            mo.workorder_ids[0].state, "ready", "All workorders should be ready."
        )
        self.assertEqual(
            mo.workorder_ids[1].state, "ready", "All workorders should be ready."
        )
        self.assertEqual(
            mo.workorder_ids[2].state, "ready", "All workorders should be ready."
        )

    def test_stepped_workorders(self):

        self.bom.operation_ids[0].blocked_by_operation_ids = [
            Command.link(self.bom.operation_ids[2].id)
        ]

        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.finished
        mo_form.product_qty = 2.0
        mo = mo_form.save()
        mo.action_confirm()
        wo1, wo2, wo3 = self._workorders_by_operation(mo)
        self.assertEqual(
            wo1.state,
            "blocked",
            "Workorder for Operation-A should be Waiting for another WO (the 3rd).",
        )
        self.assertEqual(
            wo2.state, "ready", "Workorder for Operation-B should be ready."
        )
        self.assertEqual(
            wo3.state, "ready", "Workorder for Operation-C should be ready."
        )
        mo.button_plan()
        wo2.button_start()
        wo2.qty_producing = 2
        wo2.record_production()
        self.assertEqual(
            wo1.state,
            "blocked",
            "Workorder for Operation-A should STILL be Waiting for another WO (the 3rd).",
        )
        wo3.button_start()
        wo3.qty_producing = 2
        wo3.record_production()
        self.assertEqual(
            wo1.state,
            "ready",
            "Workorder for Operation-A can be started, as its predecessors are now done.",
        )

    def test_propagate_quantity_on_backorders_with_stepped_workorders(self):

        self.bom.operation_ids[0].blocked_by_operation_ids = [
            Command.link(self.bom.operation_ids[2].id)
        ]

        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.finished
        mo_form.product_qty = 20
        mo = mo_form.save()

        self.assertEqual(mo.state, "draft")
        mo.action_confirm()

        wo_1, wo_2, wo_3 = self._workorders_by_operation(mo)
        self.assertEqual(mo.state, "confirmed")
        self.assertEqual(wo_1.state, "blocked")
        self.assertEqual(wo_2.state, "ready")
        self.assertEqual(wo_3.state, "ready")

        wo_2.button_start()
        wo_2.qty_producing = 20
        self.assertEqual(mo.state, "progress")
        wo_2.button_finish()

        wo_3.button_start()
        wo_3.qty_producing = 10
        wo_3.button_finish()

        wo_1.button_start()
        wo_1.qty_producing = 5
        wo_1.button_finish()

        self.assertEqual(mo.state, "to_close")
        mo.button_mark_done()

        bo = self.env["wizard.mrp.production.produce.partial"].create(
            {
                "mrp_production_backorder_line_ids": [
                    Command.create({"mrp_production_id": mo.id, "to_backorder": True})
                ]
            }
        )
        bo.action_backorder()

        self.assertEqual(mo.state, "done")

        mo_2 = mo.production_group_id.production_ids - mo
        wo_4, wo_5, wo_6 = self._workorders_by_operation(mo_2)

        self.assertEqual(wo_4.state, "ready")
        self.assertEqual(wo_5.state, "cancel")
        self.assertEqual(wo_6.state, "ready")

        wo_6.button_start()
        wo_6.qty_producing = 10
        self.assertEqual(mo_2.state, "progress")
        wo_6.button_finish()

        wo_4.button_start()
        wo_4.qty_producing = 5
        wo_4.button_finish()

        self.assertEqual(mo_2.state, "to_close")
        mo_2.button_mark_done()

        bo = self.env["wizard.mrp.production.produce.partial"].create(
            {
                "mrp_production_backorder_line_ids": [
                    Command.create({"mrp_production_id": mo_2.id, "to_backorder": True})
                ]
            }
        )
        bo.action_backorder()

        self.assertEqual(mo_2.state, "done")

        mo_3 = mo.production_group_id.production_ids - (mo | mo_2)
        wo_7, wo_8, wo_9 = self._workorders_by_operation(mo_3)

        self.assertEqual(wo_7.state, "ready")
        self.assertEqual(wo_8.state, "cancel")
        self.assertEqual(wo_9.state, "cancel")

        wo_7.button_start()
        wo_7.qty_producing = 10
        self.assertEqual(mo_3.state, "progress")
        wo_7.button_finish()

        self.assertEqual(mo_3.state, "to_close")
        mo_3.button_mark_done()
        self.assertEqual(mo_3.state, "done")

    def test_allow_operation_dependency_with_deleted_workorder(self):
        self.bom.operation_ids[1].blocked_by_operation_ids = [
            Command.link(self.bom.operation_ids[0].id)
        ]
        self.bom.operation_ids[2].blocked_by_operation_ids = [
            Command.link(self.bom.operation_ids[1].id)
        ]

        mo_form = Form(self.env["mrp.production"])
        mo_form.product_id = self.finished
        mo_form.product_qty = 20
        mo = mo_form.save()

        self.assertEqual(mo.state, "draft")

        wo_1, wo_2, wo_3 = self._workorders_by_operation(mo)

        wo_2.unlink()
        mo.action_confirm()

        self.assertEqual(wo_1.state, "ready")
        self.assertEqual(wo_3.state, "ready")

        wo_1.button_start()
        wo_1.button_finish()

        wo_3.button_start()
        wo_3.button_finish()

        self.assertEqual(mo.state, "to_close")
        mo.button_mark_done()
        self.assertEqual(mo.state, "done")
        self.assertEqual(
            mo.workorder_ids.operation_id,
            self.bom.operation_ids[0] | self.bom.operation_ids[2],
        )
