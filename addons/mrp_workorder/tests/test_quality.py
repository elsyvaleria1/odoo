from odoo import Command
from odoo.tests import Form
from odoo.tests.common import TransactionCase


class TestQuality(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        grp_workorder = cls.env.ref("mrp.group_mrp_routings")
        cls.env.user.write({"group_ids": [(4, grp_workorder.id)]})

        cls.product_1 = cls.env["product.product"].create({"name": "Table"})
        cls.product_2 = cls.env["product.product"].create({"name": "Table top"})
        cls.product_3 = cls.env["product.product"].create({"name": "Table leg"})
        cls.workcenter_1 = cls.env["mrp.workcenter"].create(
            {
                "name": "Test Workcenter",
                "time_start": 10,
                "time_stop": 5,
                "time_efficiency": 80,
            }
        )
        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_id": cls.product_1.id,
                "product_tmpl_id": cls.product_1.product_tmpl_id.id,
                "product_uom_id": cls.product_1.uom_id.id,
                "product_qty": 1.0,
                "consumption": "flexible",
                "operation_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Assembly",
                            "workcenter_id": cls.workcenter_1.id,
                            "time_cycle": 15,
                            "sequence": 1,
                        },
                    ),
                ],
                "type": "normal",
                "bom_line_ids": [
                    (0, 0, {"product_id": cls.product_2.id, "product_qty": 1}),
                    (0, 0, {"product_id": cls.product_3.id, "product_qty": 4}),
                ],
            }
        )

    def test_quality_point_onchange(self):
        quality_point_form = Form(
            self.env["quality.point"].with_context(
                default_product_ids=[self.product_2.id]
            )
        )
        self.assertEqual(len(quality_point_form.product_ids), 1)
        self.assertEqual(quality_point_form.product_ids[0].id, self.product_2.id)
        quality_point_form.picking_type_ids.add(
            self.env["stock.picking.type"].search(
                [("code", "=", "mrp_operation")], limit=1
            )
        )
        quality_point_form.operation_id = self.bom.operation_ids[0]
        self.assertEqual(len(quality_point_form.product_ids), 1)
        self.assertEqual(quality_point_form.product_ids[0].id, self.bom.product_id.id)

    def test_delete_move_linked_to_quality_check(self):
        self.bom.bom_line_ids.product_id.is_storable = True
        self.bom.bom_line_ids.product_id.tracking = "lot"
        self.bom.operation_ids[0].quality_point_ids = [
            Command.create(
                {
                    "product_ids": [(4, self.product_1.id)],
                    "picking_type_ids": [
                        (
                            4,
                            self.env["stock.picking.type"]
                            .search([("code", "=", "mrp_operation")], limit=1)
                            .id,
                        )
                    ],
                    "test_type_id": self.env.ref(
                        "mrp_workorder.test_type_register_consumed_materials"
                    ).id,
                    "component_id": self.product_2.id,
                }
            )
        ]
        mo_form = Form(self.env["mrp.production"])
        mo_form.bom_id = self.bom
        mo = mo_form.save()
        mo.action_confirm()
        qc = self.env["quality.check"].search(
            [("product_id", "=", self.bom.product_id.id)]
        )[-1]
        move = qc.move_id
        self.assertEqual(len(qc), 1)
        self.assertFalse(move.move_line_ids)
        move.state = "draft"
        move.unlink()
        self.assertFalse(move.exists())
        self.assertFalse(qc.exists())

    def test_label_printed_qty(self):
        super_product = self.env["product.product"].create(
            {
                "name": "Super Product",
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
            }
        )
        bom = self.env["mrp.bom"].create(
            {
                "product_id": super_product.id,
                "product_tmpl_id": super_product.product_tmpl_id.id,
                "product_uom_id": super_product.uom_id.id,
                "product_qty": 1.0,
                "operation_ids": [
                    Command.create(
                        {"name": "print label", "workcenter_id": self.workcenter_1.id}
                    )
                ],
                "type": "normal",
            }
        )

        self.env["quality.point"].create(
            {
                "title": "Print Label",
                "product_ids": [Command.link(super_product.id)],
                "operation_id": bom.operation_ids.id,
                "test_type_id": self.ref("mrp_workorder.test_type_print_label"),
            }
        )
        mo_form = Form(self.env["mrp.production"])
        mo_form.bom_id = bom
        mo_form.product_qty = 10
        mo = mo_form.save()
        mo.action_confirm()

        self.assertEqual(mo.workorder_ids.current_quality_check_id._get_print_qty(), 10)
        with Form(mo) as mo_form:
            mo_form.qty_producing = 7.0
        self.assertEqual(mo.workorder_ids.current_quality_check_id._get_print_qty(), 7)

    def test_copy_quality_check(self):
        quality_point = self.env["quality.point"].create(
            {
                "product_ids": [(4, self.product_1.id)],
            }
        )
        quality_alert_team = self.env["team.team"].create(
            {
                "use_quality": True,
                "name": "Quality Team",
            }
        )
        check_vals = {
            "product_id": self.product_1.id,
            "point_id": quality_point.id,
            "team_id": quality_alert_team.id,
        }
        quality_checks = self.env["quality.check"].create(
            [check_vals, check_vals, check_vals]
        )

        quality_checks[1]._insert_in_chain("after", quality_checks[0])
        quality_checks[2]._insert_in_chain("after", quality_checks[1])

        new_check = quality_checks[1].copy()

        self.assertEqual(quality_checks[1].next_check_id, new_check)
        self.assertEqual(new_check.previous_check_id, quality_checks[1])
        self.assertEqual(new_check.next_check_id, quality_checks[2])

    def test_a_check_reports_the_tracking_of_its_own_product(self):
        byproduct = self.env["product.product"].create(
            {"name": "Serial offcut", "is_storable": True, "tracking": "serial"}
        )
        production = self.env["mrp.production"].create(
            {"product_id": self.product_1.id, "product_qty": 1}
        )
        production.write(
            {
                "move_byproduct_ids": [
                    Command.create(
                        {
                            "product_id": byproduct.id,
                            "product_uom_qty": 1,
                            "product_uom_id": byproduct.uom_id.id,
                            "location_id": production.location_src_id.id,
                            "location_dest_id": production.location_dest_id.id,
                        }
                    )
                ]
            }
        )
        check = self.env["quality.check"].create(
            {
                "product_id": byproduct.id,
                "production_id": production.id,
                "team_id": self.env["team.team"]
                .create({"use_quality": True, "name": "QC"})
                .id,
            }
        )
        self.assertEqual(production.product_tracking, "none")
        self.assertEqual(check.product_tracking, "serial")

    def test_merge_mo_from_orderpoints(self):
        self.env["mrp.routing.workcenter"].create(
            {
                "name": "Assembly2",
                "workcenter_id": self.workcenter_1.id,
                "bom_id": self.bom.id,
            }
        )
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        route_manufacture = warehouse.manufacture_pull_id.route_id
        self.product_1.route_ids = [Command.set([route_manufacture.id])]
        orderpoint = self.env["stock.warehouse.orderpoint"].create(
            {
                "product_id": self.product_1.id,
                "warehouse_id": warehouse.id,
                "product_min_qty": 0,
                "product_max_qty": 0,
                "trigger": "auto",
            }
        )
        self.env["quality.point"].create(
            {
                "title": "QC",
                "product_ids": [Command.link(self.product_1.id)],
                "operation_id": self.bom.operation_ids[1].id,
                "test_type_id": self.env.ref("quality.test_type_instructions").id,
            }
        )
        reference = self.env["stock.reference"].create({"name": "lovely reference"})
        deliveries = self.env["stock.picking"].create(
            [
                {
                    "name": f"Lovely Delivery {i}",
                    "location_id": warehouse.lot_stock_id.id,
                    "location_dest_id": self.ref("stock.stock_location_customers"),
                    "picking_type_id": warehouse.out_type_id.id,
                    "move_ids": [
                        Command.create(
                            {
                                "location_id": warehouse.lot_stock_id.id,
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
            ]
        )

        deliveries[0].action_confirm()
        mo = self.env["mrp.production"].search(
            [("orderpoint_id", "=", orderpoint.id)], limit=1
        )
        self.assertRecordValues(
            mo,
            [
                {
                    "product_qty": 1.0,
                    "product_id": self.product_1.id,
                    "warehouse_id": warehouse.id,
                },
            ],
        )

        deliveries[1].action_confirm()
        self.assertRecordValues(
            mo,
            [
                {
                    "product_qty": 2.0,
                    "product_id": self.product_1.id,
                    "warehouse_id": warehouse.id,
                },
            ],
        )

        mo.workorder_ids[1].current_quality_check_id.action_next()
        deliveries[2].action_confirm()
        mos = self.env["mrp.production"].search(
            [("orderpoint_id", "=", orderpoint.id)], order="id", limit=2
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
            ],
        )

    def test_workorder_form_lists_pending_quality_checks(self):
        self.env["quality.point"].create(
            {
                "product_ids": [Command.link(self.product_1.id)],
                "picking_type_ids": [
                    Command.link(
                        self.env["stock.picking.type"]
                        .search([("code", "=", "mrp_operation")], limit=1)
                        .id
                    )
                ],
                "operation_id": self.bom.operation_ids[0].id,
                "test_type_id": self.env.ref("quality.test_type_instructions").id,
                "note": "Check the table is level",
            }
        )
        production = self.env["mrp.production"].create(
            {"product_id": self.product_1.id, "bom_id": self.bom.id, "product_qty": 1}
        )
        production.action_confirm()
        workorder = production.workorder_ids[0]

        self.assertTrue(
            workorder.check_ids.filtered(lambda c: c.quality_state == "none")
        )
        self.assertFalse(workorder.done_check_ids)

        workorder_form = Form(workorder)
        self.assertTrue(
            workorder_form.check_ids,
            "the form should expose every quality check, including pending ones",
        )

    def test_workorder_quality_points_follow_the_operation(self):
        production = self.env["mrp.production"].create(
            {"product_id": self.product_1.id, "bom_id": self.bom.id}
        )
        production.action_confirm()
        workorder = production.workorder_ids
        self.assertFalse(workorder.quality_point_ids)
        point = self.env["quality.point"].create(
            {
                "title": "Late step",
                "operation_id": self.bom.operation_ids.id,
                "picking_type_ids": [
                    Command.set(self.env.ref("stock.warehouse0").manu_type_id.ids)
                ],
                "test_type_id": self.env.ref("quality.test_type_instructions").id,
                "product_ids": [Command.set(self.product_1.ids)],
            }
        )
        self.assertEqual(workorder.quality_point_ids, point)
        point.product_ids = [Command.set(self.product_2.ids)]
        self.assertFalse(workorder.quality_point_ids)

    def test_batch_lot_producing_write_keeps_each_mo_lots(self):
        self.product_1.is_storable = True
        self.product_1.tracking = "serial"
        register = self.env.ref("mrp_workorder.test_type_register_production")
        team = self.env["team.team"].search([("use_quality", "=", True)], limit=1)
        productions = self.env["mrp.production"]
        lots = self.env["product.trace"]
        for name in ("SN1", "SN2"):
            production = self.env["mrp.production"].create(
                {"product_id": self.product_1.id, "bom_id": self.bom.id}
            )
            production.action_confirm()
            self.env["quality.check"].create(
                {
                    "test_type_id": register.id,
                    "workorder_id": production.workorder_ids.id,
                    "production_id": production.id,
                    "product_id": self.product_1.id,
                    "team_id": team.id,
                }
            )
            lot = self.env["product.trace"].create(
                {"name": name, "product_id": self.product_1.id}
            )
            production.trace_producing_ids = [Command.set(lot.ids)]
            productions |= production
            lots |= lot
        shared = self.env["product.trace"].create(
            {"name": "SN3", "product_id": self.product_1.id}
        )
        productions.write({"trace_producing_ids": [Command.link(shared.id)]})
        for production in productions:
            checks = production.workorder_ids.check_ids.filtered(
                lambda c: c.test_type_id == register
            )
            self.assertEqual(checks.trace_ids, production.trace_producing_ids)

    def test_shop_floor_lot_scan_uses_the_picker_domain(self):
        self.product_2.is_storable = True
        self.product_2.tracking = "lot"
        production = self.env["mrp.production"].create(
            {"product_id": self.product_1.id, "bom_id": self.bom.id}
        )
        production.action_confirm()
        move = production.move_raw_ids.filtered(
            lambda m: m.product_id == self.product_2
        )
        lot = self.env["product.trace"].create(
            {"name": "SCAN1", "product_id": self.product_2.id}
        )
        self.env["stock.quant"].create(
            {
                "product_id": self.product_2.id,
                "trace_id": lot.id,
                "location_id": self.product_2.property_stock_production.id,
                "quantity": 5,
            }
        )
        self.assertIsNone(move.get_or_create_quant_id_from_barcode("SCAN1"))
        self.env["stock.quant"]._update_available_quantity(
            self.product_2, production.location_src_id, 3, trace_id=lot
        )
        quant = self.env["stock.quant"].browse(
            move.get_or_create_quant_id_from_barcode("SCAN1")
        )
        self.assertEqual(quant.location_id, production.location_src_id)
        production.picking_type_id.use_create_components_lots = True
        new_quant = self.env["stock.quant"].browse(
            move.get_or_create_quant_id_from_barcode("SCAN-NEW")
        )
        self.assertEqual(new_quant.location_id, production.location_src_id)
        self.assertEqual(new_quant.trace_id.name, "SCAN-NEW")
        self.product_2.tracking = "none"
        self.assertIsNone(move.get_or_create_quant_id_from_barcode("UNTRACKED"))
        self.assertFalse(
            self.env["product.trace"].search(
                [("name", "=", "UNTRACKED"), ("product_id", "=", self.product_2.id)]
            )
        )

    def test_a_readonly_user_opens_the_quality_fields_this_module_adds(self):
        readonly = self.env["res.users"].create(
            {
                "name": "MRP read-only",
                "login": "mrp_readonly_quality_fields",
                "group_ids": [
                    Command.set(
                        [
                            self.env.ref("mrp.group_mrp_readonly").id,
                            self.env.ref("mrp.group_mrp_routings").id,
                        ]
                    )
                ],
            }
        )
        production = self.env["mrp.production"].create(
            {"product_id": self.product_1.id, "bom_id": self.bom.id}
        )
        production.action_confirm()
        production.workorder_ids.with_user(readonly).read(["check_ids"])
        self.bom.operation_ids.with_user(readonly).read(["quality_point_ids"])
