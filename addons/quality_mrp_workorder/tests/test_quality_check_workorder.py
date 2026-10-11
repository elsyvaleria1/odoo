import logging

from odoo import Command
from odoo.tests import Form, HttpCase, tagged

from odoo.addons.mrp.tests.common import TestMrpCommon
from odoo.addons.mrp_workorder.tests import test_tablet_client_action

_logger = logging.getLogger(__name__)


class TestQualityCheckWorkorder(TestMrpCommon):
    def test_01_quality_check_with_component_consumed_in_operation(self):
        component = self.env["product.product"].create(
            {
                "name": "consumable component",
                "type": "consu",
            }
        )
        bom = self.bom_2.copy()
        bom.bom_line_ids[0].product_id = component

        bom.bom_line_ids[0].operation_id = bom.operation_ids[0]

        self.env["quality.point"].create(
            {
                "product_ids": [],
                "picking_type_ids": [self.picking_type_manu.id],
                "measure_on": "product",
            }
        )

        production_form = Form(self.env["mrp.production"])
        production_form.product_id = bom.product_id
        production_form.bom_id = bom
        production_form.product_qty = 5.0
        production = production_form.save()
        production.action_confirm()
        production.qty_producing = 3.0

        self.assertEqual(
            len(
                production.check_ids.filtered(
                    lambda qc: qc.product_id == production.product_id
                )
            ),
            1,
        )
        self.assertEqual(len(production.check_ids), 1)

    def test_register_consumed_materials(self):
        finished = self.bom_4.product_id
        component = self.bom_4.bom_line_ids.product_id
        (finished | component).write(
            {
                "is_storable": True,
                "tracking": "serial",
            }
        )

        finished_sn, component_sn = self.env["product.trace"].create(
            [
                {
                    "name": p.name,
                    "product_id": p.id,
                }
                for p in (finished, component)
            ]
        )
        self.env["stock.quant"]._update_available_quantity(
            component, self.stock_location, 1, trace_id=component_sn
        )

        type_register_materials = self.env.ref(
            "mrp_workorder.test_type_register_consumed_materials"
        )
        operation = self.env["mrp.routing.workcenter"].create(
            {
                "name": "Super Operation",
                "bom_id": self.bom_4.id,
                "workcenter_id": self.workcenter_2.id,
                "quality_point_ids": [
                    Command.create(
                        {
                            "product_ids": [Command.link(finished.id)],
                            "picking_type_ids": [
                                Command.link(self.picking_type_manu.id)
                            ],
                            "test_type_id": type_register_materials.id,
                            "component_id": component.id,
                            "bom_id": self.bom_4.id,
                            "measure_on": "operation",
                        }
                    )
                ],
            }
        )
        self.bom_4.operation_ids = [(6, 0, operation.ids)]

        mo_form = Form(self.env["mrp.production"])
        mo_form.bom_id = self.bom_4
        mo = mo_form.save()
        mo.action_confirm()

        mo_form = Form(mo)
        mo_form.trace_producing_ids.set(finished_sn)
        mo = mo_form.save()

        self.assertEqual(mo.workorder_ids.finished_trace_ids, finished_sn)
        self.assertEqual(
            mo.workorder_ids.current_quality_check_id.trace_ids, component_sn
        )

        mo.workorder_ids.current_quality_check_id.action_next()
        mo.workorder_ids.do_finish()
        mo.button_mark_done()

        self.assertRecordValues(
            mo.move_raw_ids.move_line_ids + mo.move_finished_ids.move_line_ids,
            [
                {"quantity": 1, "trace_id": component_sn.id},
                {"quantity": 1, "trace_id": finished_sn.id},
            ],
        )

    def test_register_consumed_materials_split_production(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        finished = self.bom_4.product_id
        component = self.bom_4.bom_line_ids.product_id
        component.write(
            {
                "is_storable": True,
                "tracking": "serial",
            }
        )

        lots = self.env["product.trace"].create(
            [
                {
                    "name": f"SN00{i + 1}",
                    "product_id": component.id,
                    "company_id": self.env.company.id,
                }
                for i in range(4)
            ]
        )
        for lot in lots:
            self.env["stock.quant"]._update_available_quantity(
                component, warehouse.lot_stock_id, 1, trace_id=lot
            )

        type_register_materials = self.env.ref(
            "mrp_workorder.test_type_register_consumed_materials"
        )
        operation = self.env["mrp.routing.workcenter"].create(
            {
                "name": "Super Operation",
                "bom_id": self.bom_4.id,
                "workcenter_id": self.workcenter_2.id,
                "quality_point_ids": [
                    Command.create(
                        {
                            "product_ids": [Command.link(finished.id)],
                            "picking_type_ids": [
                                Command.link(warehouse.manu_type_id.id)
                            ],
                            "test_type_id": type_register_materials.id,
                            "component_id": component.id,
                            "bom_id": self.bom_4.id,
                            "measure_on": "product",
                        }
                    )
                ],
            }
        )
        self.bom_4.operation_ids = [Command.set(operation.ids)]

        mo_form = Form(self.env["mrp.production"])
        mo_form.bom_id = self.bom_4
        mo_form.product_qty = 2
        mo = mo_form.save()
        mo.action_confirm()

        self.assertEqual(mo.move_raw_ids.trace_ids, lots[:2])
        action = mo.action_split()
        wizard = Form.from_action(self.env, action)
        wizard.max_batch_size = 1
        action = wizard.save().action_split()
        self.assertEqual(len(mo.production_group_id.production_ids), 2)
        self.assertEqual(
            mo.production_group_id.production_ids[
                0
            ].workorder_ids.current_quality_check_id.trace_ids,
            lots[0],
        )
        self.assertEqual(
            mo.production_group_id.production_ids[
                1
            ].workorder_ids.current_quality_check_id.trace_ids,
            lots[1],
        )
        component_move = mo.workorder_ids.current_quality_check_id.move_id
        component_move.action_add_from_quant(
            self.env["stock.quant"]
            .search(
                [
                    ("trace_id", "=", lots[2].id),
                    ("location_id", "=", warehouse.lot_stock_id.id),
                ],
                limit=1,
            )
            .id
        )
        self.assertRecordValues(
            mo.move_raw_ids,
            [
                {"quantity": 1.0, "trace_ids": lots[2].ids},
            ],
        )

    def test_backorder_cancelled_workorder_quality_check(self):
        bom = self.env["mrp.bom"].create(
            {
                "product_id": self.product_6.id,
                "product_tmpl_id": self.product_6.product_tmpl_id.id,
                "product_qty": 1,
                "type": "normal",
                "operation_ids": [
                    Command.create(
                        {
                            "name": "Cut",
                            "workcenter_id": self.workcenter_1.id,
                            "time_cycle": 12,
                            "sequence": 1,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Weld",
                            "workcenter_id": self.workcenter_1.id,
                            "time_cycle": 18,
                            "sequence": 2,
                        }
                    ),
                ],
                "bom_line_ids": [
                    Command.create({"product_id": self.product_3.id, "product_qty": 2}),
                    Command.create({"product_id": self.product_2.id, "product_qty": 3}),
                ],
            }
        )
        operation_ids = bom.operation_ids
        self.env["stock.quant"].create(
            [
                {
                    "product_id": self.product_3.id,
                    "product_uom_id": self.uom_unit.id,
                    "location_id": self.shelf_1.id,
                    "quantity": 4,
                },
                {
                    "product_id": self.product_2.id,
                    "product_uom_id": self.uom_unit.id,
                    "location_id": self.shelf_1.id,
                    "quantity": 6,
                },
            ]
        )
        self.env["quality.point"].create(
            [
                {
                    "title": "test QP1",
                    "product_ids": [Command.link(self.product_6.id)],
                    "operation_id": operation_ids[0].id,
                    "note": "Cut",
                },
                {
                    "title": "test QP2",
                    "product_ids": [Command.link(self.product_6.id)],
                    "operation_id": operation_ids[1].id,
                    "note": "Weld",
                },
            ]
        )
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_6.id,
                "product_qty": 2,
                "bom_id": bom.id,
            }
        )
        mo.action_confirm()
        self.assertEqual(len(mo.move_raw_ids), 2)
        self.assertEqual(len(mo.workorder_ids), 2)
        self.assertEqual(len(mo.workorder_ids.check_ids), 2)
        full_workorder = mo.workorder_ids[0]
        full_workorder.qty_producing = 2
        full_workorder.check_ids.action_pass_and_next()
        full_workorder.button_finish()
        self.assertEqual(full_workorder.state, "done")
        partial_workorder = mo.workorder_ids[1]
        partial_workorder.qty_producing = 1
        partial_workorder.check_ids.action_pass_and_next()
        partial_workorder.button_finish()
        self.assertEqual(partial_workorder.state, "done")
        self.assertEqual(mo.qty_producing, 1)
        Form.from_action(self.env, mo.button_mark_done()).save().action_backorder()
        backorder = mo.production_group_id.production_ids[1]
        self.assertEqual(backorder.product_qty, 1)
        self.assertEqual(len(backorder.workorder_ids), 2)
        self.assertEqual(backorder.workorder_ids[0].state, "cancel")
        self.assertEqual(len(backorder.workorder_ids[0].check_ids), 0)
        backorder.workorder_ids[1].qty_producing = 1
        backorder.workorder_ids[1].check_ids.action_pass_and_next()
        backorder.workorder_ids[1].button_finish()
        backorder.button_mark_done()
        self.assertEqual(backorder.state, "done")

    def test_compute_lot_quality_checks(self):
        self.product_2.tracking = "serial"
        self.env["quality.point"].create(
            {
                "title": "Test Step",
                "picking_type_ids": [(Command.link(self.picking_type_manu.id))],
                "measure_on": "product",
            }
        )
        finished_sn = self.env["product.trace"].create(
            [
                {
                    "name": self.product_2.name,
                    "product_id": self.product_2.id,
                    "company_id": self.env.company.id,
                }
            ]
        )
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_2.id,
                "product_qty": 1,
                "picking_type_id": self.picking_type_manu.id,
            }
        )
        mo.action_confirm()
        self.assertEqual(mo.state, "confirmed")
        mo_form = Form(mo)
        mo_form.trace_producing_ids.set(finished_sn)
        mo = mo_form.save()
        mo.check_ids.do_pass()
        mo.button_mark_done()
        self.assertEqual(mo.state, "done")
        self.assertEqual(finished_sn.quality_check_qty, 1)
        bom_2 = self.env["mrp.bom"].create(
            {
                "product_id": self.product_3.id,
                "product_tmpl_id": self.product_3.product_tmpl_id.id,
                "product_qty": 1,
                "operation_ids": [
                    Command.create(
                        {
                            "name": "OP2",
                            "workcenter_id": self.workcenter_1.id,
                            "sequence": 1,
                        }
                    ),
                ],
                "bom_line_ids": [
                    Command.create({"product_id": self.product_2.id, "product_qty": 1}),
                ],
            }
        )
        self.env["quality.point"].create(
            {
                "title": "Test Step",
                "picking_type_ids": [(Command.link(self.picking_type_manu.id))],
                "operation_id": bom_2.operation_ids.id,
                "measure_on": "product",
                "test_type_id": self.env.ref(
                    "mrp_workorder.test_type_register_consumed_materials"
                ).id,
                "component_id": self.product_2.id,
            }
        )
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product_3.id,
                "product_qty": 1,
                "bom_id": bom_2.id,
                "picking_type_id": self.picking_type_manu.id,
            }
        )
        mo.action_confirm()
        self.assertEqual(len(mo.move_raw_ids), 1)
        self.assertEqual(mo.state, "confirmed")
        self.assertEqual(len(mo.workorder_ids), 1)
        quality_check = mo.workorder_ids.check_ids
        self.assertEqual(quality_check.component_id, self.product_2)
        self.assertEqual(quality_check.move_id.quantity, 1)
        self.assertEqual(finished_sn.quality_check_qty, 2)
        domain_sn_qc = [
            "|",
            ("trace_ids", "in", finished_sn.ids),
            ("finished_trace_ids", "in", finished_sn.ids),
        ]
        self.assertEqual(
            list(finished_sn.action_view_quality_checks()["domain"]), domain_sn_qc
        )

    def test_merge_mo_from_orderpoints_2(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        warehouse_2 = self.env["stock.warehouse"].create(
            {"name": "WH 2", "code": "WH2"}
        )
        route_manufacture = warehouse.manufacture_pull_id.route_id
        self.product_1.route_ids = [Command.set([route_manufacture.id])]
        orderpoints = self.env["stock.warehouse.orderpoint"].create(
            [
                {
                    "product_id": self.product_1.id,
                    "warehouse_id": warehouse.id,
                    "product_min_qty": 0,
                    "product_max_qty": 0,
                    "trigger": "auto",
                }
                for warehouse in (warehouse, warehouse_2)
            ]
        )

        self.bom = self.env["mrp.bom"].create(
            {
                "product_id": self.product_1.id,
                "product_tmpl_id": self.product_1.product_tmpl_id.id,
                "product_uom_id": self.product_1.uom_id.id,
                "product_qty": 1.0,
                "consumption": "flexible",
                "operation_ids": [
                    Command.create(
                        {
                            "name": "Assembly",
                            "workcenter_id": self.workcenter_1.id,
                            "time_cycle": 15,
                            "sequence": 1,
                        }
                    ),
                    Command.create(
                        {"name": "Assembly2", "workcenter_id": self.workcenter_1.id}
                    ),
                ],
                "type": "normal",
                "bom_line_ids": [
                    Command.create({"product_id": self.product_2.id, "product_qty": 1})
                ],
            }
        )
        self.env["quality.point"].create(
            [
                {
                    "title": "Operation QP",
                    "measure_on": "operation",
                    "product_ids": [Command.link(self.product_1.id)],
                    "operation_id": self.bom.operation_ids[1].id,
                    "test_type_id": self.env.ref("quality.test_type_instructions").id,
                },
                {
                    "title": "Production QP",
                    "measure_on": "product",
                    "picking_type_ids": [(Command.link(warehouse_2.manu_type_id.id))],
                    "product_ids": [Command.link(self.product_1.id)],
                },
            ]
        )
        reference = self.env["stock.reference"].create({"name": "lovely reference"})
        deliveries = self.env["stock.picking"].create(
            [
                {
                    "name": f"Lovely {wh.code} Delivery {i}",
                    "location_id": wh.lot_stock_id.id,
                    "location_dest_id": self.ref("stock.stock_location_customers"),
                    "picking_type_id": wh.out_type_id.id,
                    "move_ids": [
                        Command.create(
                            {
                                "location_id": wh.lot_stock_id.id,
                                "location_dest_id": self.ref(
                                    "stock.stock_location_customers"
                                ),
                                "product_id": self.product_1.id,
                                "product_uom_qty": 1,
                                "reference_ids": [Command.set(reference.ids)],
                            }
                        )
                    ],
                }
                for i in range(1, 4)
                for wh in (warehouse, warehouse_2)
            ]
        )

        deliveries[:2].action_confirm()
        mos = self.env["mrp.production"].search(
            [("orderpoint_id", "in", orderpoints.ids)], limit=2, order="warehouse_id.id"
        )
        self.assertRecordValues(
            mos,
            [
                {
                    "product_qty": 1.0,
                    "product_id": self.product_1.id,
                    "warehouse_id": warehouse.id,
                },
                {
                    "product_qty": 1.0,
                    "product_id": self.product_1.id,
                    "warehouse_id": warehouse_2.id,
                },
            ],
        )

        deliveries[2:4].action_confirm()
        self.assertRecordValues(
            mos,
            [
                {
                    "product_qty": 2.0,
                    "product_id": self.product_1.id,
                    "warehouse_id": warehouse.id,
                },
                {
                    "product_qty": 2.0,
                    "product_id": self.product_1.id,
                    "warehouse_id": warehouse_2.id,
                },
            ],
        )

        mos[0].workorder_ids[1].current_quality_check_id.action_next()
        mos[1].check_ids[0].do_pass()
        deliveries[4:].action_confirm()
        mos = self.env["mrp.production"].search(
            [("orderpoint_id", "in", orderpoints.ids)],
            limit=4,
            order="warehouse_id.id, id",
        )
        self.assertRecordValues(
            mos,
            [
                {
                    "product_qty": 2.0,
                    "product_id": self.product_1.id,
                    "warehouse_id": warehouse.id,
                },
                {
                    "product_qty": 1.0,
                    "product_id": self.product_1.id,
                    "warehouse_id": warehouse.id,
                },
                {
                    "product_qty": 2.0,
                    "product_id": self.product_1.id,
                    "warehouse_id": warehouse_2.id,
                },
                {
                    "product_qty": 1.0,
                    "product_id": self.product_1.id,
                    "warehouse_id": warehouse_2.id,
                },
            ],
        )


@tagged("post_install", "-at_install")
class TestPickingWorkorderClientActionQuality(
    test_tablet_client_action.TestWorkorderClientActionCommon, HttpCase
):
    def test_measure_quality_check(self):
        self.env["quality.point"].create(
            {
                "title": "Measure Wand Step",
                "product_ids": [Command.link(self.potion.id)],
                "picking_type_ids": [Command.link(self.picking_type_manu.id)],
                "operation_id": self.wizard_op_1.id,
                "test_type_id": self.env.ref("quality_control.test_type_measure").id,
                "norm": 15,
                "tolerance_min": 14,
                "tolerance_max": 16,
                "sequence": 0,
                "note": '<p>Make sure your wand is the correct size for the "magic" to happen</p>',
            }
        )
        mo_form = Form(self.env["mrp.production"])
        mo_form.bom_id = self.bom_potion
        mo = mo_form.save()
        mo.action_confirm()
        mo.qty_producing = mo.product_qty

        self.assertEqual(
            mo.workorder_ids.check_ids.filtered(
                lambda x: x.test_type == "measure"
            ).quality_state,
            "none",
        )

        res_action = mo.workorder_ids.check_ids.filtered(
            lambda x: x.test_type == "measure"
        ).do_measure()

        self.assertEqual(
            mo.workorder_ids.check_ids.filtered(
                lambda x: x.test_type == "measure"
            ).quality_state,
            "fail",
            "The measure quality check should have failed",
        )
        self.assertEqual(
            res_action.get("res_model"),
            "wizard.quality.check.decide",
            "The action should return a wizard when failing",
        )
