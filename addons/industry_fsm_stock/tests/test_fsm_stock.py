from datetime import datetime

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, common

from odoo.addons.industry_fsm_sale.tests.common import TestFsmFlowSaleCommon


@common.tagged("post_install", "-at_install")
class TestFsmFlowStock(TestFsmFlowSaleCommon):
    def _generate_3_steps_warehouse(self, code):
        warehouse = self.env["stock.warehouse"].create(
            {
                "name": code,
                "code": code,
                "delivery_steps": "pick_pack_ship",
            }
        )
        delivery_route = warehouse.delivery_route_id
        delivery_route.rule_ids[0].write(
            {
                "location_dest_id": delivery_route.rule_ids[1].location_src_id.id,
            }
        )
        delivery_route.rule_ids[1].write({"action": "pull"})
        delivery_route.rule_ids[2].write({"action": "pull"})
        return warehouse

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.quick_ref("industry_fsm.group_fsm_manager")
        cls.product_lot = cls.env["product.product"].create(
            {
                "name": "Acoustic Magic Bloc",
                "list_price": 2950.0,
                "is_storable": True,
                "invoice_policy": "transferred",
                "taxes_id": False,
                "tracking": "lot",
            }
        )

        cls.lot_id1 = cls.env["product.trace"].create(
            {
                "product_id": cls.product_lot.id,
                "name": "Lot_1",
            }
        )

        cls.lot_id2 = cls.env["product.trace"].create(
            {
                "product_id": cls.product_lot.id,
                "name": "Lot_2",
            }
        )

        cls.lot_id3 = cls.env["product.trace"].create(
            {
                "product_id": cls.product_lot.id,
                "name": "Lot_3",
            }
        )

        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        quants = (
            cls.env["stock.quant"]
            .with_context(inventory_mode=True)
            .create(
                {
                    "product_id": cls.product_lot.id,
                    "inventory_quantity": 4,
                    "trace_id": cls.lot_id1.id,
                    "location_id": cls.warehouse.lot_stock_id.id,
                }
            )
        )
        quants |= (
            cls.env["stock.quant"]
            .with_context(inventory_mode=True)
            .create(
                {
                    "product_id": cls.product_lot.id,
                    "inventory_quantity": 2,
                    "trace_id": cls.lot_id2.id,
                    "location_id": cls.warehouse.lot_stock_id.id,
                }
            )
        )
        quants |= (
            cls.env["stock.quant"]
            .with_context(inventory_mode=True)
            .create(
                {
                    "product_id": cls.product_lot.id,
                    "inventory_quantity": 2,
                    "trace_id": cls.lot_id3.id,
                    "location_id": cls.warehouse.lot_stock_id.id,
                }
            )
        )
        quants.action_apply_inventory()

        cls.storable_product_ordered = cls.env["product.product"].create(
            {
                "name": "Storable product ordered",
                "list_price": 60,
                "is_storable": True,
                "invoice_policy": "ordered",
                "taxes_id": False,
            }
        )
        cls.storable_product_delivered = cls.env["product.product"].create(
            {
                "name": "Storable product delivered",
                "list_price": 75.6,
                "is_storable": True,
                "invoice_policy": "transferred",
                "taxes_id": False,
            }
        )
        cls.warehouse_A, cls.warehouse_B = cls.env["stock.warehouse"].create(
            [
                {
                    "name": "WH A",
                    "code": "WHA",
                    "company_id": cls.env.company.id,
                    "partner_id": cls.env.company.partner_id.id,
                },
                {
                    "name": "WH B",
                    "code": "WHB",
                    "company_id": cls.env.company.id,
                    "partner_id": cls.env.company.partner_id.id,
                },
            ]
        )
        cls.warehouse_3s_pull = cls._generate_3_steps_warehouse(cls, "WH3S")

        (
            cls.product_lot_stock,
            cls.product_lot_no_stock,
            cls.product_sn_stock,
            cls.product_sn_no_stock,
        ) = cls.env["product.product"].create(
            [
                {
                    "name": "Storable product with lot 1",
                    "list_price": 60,
                    "is_storable": True,
                    "invoice_policy": "ordered",
                    "taxes_id": False,
                    "tracking": "lot",
                },
                {
                    "name": "Storable product with lot 2 no stock",
                    "list_price": 60,
                    "is_storable": True,
                    "invoice_policy": "ordered",
                    "taxes_id": False,
                    "tracking": "lot",
                },
                {
                    "name": "Storable product with SN",
                    "list_price": 60,
                    "is_storable": True,
                    "invoice_policy": "ordered",
                    "taxes_id": False,
                    "tracking": "serial",
                },
                {
                    "name": "Storable product with SN no stock",
                    "list_price": 60,
                    "is_storable": True,
                    "invoice_policy": "ordered",
                    "taxes_id": False,
                    "tracking": "serial",
                },
            ]
        )
        (
            cls.lot_pls_1,
            cls.lot_pls_2,
            cls.lot_plns_1,
            cls.lot_plns_2,
            cls.serial_stock_1,
            cls.serial_stock_2,
            cls.serial_no_stock_1,
            cls.serial_no_stock_2,
        ) = cls.env["product.trace"].create(
            [
                {
                    "product_id": cls.product_lot_stock.id,
                    "name": "lot_pls_1",
                },
                {
                    "product_id": cls.product_lot_stock.id,
                    "name": "lot_pls_2",
                },
                {
                    "product_id": cls.product_lot_no_stock.id,
                    "name": "lot_plns_1",
                },
                {
                    "product_id": cls.product_lot_no_stock.id,
                    "name": "lot_plns_2",
                },
                {
                    "name": "serial_stock_1",
                    "product_id": cls.product_sn_stock.id,
                },
                {
                    "name": "serial_stock_2",
                    "product_id": cls.product_sn_stock.id,
                },
                {
                    "name": "serial_no_stock_1",
                    "product_id": cls.product_sn_no_stock.id,
                },
                {
                    "name": "serial_no_stock_2",
                    "product_id": cls.product_sn_no_stock.id,
                },
            ]
        )
        cls.env["stock.quant"].with_context(inventory_mode=True).create(
            [
                {
                    "product_id": cls.product_sn_stock.id,
                    "inventory_quantity": 1,
                    "trace_id": cls.serial_stock_1.id,
                    "location_id": cls.warehouse.lot_stock_id.id,
                },
                {
                    "product_id": cls.product_lot_stock.id,
                    "inventory_quantity": 500,
                    "trace_id": cls.lot_pls_1.id,
                    "location_id": cls.warehouse.lot_stock_id.id,
                },
                {
                    "product_id": cls.product_sn_stock.id,
                    "inventory_quantity": 1,
                    "trace_id": cls.serial_stock_2.id,
                    "location_id": cls.warehouse.lot_stock_id.id,
                },
                {
                    "product_id": cls.product_lot_stock.id,
                    "inventory_quantity": 500,
                    "trace_id": cls.lot_pls_2.id,
                    "location_id": cls.warehouse.lot_stock_id.id,
                },
            ]
        ).action_apply_inventory()

    def _test_fsm_flow(self):
        self.warehouse.delivery_steps = "pick_pack_ship"

        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        self.task.sale_order_id.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_lot.id,
                            "product_qty": 3,
                            "fsm_trace_id": self.lot_id2.id,
                        }
                    )
                ]
            }
        )

        move = self.task.sale_order_id.line_ids.move_ids
        while move.move_orig_ids:
            move = move.move_orig_ids
        self.assertEqual(move.move_line_ids[0].trace_id, self.lot_id2)
        self.assertEqual(move.move_line_ids[0].quantity_product_uom, 2)
        self.assertNotEqual(
            move.move_line_ids[1].trace_id,
            self.lot_id2,
            "Lot automatically added on move lines is not the same as asked. (By default, it's the first lot available)",
        )
        self.assertEqual(move.move_line_ids[1].quantity_product_uom, 1)
        self.task.with_user(self.project_user).action_fsm_validate()
        self.assertEqual(
            move.move_line_ids.trace_id,
            self.lot_id2,
            "Asked lots are added on move lines.",
        )
        self.assertEqual(
            move.quantity, 3, "We deliver 3 (even they are only 2 in stock)"
        )

        self.assertEqual(
            self.task.sale_order_id.picking_ids.mapped("state"),
            ["done", "done", "done"],
            "Pickings should be set as done",
        )

    def test_fsm_flow_without_auto_done(self):
        self._test_fsm_flow()

    def test_fsm_with_auto_done(self):
        self.project_user.group_ids += self.env.ref("sale.group_auto_done_setting")
        self._test_fsm_flow()

    def test_fsm_mixed_pickings(self):
        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        self.task.sale_order_id.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 1,
                        }
                    )
                ]
            }
        )
        self.task.with_user(self.project_user).action_fsm_validate()
        self.assertNotEqual(
            self.task.sale_order_id.picking_ids.mapped("state"),
            ["done"],
            "Pickings should be set as done",
        )

    def test_fsm_flow_with_default_warehouses(self):
        self.partner_1.write({"user_id": self.uid})
        self.project_user.write({"property_warehouse_id": self.warehouse_A.id})
        self.assertEqual(
            self.project_user._get_default_warehouse_id().id, self.warehouse_A.id
        )

    def test_fsm_stock_already_validated_picking(self):
        self.warehouse.delivery_steps = "ship_only"

        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        self.task.sale_order_id.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_lot.id,
                            "product_qty": 1,
                            "fsm_trace_id": self.lot_id2.id,
                            "task_id": self.task.id,
                        }
                    )
                ]
            }
        )

        action_stock_tracking = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        self.assertEqual(
            action_stock_tracking["res_model"], "wizard.project.task.update.product.lot"
        )
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            action_stock_tracking["res_id"]
        )
        self.assertFalse(
            wizard.tracking_validated_line_ids, "There aren't validated line"
        )
        self.assertEqual(
            wizard.tracking_line_ids.product_id,
            self.product_lot,
            "There are one line with the right product",
        )
        self.assertEqual(
            wizard.tracking_line_ids.trace_id, self.lot_id2, "The line has lot_id2"
        )

        move = self.task.sale_order_id.line_ids.move_ids
        move.quantity = 1
        picking_ids = self.task.sale_order_id.picking_ids
        picking_ids.with_context(skip_sms=True).button_validate()
        self.assertEqual(
            picking_ids.mapped("state"), ["done"], "Pickings should be set as done"
        )
        self.assertEqual(
            move.move_line_ids.trace_id, self.lot_id2, "The line has lot_id2"
        )

        action_stock_tracking = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            action_stock_tracking["res_id"]
        )
        self.assertFalse(wizard.tracking_line_ids, "There aren't line to validate")
        self.assertEqual(
            wizard.tracking_validated_line_ids.product_id,
            self.product_lot,
            "There are one line with the right product",
        )
        self.assertEqual(
            wizard.tracking_validated_line_ids.trace_id,
            self.lot_id2,
            "The line has lot_id2 (the lot choosed at the beginning)",
        )

        wizard.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_lot.id,
                            "quantity": 3,
                            "trace_id": self.lot_id3.id,
                        }
                    )
                ]
            }
        )
        wizard.action_generate_lot()

        self.task.with_user(self.project_user).action_fsm_validate()
        order_line_ids = self.task.sale_order_id.line_ids.filtered(
            lambda l: l.product_id == self.product_lot
        )
        move = order_line_ids.move_ids
        self.assertEqual(len(order_line_ids), 2, "There are 2 order lines.")
        self.assertEqual(
            move.move_line_ids.trace_id,
            self.lot_id2 + self.lot_id3,
            "Lots stay the same.",
        )
        self.assertEqual(
            sum(move.move_line_ids.mapped("quantity")), 4, "We deliver 4 (1+3)"
        )

        self.assertEqual(
            self.task.sale_order_id.picking_ids.mapped("state"),
            ["done", "done"],
            "The 2 pickings should be set as done",
        )

    def test_modify_quantity_for_tracked_product_by_lot_and_sn(self):
        self.assertFalse(
            self.task.material_line_product_count,
            "No product should be linked to a new task",
        )
        self.task.write({"partner_id": self.partner_1.id})

        expected_product_count = 0
        self.product_lot.with_context({"fsm_task_id": self.task.id}).fsm_add_quantity()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            "No product should be linked to the task, you should validate Lot Number before",
        )

        action_stock_tracking = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        self.assertEqual(
            action_stock_tracking["res_model"], "wizard.project.task.update.product.lot"
        )
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            action_stock_tracking["res_id"]
        )
        expected_product_count = 8
        wizard.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "quantity": 3,
                            "trace_id": self.lot_id3.id,
                        }
                    ),
                    Command.create(
                        {
                            "quantity": 5,
                            "trace_id": self.lot_id1.id,
                        }
                    ),
                ],
            }
        )
        wizard.action_generate_lot()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task",
        )

        self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).fsm_remove_quantity()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task",
        )

        wizard.write(
            {
                "tracking_line_ids": [Command.unlink(wizard.tracking_line_ids[0].id)],
            }
        )
        wizard.action_generate_lot()
        expected_product_count -= 3
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task, you should validate Lot Number before",
        )

        product_tracked_by_sn = self.env["product.product"].create(
            {
                "name": "Product Storable by Serial Number",
                "list_price": 600,
                "is_storable": True,
                "invoice_policy": "transferred",
                "tracking": "serial",
            }
        )

        serial1 = self.env["product.trace"].create(
            {
                "name": "serial1",
                "product_id": product_tracked_by_sn.id,
            }
        )

        serial2 = self.env["product.trace"].create(
            {
                "name": "serial2",
                "product_id": product_tracked_by_sn.id,
            }
        )

        product_tracked_by_sn.with_context(
            {"fsm_task_id": self.task.id}
        ).fsm_add_quantity()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task, you should validate Serial Number before",
        )

        product_tracked_by_sn_wizard = product_tracked_by_sn.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        product_tracked_by_sn_wizard_id = self.env[
            "wizard.project.task.update.product.lot"
        ].browse(product_tracked_by_sn_wizard["res_id"])
        expected_product_count += 1
        product_tracked_by_sn_wizard_id.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "trace_id": serial1.id,
                        }
                    ),
                ],
            }
        )
        product_tracked_by_sn_wizard_id.action_generate_lot()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task",
        )
        self.project_user.group_ids += self.env.ref("stock.group_stock_user")
        product_tracked_by_sn.with_user(self.project_user).with_context(
            {"fsm_task_id": self.task.id}
        ).set_fsm_quantity(2)
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task, you should validate Lot Number before",
        )
        product_tracked_by_sn_wizard_id.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "trace_id": serial2.id,
                        }
                    ),
                ],
            }
        )
        expected_product_count += 1
        product_tracked_by_sn_wizard_id.action_generate_lot()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task, you should validate Serial Number before",
        )

        product_tracked_by_sn.with_context(
            {"fsm_task_id": self.task.id}
        ).fsm_remove_quantity()
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task, you should validate Serial Number before, Serial Number validation is mandatory",
        )

        product_tracked_by_sn_wizard_id.write(
            {
                "tracking_line_ids": [
                    Command.unlink(
                        product_tracked_by_sn_wizard_id.tracking_line_ids[0].id
                    ),
                ],
            }
        )
        product_tracked_by_sn_wizard_id.action_generate_lot()
        expected_product_count -= 1
        self.assertEqual(
            self.task.material_line_product_count,
            expected_product_count,
            f"{expected_product_count} product should be linked to the task, you should validate Serial Number before",
        )

    def test_fsm_stock_validate_half_SOL_manually(self):
        self.warehouse.delivery_steps = "ship_only"

        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()

        self._add_lot_product(
            self.product_lot, [{"trace_id": self.lot_id3.id, "qty": 5}]
        )

        order_line_ids = self.task.sale_order_id.line_ids.filtered(
            lambda l: l.product_id == self.product_lot
        )
        order_line_ids[0].move_ids[0].move_line_ids[0].write(
            {"quantity": 3, "trace_id": self.lot_id2.id}
        )

        Form.from_action(
            self.env, self.task.sale_order_id.picking_ids.button_validate()
        ).save().process()

        wizard = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard_id = self.env["wizard.project.task.update.product.lot"].browse(
            wizard["res_id"]
        )
        self.assertEqual(
            wizard_id.tracking_line_ids.product_id,
            self.product_lot,
            "There is one (non validated) line with the right product",
        )
        self.assertEqual(
            wizard_id.tracking_line_ids.trace_id,
            self.lot_id3,
            "The line has lot_id3, (the lot chosen at the beginning in the wizard)",
        )
        self.assertEqual(
            wizard_id.tracking_line_ids.quantity,
            2,
            "Quantity is 2 (5 from the beginning in the wizard - 3 already delivered)",
        )
        self.assertEqual(
            wizard_id.tracking_validated_line_ids.product_id,
            self.product_lot,
            "There is one validated line with the right product",
        )
        self.assertEqual(
            wizard_id.tracking_validated_line_ids.trace_id,
            self.lot_id2,
            "The line has lot_id2, (not the lot chosen at the beginning, but the lot put in picking)",
        )
        self.assertEqual(
            wizard_id.tracking_validated_line_ids.quantity,
            3,
            "Quantity is 3, chosen in the picking",
        )

        self._update_product(
            self.product_lot, [{"index": 0, "trace_id": self.lot_id3.id, "qty": 4}]
        )

        self.assertEqual(
            order_line_ids.product_qty,
            7,
            "Quantity on SOL is 7 (3 already delivered and 4 set in wizard)",
        )
        self.assertEqual(
            order_line_ids.qty_transferred,
            3,
            "Quantity already delivered is 3, chosen in the picking",
        )

        self.task.with_user(self.project_user).action_fsm_validate()
        order_line_ids = self.task.sale_order_id.line_ids.filtered(
            lambda l: l.product_id == self.product_lot
        )
        move = order_line_ids.move_ids
        self.assertEqual(
            len(order_line_ids),
            1,
            "There are 1 order lines, delivered in 2 times (first manually, second with fsm task validation).",
        )
        self.assertEqual(
            move.move_line_ids.trace_id,
            self.lot_id2 + self.lot_id3,
            "Lot stay the same.",
        )
        self.assertEqual(
            sum(move.move_line_ids.mapped("quantity")), 7, "We deliver 7 (4+3)"
        )

        self.assertEqual(
            self.task.sale_order_id.picking_ids.mapped("state"),
            ["done", "done"],
            "The 2 pickings should be set as done",
        )

    def test_action_quantity_set(self):
        self.task.partner_id = self.partner_1
        product = self.product_lot.with_context(fsm_task_id=self.task.id)
        action = product.fsm_add_quantity()
        self.assertEqual(product.fsm_quantity, 0)
        self.assertEqual(
            action.get("type"),
            "ir.actions.act_window",
            "It should redirect to the tracking wizard",
        )
        self.assertEqual(
            action.get("res_model"),
            "wizard.project.task.update.product.lot",
            "It should redirect to the tracking wizard",
        )

    def test_set_quantity_with_no_so(self):
        self.task.partner_id = self.partner_1
        product = self.consu_product_ordered.with_context(fsm_task_id=self.task.id)
        self.assertFalse(self.task.sale_order_id)
        product.fsm_add_quantity()
        self.assertEqual(product.fsm_quantity, 1)
        order_line = self.task.sale_order_id.line_ids
        self.assertEqual(order_line.product_id.id, product.id)
        self.assertEqual(order_line.product_qty, 1)
        self.assertEqual(order_line.qty_transferred, 0)

        product.set_fsm_quantity(5)
        self.assertEqual(product.fsm_quantity, 5)
        self.assertEqual(order_line.product_id.id, product.id)
        self.assertEqual(order_line.product_qty, 5)
        self.assertEqual(order_line.qty_transferred, 0)

        product.set_fsm_quantity(3)
        self.assertEqual(product.fsm_quantity, 3)
        self.assertEqual(order_line.product_id.id, product.id)
        self.assertEqual(order_line.product_qty, 3)
        self.assertEqual(order_line.qty_transferred, 0)

    def test_set_quantity_with_done_so(self):
        self.task.write({"partner_id": self.partner_1.id})
        product = self.consu_product_ordered.with_context({"fsm_task_id": self.task.id})
        product.set_fsm_quantity(1)

        so = self.task.sale_order_id
        line01 = so.line_ids[-1]
        self.assertEqual(line01.product_qty, 1)
        so.picking_ids.button_validate()

        product.set_fsm_quantity(3)
        self.assertEqual(line01.product_qty, 3)

    def test_validate_task_before_delivery(self):
        product = self.product_a
        task = self.task

        self.warehouse.delivery_steps = "pick_pack_ship"

        product.is_storable = True
        self.env["stock.quant"]._update_available_quantity(
            product, self.warehouse.lot_stock_id, 5
        )

        task.write({"partner_id": self.partner_1.id})
        task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        so = task.sale_order_id
        so.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_qty": 1,
                            "task_id": task.id,
                        }
                    )
                ]
            }
        )
        for picking in so.picking_ids.sorted(lambda p: p.id)[:2]:
            picking.move_line_ids.quantity = 1
            picking.button_validate()

        task.with_user(self.project_user).action_fsm_validate()

        for picking in so.picking_ids:
            self.assertEqual(picking.state, "done")
            self.assertEqual(len(picking.move_line_ids), 1)
            self.assertEqual(picking.move_line_ids.quantity, 1)

    def test_fsm_qty(self):
        self.task.write({"partner_id": self.partner_1.id})
        product = self.consu_product_ordered.with_context({"fsm_task_id": self.task.id})
        self.assertEqual(product.set_fsm_quantity(-1), None)
        self.assertEqual(product.set_fsm_quantity(6), True)
        self.assertEqual(product.set_fsm_quantity(5), True)

        product.write({"is_storable": True, "tracking": "lot"})
        self.assertIn("name", product.set_fsm_quantity(4))

        product.write({"tracking": "none", "is_storable": False})
        self.task.with_user(self.project_user).action_fsm_validate()
        self.task.sale_order_id.sudo().action_lock()
        self.assertEqual(product.set_fsm_quantity(3), False)

    def test_fsm_tracking_wizard_access_right(self):
        self.assertFalse(
            self.task.material_line_product_count,
            "No product should be linked to a new task",
        )
        self.task.write({"partner_id": self.partner_1.id})
        with self.assertRaises(AccessError):
            self.product_lot_stock.with_user(self.project_user).with_context(
                {"fsm_task_id": self.task.id}
            ).set_fsm_quantity(1)
        wizard_action = (
            self.product_lot_stock.with_user(self.project_user)
            .with_context({"fsm_task_id": self.task.id})
            .action_assign_serial()
        )
        wizard = (
            self.env["wizard.project.task.update.product.lot"]
            .with_user(self.project_user)
            .browse(wizard_action["res_id"])
        )
        with self.assertRaises(
            AccessError,
            msg="The user should not be able to generate the lot since he has no access to Inventory app.",
        ):
            wizard.action_generate_lot()

    def test_stock_moves_and_pickings_when_task_is_done(self):
        self.task.write({"partner_id": self.partner_1.id})
        stock_moves = self.env["stock.move"].search(
            [("product_id", "=", self.storable_product_ordered.id)]
        )
        expected_stock_moves_count = 0
        self.assertFalse(stock_moves)
        expected_qty_available = 0
        self.assertEqual(
            self.storable_product_ordered.qty_available, expected_qty_available
        )
        expected_stock_pickings_count = 0
        stock_pickings = self.env["stock.picking"].search(
            [("product_id", "=", self.storable_product_ordered.id)]
        )
        self.assertFalse(stock_pickings)

        product_quantity_used_to_add = 6
        self.storable_product_ordered.with_user(self.project_user).with_context(
            {"fsm_task_id": self.task.id}
        ).set_fsm_quantity(product_quantity_used_to_add)
        self.task.action_fsm_validate()
        stock_moves = self.env["stock.move"].search(
            [("product_id", "=", self.storable_product_ordered.id)]
        )
        expected_stock_moves_count += 1
        self.assertEqual(len(stock_moves), expected_stock_moves_count)
        stock_move = stock_moves[0]
        expected_qty_available -= product_quantity_used_to_add
        self.assertEqual(
            self.storable_product_ordered.qty_available, expected_qty_available
        )
        expected_stock_pickings_count += 1
        stock_pickings = self.env["stock.picking"].search(
            [("product_id", "=", self.storable_product_ordered.id)]
        )
        self.assertEqual(len(stock_pickings), expected_stock_pickings_count)
        stock_picking = stock_pickings[0]
        self.assertEqual(stock_picking.product_id, self.storable_product_ordered)
        self.assertEqual(stock_picking.move_ids, stock_move)

    def test_fsm_flow_with_multi_routing(self):
        self.warehouse.write({"delivery_steps": "pick_pack_ship"})
        self.task.write({"partner_id": self.partner_1.id})

        self.assertEqual(self.task.material_line_product_count, 0)
        self.consu_product_ordered.with_user(self.project_user).with_context(
            {"fsm_task_id": self.task.id}
        ).fsm_add_quantity()
        self.assertEqual(self.task.material_line_product_count, 1)

        self.assertEqual(
            self.task.sale_order_id.count_transfer_outgoing,
            1,
            "Only 'pick' should be created at this point",
        )
        self.task.with_user(self.project_user).action_fsm_validate()
        self.assertEqual(self.task.sale_order_id.count_transfer_outgoing, 3)
        self.assertEqual(
            self.task.sale_order_id.picking_ids.mapped("state"),
            ["done", "done", "done"],
            "Pickings should be set as done",
        )

    def test_multi_routing_with_serial_product(self):
        user_warehouse = self.project_user._get_default_warehouse_id()
        user_warehouse.write({"delivery_steps": "pick_pack_ship"})
        self.task.write({"partner_id": self.partner_1.id})
        self.task._fsm_get_or_create_sale_order()

        self._add_lot_product(
            self.product_lot_stock,
            [
                {"trace_id": self.lot_pls_1.id, "qty": 2},
                {"trace_id": self.lot_pls_2.id, "qty": 3},
            ],
        )
        self._add_lot_product(
            self.product_lot_no_stock,
            [
                {"trace_id": self.lot_plns_1.id, "qty": 4},
                {"trace_id": self.lot_plns_2.id, "qty": 5},
            ],
        )
        self._add_serial_product(
            self.product_sn_stock, [self.serial_stock_1.id, self.serial_stock_2.id]
        )
        self._add_serial_product(
            self.product_sn_no_stock,
            [self.serial_no_stock_1.id, self.serial_no_stock_2.id],
        )

        pick = self.task.sale_order_id.picking_ids
        self.assertRecordValues(
            pick.move_ids,
            [
                {
                    "product_id": self.product_lot_stock.id,
                    "trace_ids": self.lot_pls_1.ids,
                    "product_uom_qty": 2.0,
                    "quantity": 2.0,
                },
                {
                    "product_id": self.product_lot_stock.id,
                    "trace_ids": self.lot_pls_2.ids,
                    "product_uom_qty": 3.0,
                    "quantity": 3.0,
                },
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_ids": self.lot_plns_1.ids,
                    "product_uom_qty": 4.0,
                    "quantity": 4.0,
                },
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_ids": self.lot_plns_2.ids,
                    "product_uom_qty": 5.0,
                    "quantity": 5.0,
                },
                {
                    "product_id": self.product_sn_stock.id,
                    "trace_ids": self.serial_stock_1.ids,
                    "product_uom_qty": 1.0,
                    "quantity": 1.0,
                },
                {
                    "product_id": self.product_sn_stock.id,
                    "trace_ids": self.serial_stock_2.ids,
                    "product_uom_qty": 1.0,
                    "quantity": 1.0,
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_ids": self.serial_no_stock_1.ids,
                    "product_uom_qty": 1.0,
                    "quantity": 1.0,
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_ids": self.serial_no_stock_2.ids,
                    "product_uom_qty": 1.0,
                    "quantity": 1.0,
                },
            ],
        )

        self.task.action_fsm_validate()
        out = self.task.sale_order_id.picking_ids.filtered(
            lambda p: p.picking_type_id.code == "outgoing"
        )
        self.assertRecordValues(
            out.move_ids,
            [
                {
                    "product_id": self.product_lot_stock.id,
                    "trace_ids": self.lot_pls_1.ids,
                    "product_uom_qty": 2.0,
                    "quantity": 2.0,
                },
                {
                    "product_id": self.product_lot_stock.id,
                    "trace_ids": self.lot_pls_2.ids,
                    "product_uom_qty": 3.0,
                    "quantity": 3.0,
                },
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_ids": self.lot_plns_1.ids,
                    "product_uom_qty": 4.0,
                    "quantity": 4.0,
                },
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_ids": self.lot_plns_2.ids,
                    "product_uom_qty": 5.0,
                    "quantity": 5.0,
                },
                {
                    "product_id": self.product_sn_stock.id,
                    "trace_ids": self.serial_stock_1.ids,
                    "product_uom_qty": 1.0,
                    "quantity": 1.0,
                },
                {
                    "product_id": self.product_sn_stock.id,
                    "trace_ids": self.serial_stock_2.ids,
                    "product_uom_qty": 1.0,
                    "quantity": 1.0,
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_ids": self.serial_no_stock_1.ids,
                    "product_uom_qty": 1.0,
                    "quantity": 1.0,
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_ids": self.serial_no_stock_2.ids,
                    "product_uom_qty": 1.0,
                    "quantity": 1.0,
                },
            ],
        )
        self.assertEqual(len(self.task.sale_order_id.picking_ids), 3)
        for pick in self.task.sale_order_id.picking_ids:
            self.assertEqual("done", pick.state, "the delivery should be validated")

    def test_multi_routing_add_and_remove_serial_product(self):
        wh_user = self.warehouse_3s_pull
        wh_other = self._generate_3_steps_warehouse("WH3O")

        self.env.user.write({"property_warehouse_id": wh_user.id})

        self.task.write({"partner_id": self.partner_1.id})
        self.task._fsm_get_or_create_sale_order()

        self.env.user.write({"property_warehouse_id": wh_other.id})

        self._add_lot_product(
            self.product_lot_no_stock, [{"trace_id": self.lot_plns_1.id, "qty": 4}]
        )
        self._add_serial_product(self.product_sn_no_stock, [self.serial_no_stock_1.id])
        self._add_lot_product(
            self.product_lot_no_stock, [{"trace_id": self.lot_plns_2.id, "qty": 2}]
        )
        self._add_serial_product(self.product_sn_no_stock, [self.serial_no_stock_2.id])

        self.env.user.write({"property_warehouse_id": wh_user.id})
        self._add_lot_product(
            self.product_lot_no_stock, [{"trace_id": self.lot_plns_1.id, "qty": 5}]
        )
        self._add_serial_product(self.product_sn_no_stock, [self.serial_no_stock_1.id])
        self._add_lot_product(
            self.product_lot_no_stock, [{"trace_id": self.lot_plns_2.id, "qty": 3}]
        )
        self._add_serial_product(self.product_sn_no_stock, [self.serial_no_stock_2.id])

        picks = self.task.sale_order_id.picking_ids
        delivery_out_whA = picks.filtered(
            lambda p: (
                p.picking_type_id.warehouse_id == wh_other
                and p.location_dest_id.usage == "customer"
            )
        )
        delivery_out_default = picks.filtered(
            lambda p: (
                p.picking_type_id.warehouse_id == wh_user
                and p.location_dest_id.usage == "customer"
            )
        )
        pickings_step_whA = picks.filtered(
            lambda p: (
                p.picking_type_id.warehouse_id == wh_other
                and p.location_dest_id.usage != "customer"
            )
        )
        pickings_step_default = picks.filtered(
            lambda p: (
                p.picking_type_id.warehouse_id == wh_user
                and p.location_dest_id.usage != "customer"
            )
        )
        for pick in pickings_step_whA:
            self.assertRecordValues(
                pick.move_ids.move_line_ids.sorted("trace_id"),
                [
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_id": self.lot_plns_1.id,
                        "quantity": 4.0,
                    },
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_id": self.lot_plns_2.id,
                        "quantity": 2.0,
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_id": self.serial_no_stock_1.id,
                        "quantity": 1.0,
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_id": self.serial_no_stock_2.id,
                        "quantity": 1.0,
                    },
                ],
            )
        for pick in pickings_step_default:
            self.assertRecordValues(
                pick.move_ids.move_line_ids.sorted("trace_id"),
                [
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_id": self.lot_plns_1.id,
                        "quantity": 5.0,
                    },
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_id": self.lot_plns_2.id,
                        "quantity": 3.0,
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_id": self.serial_no_stock_1.id,
                        "quantity": 1.0,
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_id": self.serial_no_stock_2.id,
                        "quantity": 1.0,
                    },
                ],
            )
        self.assertRecordValues(
            delivery_out_whA.move_ids.move_line_ids.sorted("trace_id"),
            [
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_id": self.lot_plns_1.id,
                    "quantity": 4.0,
                },
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_id": self.lot_plns_2.id,
                    "quantity": 2.0,
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_id": self.serial_no_stock_1.id,
                    "quantity": 1.0,
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_id": self.serial_no_stock_2.id,
                    "quantity": 1.0,
                },
            ],
        )
        self.assertRecordValues(
            delivery_out_default.move_ids.move_line_ids.sorted("trace_id"),
            [
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_id": self.lot_plns_1.id,
                    "quantity": 5.0,
                },
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_id": self.lot_plns_2.id,
                    "quantity": 3.0,
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_id": self.serial_no_stock_1.id,
                    "quantity": 1.0,
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_id": self.serial_no_stock_2.id,
                    "quantity": 1.0,
                },
            ],
        )

        self.env.user.write({"property_warehouse_id": wh_other.id})
        self._unlink_product(self.product_lot_no_stock, [1])
        self._unlink_product(self.product_sn_no_stock, [1])
        self.env.user.write({"property_warehouse_id": wh_user.id})
        self._unlink_product(self.product_lot_no_stock, [2])
        self._unlink_product(self.product_sn_no_stock, [2])

        for pick in pickings_step_whA:
            self.assertRecordValues(
                pick.move_ids,
                [
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_ids": self.lot_plns_1.ids,
                        "product_uom_qty": 4.0,
                        "quantity": 4.0,
                        "state": "assigned",
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_ids": self.serial_no_stock_1.ids,
                        "product_uom_qty": 1.0,
                        "quantity": 1.0,
                        "state": "assigned",
                    },
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_ids": [],
                        "product_uom_qty": 0,
                        "quantity": 0,
                        "state": "cancel",
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_ids": [],
                        "product_uom_qty": 0,
                        "quantity": 0,
                        "state": "cancel",
                    },
                ],
            )
        for pick in pickings_step_default:
            self.assertRecordValues(
                pick.move_ids,
                [
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_ids": self.lot_plns_1.ids,
                        "product_uom_qty": 5.0,
                        "quantity": 5.0,
                        "state": "assigned",
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_ids": self.serial_no_stock_1.ids,
                        "product_uom_qty": 1.0,
                        "quantity": 1.0,
                        "state": "assigned",
                    },
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_ids": [],
                        "product_uom_qty": 0,
                        "quantity": 0,
                        "state": "cancel",
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_ids": [],
                        "product_uom_qty": 0.0,
                        "quantity": 0.0,
                        "state": "cancel",
                    },
                ],
            )
        self.assertRecordValues(
            delivery_out_whA.move_ids,
            [
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_ids": self.lot_plns_1.ids,
                    "product_uom_qty": 4.0,
                    "quantity": 4.0,
                    "state": "assigned",
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_ids": self.serial_no_stock_1.ids,
                    "product_uom_qty": 1.0,
                    "quantity": 1.0,
                    "state": "assigned",
                },
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_ids": [],
                    "product_uom_qty": 0.0,
                    "quantity": 0.0,
                    "state": "cancel",
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_ids": [],
                    "product_uom_qty": 0.0,
                    "quantity": 0.0,
                    "state": "cancel",
                },
            ],
        )
        self.assertRecordValues(
            delivery_out_default.move_ids,
            [
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_ids": self.lot_plns_1.ids,
                    "product_uom_qty": 5.0,
                    "quantity": 5.0,
                    "state": "assigned",
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_ids": self.serial_no_stock_1.ids,
                    "product_uom_qty": 1.0,
                    "quantity": 1.0,
                    "state": "assigned",
                },
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_ids": [],
                    "product_uom_qty": 0.0,
                    "quantity": 0.0,
                    "state": "cancel",
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_ids": [],
                    "product_uom_qty": 0.0,
                    "quantity": 0.0,
                    "state": "cancel",
                },
            ],
        )
        for pick in pickings_step_whA:
            self.assertRecordValues(
                pick.move_ids.move_line_ids,
                [
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_id": self.lot_plns_1.id,
                        "quantity": 4.0,
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_id": self.serial_no_stock_1.id,
                        "quantity": 1.0,
                    },
                ],
            )
        for pick in pickings_step_default:
            self.assertRecordValues(
                pick.move_ids.move_line_ids,
                [
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_id": self.lot_plns_1.id,
                        "quantity": 5.0,
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_id": self.serial_no_stock_1.id,
                        "quantity": 1.0,
                    },
                ],
            )
        self.assertRecordValues(
            delivery_out_whA.move_ids.move_line_ids,
            [
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_id": self.lot_plns_1.id,
                    "quantity": 4.0,
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_id": self.serial_no_stock_1.id,
                    "quantity": 1.0,
                },
            ],
        )
        self.assertRecordValues(
            delivery_out_default.move_ids.move_line_ids,
            [
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_id": self.lot_plns_1.id,
                    "quantity": 5.0,
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_id": self.serial_no_stock_1.id,
                    "quantity": 1.0,
                },
            ],
        )

        self.env.user.write({"property_warehouse_id": wh_other.id})
        self._unlink_product(self.product_lot_no_stock, [0])
        self._unlink_product(self.product_sn_no_stock, [0])
        self.env.user.write({"property_warehouse_id": wh_user.id})
        self._unlink_product(self.product_lot_no_stock, [0])
        self._unlink_product(self.product_sn_no_stock, [0])

        for pick in pickings_step_whA:
            self.assertRecordValues(
                pick.move_ids,
                [
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_ids": [],
                        "product_uom_qty": 0.0,
                        "quantity": 0.0,
                        "state": "cancel",
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_ids": [],
                        "product_uom_qty": 0.0,
                        "quantity": 0.0,
                        "state": "cancel",
                    },
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_ids": [],
                        "product_uom_qty": 0.0,
                        "quantity": 0.0,
                        "state": "cancel",
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_ids": [],
                        "product_uom_qty": 0.0,
                        "quantity": 0.0,
                        "state": "cancel",
                    },
                ],
            )
        for pick in pickings_step_default:
            self.assertRecordValues(
                pick.move_ids,
                [
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_ids": [],
                        "product_uom_qty": 0.0,
                        "quantity": 0.0,
                        "state": "cancel",
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_ids": [],
                        "product_uom_qty": 0.0,
                        "quantity": 0.0,
                        "state": "cancel",
                    },
                    {
                        "product_id": self.product_lot_no_stock.id,
                        "trace_ids": [],
                        "product_uom_qty": 0.0,
                        "quantity": 0.0,
                        "state": "cancel",
                    },
                    {
                        "product_id": self.product_sn_no_stock.id,
                        "trace_ids": [],
                        "product_uom_qty": 0.0,
                        "quantity": 0.0,
                        "state": "cancel",
                    },
                ],
            )
        self.assertRecordValues(
            delivery_out_whA.move_ids,
            [
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_ids": [],
                    "product_uom_qty": 0.0,
                    "quantity": 0.0,
                    "state": "cancel",
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_ids": [],
                    "product_uom_qty": 0.0,
                    "quantity": 0.0,
                    "state": "cancel",
                },
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_ids": [],
                    "product_uom_qty": 0.0,
                    "quantity": 0.0,
                    "state": "cancel",
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_ids": [],
                    "product_uom_qty": 0.0,
                    "quantity": 0.0,
                    "state": "cancel",
                },
            ],
        )
        self.assertRecordValues(
            delivery_out_default.move_ids,
            [
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_ids": [],
                    "product_uom_qty": 0.0,
                    "quantity": 0.0,
                    "state": "cancel",
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_ids": [],
                    "product_uom_qty": 0.0,
                    "quantity": 0.0,
                    "state": "cancel",
                },
                {
                    "product_id": self.product_lot_no_stock.id,
                    "trace_ids": [],
                    "product_uom_qty": 0.0,
                    "quantity": 0.0,
                    "state": "cancel",
                },
                {
                    "product_id": self.product_sn_no_stock.id,
                    "trace_ids": [],
                    "product_uom_qty": 0.0,
                    "quantity": 0.0,
                    "state": "cancel",
                },
            ],
        )
        for pick in self.task.sale_order_id.picking_ids:
            self.assertFalse(pick.move_ids.move_line_ids)

        for pick in self.task.sale_order_id.picking_ids:
            self.assertEqual("cancel", pick.state, "the delivery should be canceled")

    def test_multi_routing_update_quantity_and_lot_id_on_serial_product(self):
        user_warehouse = self.project_user._get_default_warehouse_id()
        user_warehouse.write({"delivery_steps": "pick_pack_ship"})
        self.task.write({"partner_id": self.partner_1.id})
        self.task._fsm_get_or_create_sale_order()

        self.warehouse_A.write({"delivery_steps": "pick_pack_ship"})
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})

        self._add_lot_product(
            self.product_lot_no_stock, [{"trace_id": self.lot_plns_1.id, "qty": 4}]
        )
        self.env.user.write({"property_warehouse_id": user_warehouse.id})
        self._add_lot_product(
            self.product_lot_no_stock, [{"trace_id": self.lot_plns_1.id, "qty": 3}]
        )
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})

        self._update_product(
            self.product_lot_no_stock,
            [{"index": 0, "qty": 6, "trace_id": self.lot_plns_1}],
        )
        self.env.user.write({"property_warehouse_id": user_warehouse.id})
        self._update_product(
            self.product_lot_no_stock,
            [{"index": 1, "qty": 6, "trace_id": self.lot_plns_1}],
        )
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})

        for pick in self.task.sale_order_id.picking_ids:
            self.assertEqual(6, pick.move_ids[0].move_line_ids[0].quantity)
            self.assertEqual(
                self.lot_plns_1, pick.move_ids[0].move_line_ids[0].trace_id
            )

        self._update_product(
            self.product_lot_no_stock,
            [{"index": 0, "qty": 2, "trace_id": self.lot_plns_1}],
        )
        self.env.user.write({"property_warehouse_id": user_warehouse.id})
        self._update_product(
            self.product_lot_no_stock,
            [{"index": 1, "qty": 2, "trace_id": self.lot_plns_1}],
        )
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})

        for pick in self.task.sale_order_id.picking_ids:
            self.assertEqual(2, pick.move_ids[0].move_line_ids[0].quantity)
            self.assertEqual(
                self.lot_plns_1, pick.move_ids[0].move_line_ids[0].trace_id
            )

        self._update_product(
            self.product_lot_no_stock,
            [{"index": 0, "qty": 2, "trace_id": self.lot_plns_2}],
        )
        self.env.user.write({"property_warehouse_id": user_warehouse.id})
        self._update_product(
            self.product_lot_no_stock,
            [{"index": 1, "qty": 2, "trace_id": self.lot_plns_2}],
        )
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})
        picking_step = self.task.sale_order_id.picking_ids
        for pick in picking_step:
            self.assertEqual(2, pick.move_ids.move_line_ids.quantity)
            self.assertEqual(self.lot_plns_2, pick.move_ids.move_line_ids.trace_id)

        self._add_serial_product(self.product_sn_no_stock, [self.serial_no_stock_1.id])
        self.env.user.write({"property_warehouse_id": user_warehouse.id})
        self._add_serial_product(self.product_sn_no_stock, [self.serial_no_stock_1.id])
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})
        self._update_product(
            self.product_sn_no_stock,
            [{"index": 0, "qty": 1, "trace_id": self.serial_no_stock_2}],
        )
        self.env.user.write({"property_warehouse_id": user_warehouse.id})
        self._update_product(
            self.product_sn_no_stock,
            [{"index": 1, "qty": 1, "trace_id": self.serial_no_stock_2}],
        )
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})

        for pick in picking_step:
            self.assertEqual(1, pick.move_ids.move_line_ids[1].quantity)
            self.assertEqual(
                self.serial_no_stock_2, pick.move_ids.move_line_ids[1].trace_id
            )

        self._update_product(
            self.product_sn_no_stock,
            [{"index": 0, "qty": 1, "trace_id": self.serial_no_stock_1}],
        )
        self.task.action_fsm_validate()
        picking_out = self.task.sale_order_id.picking_ids.filtered(
            lambda p: p.picking_type_id.code == "outgoing"
        )
        serial_moves = picking_out.move_ids.filtered(
            lambda m: m.product_id == self.product_sn_no_stock
        )
        self.assertEqual(len(serial_moves), 2)
        self.assertEqual(
            serial_moves.move_line_ids.trace_id,
            self.serial_no_stock_1 | self.serial_no_stock_2,
        )
        for move in serial_moves:
            self.assertEqual(move.move_line_ids.quantity, 1)
            self.assertEqual(
                move.move_line_ids.trace_id, move.sale_line_id.fsm_trace_id
            )
        for pick in self.task.sale_order_id.picking_ids:
            self.assertEqual("done", pick.state, "the delivery should be validated")

    def test_multi_routing_serial_product_with_same_lot_id(self):
        user_warehouse = self.project_user._get_default_warehouse_id()
        user_warehouse.write({"delivery_steps": "pick_pack_ship"})
        self.task.write({"partner_id": self.partner_1.id})
        self.task._fsm_get_or_create_sale_order()

        self._add_lot_product(
            self.product_lot_no_stock,
            [
                {"trace_id": self.lot_plns_1.id, "qty": 1},
                {"trace_id": self.lot_plns_1.id, "qty": 2},
            ],
        )
        self.warehouse_A.write({"delivery_steps": "pick_pack_ship"})
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})
        self._add_lot_product(
            self.product_lot_no_stock,
            [
                {"trace_id": self.lot_plns_1.id, "qty": 1},
                {"trace_id": self.lot_plns_1.id, "qty": 2},
            ],
        )

        picking_step = (
            self.task.sale_order_id.picking_ids[0]
            | self.task.sale_order_id.picking_ids[1]
        )

        for pick in picking_step:
            self.assertEqual(1, pick.move_ids[0].move_line_ids[0].quantity)
            self.assertEqual(2, pick.move_ids[1].move_line_ids[0].quantity)
            self.assertEqual(
                self.lot_plns_1, pick.move_ids[0].move_line_ids[0].trace_id
            )

        self.task.action_fsm_validate()
        picking_out = self.task.sale_order_id.picking_ids.filtered(
            lambda p: p.picking_type_id.code == "outgoing"
        )
        for pick in picking_out:
            self.assertEqual(1, pick.move_ids[0].move_line_ids[0].quantity)
            self.assertEqual(
                self.lot_plns_1, pick.move_ids[0].move_line_ids[0].trace_id
            )
            self.assertEqual(2, pick.move_ids[1].move_line_ids[0].quantity)
            self.assertEqual(
                self.lot_plns_1, pick.move_ids[1].move_line_ids[0].trace_id
            )
        for pick in self.task.sale_order_id.picking_ids:
            self.assertEqual("done", pick.state, "the delivery should be validated")

    def test_multi_routing_add_product_to_done_task(self):
        user_warehouse = self.project_user._get_default_warehouse_id()
        user_warehouse.write({"delivery_steps": "pick_pack_ship"})
        self.task.write({"partner_id": self.partner_1.id})
        self.task._fsm_get_or_create_sale_order()

        self.warehouse_A.write({"delivery_steps": "pick_pack_ship"})
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})

        self._add_lot_product(
            self.product_lot_no_stock,
            [
                {"trace_id": self.lot_plns_1.id, "qty": 1},
                {"trace_id": self.lot_plns_1.id, "qty": 2},
            ],
        )
        self.env.user.write({"property_warehouse_id": user_warehouse.id})
        self._add_lot_product(
            self.product_lot_no_stock,
            [
                {"trace_id": self.lot_plns_1.id, "qty": 1},
                {"trace_id": self.lot_plns_1.id, "qty": 2},
            ],
        )
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})

        self.task.action_fsm_validate()
        for pick in self.task.sale_order_id.picking_ids:
            self.assertEqual("done", pick.state, "the delivery should be validated")
        old_pickings = self.task.sale_order_id.picking_ids

        self._add_lot_product(
            self.product_lot_no_stock,
            [
                {"trace_id": self.lot_plns_1.id, "qty": 1},
                {"trace_id": self.lot_plns_1.id, "qty": 2},
            ],
        )
        self.env.user.write({"property_warehouse_id": user_warehouse.id})
        self._add_lot_product(
            self.product_lot_no_stock,
            [
                {"trace_id": self.lot_plns_1.id, "qty": 1},
                {"trace_id": self.lot_plns_1.id, "qty": 2},
            ],
        )
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})
        self.assertEqual(
            8, len(self.task.sale_order_id.picking_ids)
        )

        picking_step = self.task.sale_order_id.picking_ids - old_pickings
        for pick in picking_step:
            self.assertEqual(1, pick.move_ids[0].move_line_ids[0].quantity)
            self.assertEqual(
                self.lot_plns_1, pick.move_ids[0].move_line_ids[0].trace_id
            )
            self.assertEqual(2, pick.move_ids[1].move_line_ids[0].quantity)
            self.assertEqual(
                self.lot_plns_1, pick.move_ids[1].move_line_ids[0].trace_id
            )
        self.task.action_fsm_validate()

        picking_out = (
            self.task.sale_order_id.picking_ids.filtered(
                lambda p: p.picking_type_id == user_warehouse.out_type_id
            )
            - old_pickings
        )
        for pick in picking_out:
            self.assertEqual(1, pick.move_ids[0].move_line_ids[0].quantity)
            self.assertEqual(
                self.lot_plns_1, pick.move_ids[0].move_line_ids[0].trace_id
            )
            self.assertEqual(2, pick.move_ids[1].move_line_ids[0].quantity)
            self.assertEqual(
                self.lot_plns_1, pick.move_ids[1].move_line_ids[0].trace_id
            )

        for pick in self.task.sale_order_id.picking_ids:
            self.assertEqual("done", pick.state, "the delivery should be validated")
        self.assertEqual(12, len(self.task.sale_order_id.picking_ids))

    def _unlink_product(self, product, line_indexes):
        wizard_action = product.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            wizard_action["res_id"]
        )
        wizard.write(
            {
                "tracking_line_ids": [
                    Command.unlink(wizard.tracking_line_ids[index].id)
                    for index in line_indexes
                ],
            }
        )
        wizard.action_generate_lot()

    def _update_product(self, product, lines):
        wizard_action = product.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            wizard_action["res_id"]
        )
        for line in lines:
            wizard.tracking_line_ids[line["index"]].quantity = line["qty"]
            wizard.tracking_line_ids[line["index"]].trace_id = line["trace_id"]
        wizard.action_generate_lot()

    def _add_serial_product(self, product, lines):
        wizard_action = product.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            wizard_action["res_id"]
        )
        wizard.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "trace_id": line,
                        }
                    )
                    for line in lines
                ],
            }
        )
        wizard.action_generate_lot()

    def _add_lot_product(self, product, lines):
        wizard_action = product.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            wizard_action["res_id"]
        )
        wizard.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "quantity": line["qty"],
                            "trace_id": line["trace_id"],
                        }
                    )
                    for line in lines
                ],
            }
        )
        wizard.action_generate_lot()

    def test_fsm_delivered_timesheet(self):
        self.task.write({"partner_id": self.partner_1.id})
        product = self.service_product_delivered.with_context(
            {"fsm_task_id": self.task.id}
        )
        product.type = "service"
        product.service_policy = "delivered_timesheet"
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        sale_order = self.task.sale_order_id
        sale_order_line = self.env["sale.order.line"].create(
            {
                "product_id": product.id,
                "order_id": sale_order.id,
                "name": "sales order line 0",
                "product_qty": 4,
                "task_id": self.task.id,
            }
        )
        self.task.sale_line_id = sale_order_line.id
        timesheet = self.env["account.analytic.line"].create(
            {
                "name": "Test Line",
                "project_id": self.task.project_id.id,
                "task_id": self.task.id,
                "date": datetime.now(),
                "unit_amount": 2,
                "employee_id": self.employee_user2.id,
            }
        )
        self.task.with_user(self.project_user).action_fsm_validate()
        self.assertEqual(
            sale_order.line_ids[0].qty_transferred,
            timesheet.unit_amount,
            "The delivered quantity should be the same as the timesheet amount",
        )
        self.assertEqual(
            sale_order.line_ids[0].qty_to_invoice,
            timesheet.unit_amount,
            "The quantity to invoice should be the same as the timesheet amount",
        )

    def test_child_location_dispatching_serial_number(self):
        parent_location = self.warehouse.lot_stock_id
        child_location = self.env["stock.location"].create(
            {
                "name": "Shell",
                "location_id": parent_location.id,
            }
        )
        product = self.env["product.product"].create(
            {
                "name": "Cereal",
                "is_storable": True,
                "tracking": "serial",
            }
        )
        sn1 = self.env["product.trace"].create(
            {
                "name": "SN0001",
                "product_id": product.id,
            }
        )
        task_sn = self.env["project.task"].create(
            {
                "name": "Fsm task cereal",
                "user_ids": [(4, self.project_user.id)],
                "project_id": self.fsm_project.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            product, child_location, quantity=1, trace_id=sn1
        )

        self.product_a.is_storable = True
        self.env["stock.quant"]._update_available_quantity(
            self.product_a, child_location, quantity=1
        )

        task_sn.write({"partner_id": self.partner_1.id})
        task_sn.with_user(self.project_user)._fsm_get_or_create_sale_order()

        self.product_a.with_context({"fsm_task_id": task_sn.id}).set_fsm_quantity(1)
        wizard = product.with_context(
            {"fsm_task_id": task_sn.id}
        ).action_assign_serial()
        wizard_id = self.env["wizard.project.task.update.product.lot"].browse(
            wizard["res_id"]
        )
        wizard_id.write(
            {
                "tracking_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "trace_id": sn1.id,
                        },
                    )
                ]
            }
        )
        wizard_id.action_generate_lot()
        task_sn.with_user(self.project_user).action_fsm_validate()

        self.assertEqual(
            task_sn.sale_order_id.line_ids.move_ids.move_line_ids.location_id,
            child_location,
        )

    def test_multiple_fsm_task(self):
        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        sale_order = self.task.sale_order_id
        product_field_service, product_a, product_b = self.env[
            "product.product"
        ].create(
            [
                {
                    "name": "field service",
                    "list_price": 885.0,
                    "type": "service",
                    "service_policy": "delivered_timesheet",
                    "taxes_id": False,
                    "project_id": self.fsm_project.id,
                    "service_tracking": "task_global_project",
                },
                {
                    "name": "product A",
                    "list_price": 2950.0,
                    "is_storable": True,
                    "invoice_policy": "transferred",
                    "taxes_id": False,
                },
                {
                    "name": "product B",
                    "list_price": 2950.0,
                    "is_storable": True,
                    "invoice_policy": "transferred",
                    "taxes_id": False,
                },
            ]
        )
        self.env["sale.order.line"].create(
            [
                {
                    "product_id": product_field_service.id,
                    "order_id": sale_order.id,
                    "name": "sales order line 0",
                },
                {
                    "product_id": product_field_service.id,
                    "order_id": sale_order.id,
                    "name": "sales order line 1",
                },
            ]
        )

        task_sol_0 = sale_order.line_ids[0].task_id
        task_sol_1 = sale_order.line_ids[1].task_id

        product_a.with_context({"fsm_task_id": task_sol_0.id}).set_fsm_quantity(2)
        product_b.with_context({"fsm_task_id": task_sol_0.id}).set_fsm_quantity(4)
        product_a.with_context({"fsm_task_id": task_sol_1.id}).set_fsm_quantity(1)
        product_b.with_context({"fsm_task_id": task_sol_1.id}).set_fsm_quantity(3)

        self.assertEqual(
            6,
            len(sale_order.line_ids),
            "It is expected to have the 2 new sol that were created when the products were added to the task",
        )

        move_lines = sale_order.picking_ids.move_ids
        sale_order_lines = sale_order.line_ids
        self.assertEqual(
            2,
            move_lines[0].quantity,
            "quantity must be 2 as the product were added through the fsm_task",
        )
        self.assertEqual(2, move_lines[0].product_uom_qty, "quantity must be 2")
        self.assertEqual(
            product_a, move_lines[0].product_id, "product must be product a"
        )
        self.assertEqual(
            4,
            move_lines[1].quantity,
            "quantity must be 4 as the product were added through the fsm_task",
        )
        self.assertEqual(4, move_lines[1].product_uom_qty, "quantity must be 4")
        self.assertEqual(
            product_b, move_lines[1].product_id, "product must be product b"
        )
        self.assertEqual(
            1,
            move_lines[2].quantity,
            "quantity must be 1 as the product were added through the fsm_task",
        )
        self.assertEqual(1, move_lines[2].product_uom_qty, "quantity must be 1")
        self.assertEqual(
            product_a, move_lines[2].product_id, "product must be product a"
        )
        self.assertEqual(
            3,
            move_lines[3].quantity,
            "quantity must be 3 as the product were added through the fsm_task",
        )
        self.assertEqual(3, move_lines[3].product_uom_qty, "quantity must be 3")
        self.assertEqual(
            product_b, move_lines[3].product_id, "product must be product b"
        )

        task_sol_0.with_user(self.project_user).action_fsm_validate()
        self.assertEqual(
            2,
            sale_order_lines[2].qty_transferred,
            "quantity delivered must be set to 2",
        )
        self.assertEqual(
            4,
            sale_order_lines[3].qty_transferred,
            "quantity delivered must be set to 4",
        )
        self.assertEqual(
            0,
            sale_order_lines[4].qty_transferred,
            "quantity delivered must not change, since its task is not yet marked as done",
        )
        self.assertEqual(
            0,
            sale_order_lines[5].qty_transferred,
            "quantity delivered must not change, since its task is not yet marked as done",
        )
        self.assertEqual(
            "assigned",
            sale_order.picking_ids[0].state,
            "delivery's state must be done as a backorder with the remaining qty was created",
        )

        task_sol_1.with_user(self.project_user).action_fsm_validate()
        self.assertEqual(
            2,
            sale_order_lines[2].qty_transferred,
            "marking the next task as done must not change the precedent validation",
        )
        self.assertEqual(
            4,
            sale_order_lines[3].qty_transferred,
            "marking the next task as done must not change the precedent validation",
        )
        self.assertEqual(
            1,
            sale_order_lines[4].qty_transferred,
            "quantity delivered must be set to 1",
        )
        self.assertEqual(
            3,
            sale_order_lines[5].qty_transferred,
            "quantity delivered must be set to 3",
        )
        self.assertEqual("done", sale_order.picking_ids[0].state)

    def test_lot_picking(self):
        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        wizard_action = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            wizard_action["res_id"]
        )
        wizard.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_lot.id,
                            "quantity": 3,
                            "trace_id": self.lot_id3.id,
                        }
                    )
                ]
            }
        )
        wizard.action_generate_lot()
        self.assertEqual(
            len(self.task.sale_order_id.line_ids), 1, "There is 1 order line"
        )
        line = self.task.sale_order_id.line_ids
        self.assertEqual(len(line.move_ids), 1, "There is 1 move")
        self.assertEqual(len(line.move_ids.move_line_ids), 1, "There is 1 move line")
        move = line.move_ids
        move_line = move.move_line_ids
        self.assertEqual(move.product_uom_qty, 3, "The move quantity is 3")
        self.assertEqual(move_line.trace_id, self.lot_id3, "Lot stay the same.")
        self.assertEqual(move_line.quantity, 3, "We deliver 3")
        wizard_action = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            wizard_action["res_id"]
        )
        new_tracking_line = self.env[
            "wizard.project.task.update.product.lot.line"
        ].create(
            {
                "product_id": self.product_lot.id,
                "quantity": 2,
                "trace_id": self.lot_id2.id,
            }
        )
        wizard.write({"tracking_line_ids": [Command.set([new_tracking_line.id])]})
        wizard.action_generate_lot()
        self.assertEqual(
            len(self.task.sale_order_id.line_ids), 2, "There are 2 order lines"
        )
        previous_line = self.task.sale_order_id.line_ids[0]
        self.assertEqual(
            previous_line.product_qty, 0, "The product qty is set to 0 on previous line"
        )
        self.assertEqual(len(previous_line.move_ids), 1, "There is 1 move")
        self.assertEqual(
            previous_line.move_ids[0].state, "cancel", "The move is cancelled"
        )
        self.assertEqual(
            previous_line.move_ids[0].product_uom_qty, 0, "The move quantity is 0"
        )
        self.assertFalse(previous_line.move_ids.move_line_ids, "There is no move line")
        new_line = self.task.sale_order_id.line_ids[1]
        self.assertEqual(len(new_line.move_ids), 1, "There is 1 move")
        self.assertEqual(
            len(new_line.move_ids.move_line_ids), 1, "There is 1 move line"
        )
        new_move = new_line.move_ids
        new_move_line = new_move.move_line_ids
        self.assertEqual(new_move.product_uom_qty, 2, "The move quantity is 2")
        self.assertEqual(new_move_line.trace_id, self.lot_id2, "Lot stay the same.")
        self.assertEqual(new_move_line.quantity, 2, "We deliver 2")
        self.assertTrue(
            new_move.state == "assigned",
            "Move state set to assigned prior to FSM task validation",
        )
        self.task.with_user(self.project_user).action_fsm_validate()
        self.assertTrue(new_move.state == "done", "Move from SOL2 state set to done")

    def test_warehouse(self):
        warehouse_C = self.env["stock.warehouse"].create(
            {
                "name": "WH C",
                "code": "WHC",
                "company_id": self.env.company.id,
                "partner_id": self.env.company.partner_id.id,
            }
        )
        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        default_warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self.task.sale_order_id.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_qty": 1,
                        }
                    ),
                ],
            }
        )
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})
        product = self.storable_product_ordered.with_context(
            {"fsm_task_id": self.task.id}
        )
        product.set_fsm_quantity(1)
        self.env.user.write({"property_warehouse_id": self.warehouse_B.id})
        wizard_action = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            wizard_action["res_id"]
        )
        wizard.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_lot.id,
                            "quantity": 3,
                            "trace_id": self.lot_id3.id,
                        }
                    ),
                ],
            }
        )
        wizard.action_generate_lot()
        self.env.user.write({"property_warehouse_id": warehouse_C.id})
        wizard_action = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            wizard_action["res_id"]
        )
        wizard.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_lot.id,
                            "quantity": 3,
                            "trace_id": self.lot_id3.id,
                        }
                    ),
                ],
            }
        )
        wizard.action_generate_lot()
        self.assertEqual(
            len(self.task.sale_order_id.line_ids), 4, "Four lines are added"
        )
        first_line, second_line, third_line, fourth_line = (
            self.task.sale_order_id.line_ids
        )
        self.assertTrue(
            all(
                len(sol.move_ids.move_line_ids) == 1
                for sol in self.task.sale_order_id.line_ids
            ),
            "There is 1 move line on each SOL",
        )
        self.assertEqual(
            first_line.move_ids.warehouse_id,
            default_warehouse,
            "First SOL move warehouse is the company default one",
        )
        self.assertEqual(
            second_line.move_ids.warehouse_id,
            self.warehouse_A,
            "Second SOL move warehouse is self.warehouse_B (as set as default)",
        )
        self.assertEqual(
            third_line.move_ids.warehouse_id,
            self.warehouse_B,
            "Third SOL move warehouse is self.warehouse_B (as set as default)",
        )
        self.assertEqual(
            fourth_line.move_ids.warehouse_id,
            warehouse_C,
            "Fourth SOL move warehouse is warehouse_C (as set as default)",
        )

    def test_serial_missing_on_empty_sol(self):
        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        wizard_action = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            wizard_action["res_id"]
        )
        wizard.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_lot.id,
                            "quantity": 3,
                            "trace_id": self.lot_id3.id,
                        }
                    ),
                ],
            }
        )
        wizard.action_generate_lot()
        self.assertEqual(
            self.product_lot.serial_missing, False, "serial_missing is Falsy"
        )
        wizard_action = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            wizard_action["res_id"]
        )
        wizard.tracking_line_ids.unlink()
        wizard.action_generate_lot()
        self.assertEqual(len(self.task.sale_order_id.line_ids), 1, "There is one SOL")
        sol = self.task.sale_order_id.line_ids[0]
        self.assertEqual(sol.product_qty, 0, "The quantity on the SOL is set to 0")
        self.assertEqual(sol.qty_transferred, 0, "The quantity on the SOL is set to 0")
        self.assertEqual(
            self.product_lot.serial_missing, False, "serial_missing is Falsy"
        )

    def test_quantity_decreasable_on_different_warehouses(self):
        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})
        product = self.storable_product_ordered.with_context(
            {"fsm_task_id": self.task.id}
        )
        product.set_fsm_quantity(2)
        self.assertTrue(product.quantity_decreasable)
        self.env.user.write({"property_warehouse_id": self.warehouse_B.id})
        product._compute_quantity_decreasable()
        self.assertFalse(product.quantity_decreasable)
        product.fsm_add_quantity()
        self.assertTrue(product.quantity_decreasable)
        product.fsm_remove_quantity()
        product.fsm_add_quantity()
        with self.assertRaises(UserError):
            product.set_fsm_quantity(1)
        self.assertEqual(
            len(self.task.sale_order_id.line_ids), 1, "There is 1 order line"
        )
        self.task.sale_order_id.line_ids.move_ids.picked = True
        self.task.sale_order_id.line_ids.move_ids._action_done()
        self.assertFalse(product.quantity_decreasable)

    def test_quantity_decreasable_on_multicompany(self):
        company_A = self.env.company
        company_B = self.env["res.company"].search(
            [("id", "!=", company_A.id)], limit=1
        )
        warehouse_B = self.env["stock.warehouse"].search(
            [("company_id", "=", company_B.id)], limit=1
        )
        if not warehouse_B:
            warehouse_B = (
                self.env["stock.warehouse"]
                .sudo()
                .create({"name": "WH", "code": "WH-B", "company_id": company_B.id})
            )
        self.env.user.write(
            {
                "company_ids": [(6, 0, [company_A.id, company_B.id])],
                "company_id": company_A.id,
            }
        )
        warehouse_B = self.env.user.with_company(company_B)._get_default_warehouse_id()
        if not warehouse_B:
            warehouse_B = (
                self.env["stock.warehouse"]
                .sudo()
                .create({"name": "WH", "code": "WH-B", "company_id": company_B.id})
            )
            self.assertEqual(
                self.env.user.with_company(company_B)._get_default_warehouse_id(),
                warehouse_B,
            )

        customer = self.env["res.partner"].create(
            {"name": "Customer", "company_id": company_B.id}
        )

        project = self.env["project.project"].create(
            {
                "name": "test-project",
                "allow_billable": True,
                "allow_material": True,
            }
        )
        fsm_task = self.env["project.task"].create(
            {
                "name": "Fsm task",
                "project_id": project.id,
                "partner_id": customer.id,
            }
        )
        fsm_task.with_user(self.env.user)._fsm_get_or_create_sale_order()
        product = self.storable_product_ordered.with_context(
            {"fsm_task_id": fsm_task.id}
        )

        product.set_fsm_quantity(2)
        product._compute_quantity_decreasable()
        self.assertTrue(product.quantity_decreasable)
        self.assertEqual(product.quantity_decreasable_sum, 2)

        move = self.env["stock.move"].search([("product_id", "=", product.id)], limit=1)
        self.assertEqual(
            move.warehouse_id.id,
            warehouse_B.id,
            "Reservation happened on a wrong warehouse",
        )

    def test_is_same_warehouse(self):
        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        self.env.user.write({"property_warehouse_id": self.warehouse_A.id})
        wizard_action = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            wizard_action["res_id"]
        )
        wizard.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_lot.id,
                            "quantity": 3,
                            "trace_id": self.lot_id3.id,
                        }
                    ),
                ],
            }
        )
        self.assertEqual(
            wizard.tracking_line_ids[0].warehouse_id,
            self.warehouse_A,
            "`wizard.project.task.update.product.lot.line` warehouse is the default one on new tracking lines",
        )
        self.assertTrue(wizard.tracking_line_ids[0].is_same_warehouse)
        self.assertTrue(wizard.is_same_warehouse)
        wizard.action_generate_lot()
        self.env.user.write({"property_warehouse_id": self.warehouse_B.id})
        wizard_action = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            wizard_action["res_id"]
        )
        self.assertFalse(wizard.tracking_line_ids[0].is_same_warehouse)
        self.assertFalse(wizard.is_same_warehouse)

    def test_fsm_task_and_tracked_products_reservation(self):
        self.warehouse.delivery_steps = "pick_ship"
        self.task.write({"partner_id": self.partner_1.id})
        self.task._fsm_get_or_create_sale_order()

        product_01_sn, product_02_sn, product_03_lot = (
            self.env["product.product"]
            .create(
                [
                    {
                        "name": "Product SN 01",
                        "is_storable": True,
                        "tracking": "serial",
                    },
                    {
                        "name": "Product SN 02",
                        "is_storable": True,
                        "tracking": "serial",
                    },
                    {
                        "name": "Product LOT",
                        "is_storable": True,
                        "tracking": "lot",
                    },
                ]
            )
            .with_context({"fsm_task_id": self.task.id})
        )

        p01sn01, p01sn02, p01sn03, p02sn01, p03lot01, p03lot02 = self.env[
            "product.trace"
        ].create(
            [
                {
                    "name": str(i),
                    "product_id": p.id,
                }
                for i, p in enumerate(
                    [
                        product_01_sn,
                        product_01_sn,
                        product_01_sn,
                        product_02_sn,
                        product_03_lot,
                        product_03_lot,
                    ]
                )
            ]
        )

        self.env["stock.quant"]._update_available_quantity(
            product_01_sn, self.warehouse.lot_stock_id, 1, trace_id=p01sn01
        )
        self.env["stock.quant"]._update_available_quantity(
            product_01_sn, self.warehouse.lot_stock_id, 1, trace_id=p01sn02
        )
        self.env["stock.quant"]._update_available_quantity(
            product_01_sn, self.warehouse.lot_stock_id, 1, trace_id=p01sn03
        )
        self.env["stock.quant"]._update_available_quantity(
            product_02_sn, self.warehouse.lot_stock_id, 1, trace_id=p02sn01
        )
        self.env["stock.quant"]._update_available_quantity(
            product_03_lot, self.warehouse.lot_stock_id, 10, trace_id=p03lot01
        )
        self.env["stock.quant"]._update_available_quantity(
            product_03_lot, self.warehouse.lot_stock_id, 10, trace_id=p03lot02
        )

        action = product_01_sn.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            action["res_id"]
        )
        wizard.tracking_line_ids = [
            (0, 0, {"trace_id": p01sn01.id, "quantity": 1.0}),
            (0, 0, {"trace_id": p01sn03.id, "quantity": 1.0}),
        ]
        wizard.action_generate_lot()

        action = product_02_sn.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            action["res_id"]
        )
        wizard.tracking_line_ids = [
            (0, 0, {"trace_id": p02sn01.id, "quantity": 1.0}),
        ]
        wizard.action_generate_lot()

        action = product_03_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            action["res_id"]
        )
        wizard.tracking_line_ids = [
            (0, 0, {"trace_id": p03lot01.id, "quantity": 3.0}),
            (0, 0, {"trace_id": p03lot02.id, "quantity": 4.0}),
        ]
        wizard.action_generate_lot()

        so = self.task.sale_order_id
        picking = so.picking_ids
        self.assertRecordValues(
            picking.move_ids.move_line_ids,
            [
                {
                    "product_id": product_01_sn.id,
                    "trace_id": p01sn01.id,
                    "quantity": 1.0,
                },
                {
                    "product_id": product_01_sn.id,
                    "trace_id": p01sn03.id,
                    "quantity": 1.0,
                },
                {
                    "product_id": product_02_sn.id,
                    "trace_id": p02sn01.id,
                    "quantity": 1.0,
                },
                {
                    "product_id": product_03_lot.id,
                    "trace_id": p03lot01.id,
                    "quantity": 3.0,
                },
                {
                    "product_id": product_03_lot.id,
                    "trace_id": p03lot02.id,
                    "quantity": 4.0,
                },
            ],
        )
        picking.button_validate()

        delivery = so.picking_ids - picking
        self.assertRecordValues(
            delivery.move_ids.move_line_ids,
            [
                {
                    "product_id": product_01_sn.id,
                    "trace_id": p01sn01.id,
                    "quantity": 1.0,
                },
                {
                    "product_id": product_01_sn.id,
                    "trace_id": p01sn03.id,
                    "quantity": 1.0,
                },
                {
                    "product_id": product_02_sn.id,
                    "trace_id": p02sn01.id,
                    "quantity": 1.0,
                },
                {
                    "product_id": product_03_lot.id,
                    "trace_id": p03lot01.id,
                    "quantity": 3.0,
                },
                {
                    "product_id": product_03_lot.id,
                    "trace_id": p03lot02.id,
                    "quantity": 4.0,
                },
            ],
        )

    def test_mark_as_done_with_report_enable_and_multi_step(self):

        self.project_user.group_ids += self.env.ref("stock.group_reception_report")
        self.warehouse.delivery_steps = "pick_pack_ship"
        self.task.partner_id = self.partner_1.id
        self.consu_product_ordered.with_user(self.project_user).with_context(
            {"fsm_task_id": self.task.id}
        ).fsm_add_quantity()
        self.task.with_user(self.project_user).action_fsm_validate()

        self.assertTrue(self.project_user.has_group("stock.group_reception_report"))
        self.assertTrue(
            all(
                self.task.sale_order_id.picking_ids.mapped(lambda p: p.state == "done")
            ),
            "Pickings should be set as done",
        )

    def test_action_product_forecast_report(self):
        self.task.partner_id = self.partner_1
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        self.task.sale_order_id.write(
            {
                "warehouse_id": self.warehouse_A.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_lot.id,
                            "product_qty": 1,
                            "fsm_trace_id": self.lot_id2.id,
                            "task_id": self.task.id,
                        }
                    )
                ],
            }
        )
        self.env.user.property_warehouse_id = self.warehouse_B
        product_forecast_report_action = self.product_lot.with_context(
            fsm_task_id=self.task.id
        ).action_product_forecast_report()
        self.assertEqual(
            product_forecast_report_action["context"]["warehouse_id"],
            self.warehouse_A.id,
            "Should follow the warehouse set in the sale order linked to the fsm task.",
        )

        self.task.sale_order_id = False
        product_forecast_report_action = self.product_lot.with_context(
            fsm_task_id=self.task.id
        ).action_product_forecast_report()
        self.assertEqual(
            product_forecast_report_action["context"]["warehouse_id"],
            self.warehouse_B.id,
            "Should follow the user's warehouse",
        )

        self.env.user.property_warehouse_id = False
        warehouse = (
            self.env["stock.warehouse"]
            .with_company(self.task.company_id.id)
            .search([], limit=1, order="sequence")
        )
        product_forecast_report_action = self.product_lot.with_context(
            fsm_task_id=self.task.id
        ).action_product_forecast_report()
        self.assertEqual(
            product_forecast_report_action["context"]["warehouse_id"],
            warehouse.id,
            "The warehouse set should be the first one found",
        )

    def test_stock_move_customer_product_count(self):

        self.warehouse.delivery_steps = "ship_only"
        self.env.user.write({"property_warehouse_id": self.warehouse.id})

        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()

        self.task.sale_order_id.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.consu_product_ordered.id,
                            "product_qty": 3,
                        }
                    ),
                ],
            }
        )

        self.task._compute_stock_move_customer_product_total()
        self.assertEqual(
            self.task.stock_move_customer_product_count,
            3,
            "There are 3 products ready to be delivered to the customer",
        )

        self.task.sale_order_id.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.storable_product_ordered.id,
                            "product_qty": 4,
                        }
                    ),
                ],
            }
        )

        self.assertEqual(
            round(sum(self.task.sale_order_id.line_ids.move_ids.mapped("product_qty"))),
            7,
        )
        self.task._compute_stock_move_customer_product_total()
        self.assertEqual(
            self.task.stock_move_customer_product_count,
            7,
            "Adding storable product should be counted in the stock_move_customer_count even if it's not reserved yet",
        )

        storable_stock_move = self.env["stock.move"].search(
            [
                ("picking_id", "=", self.task.sale_order_id.picking_ids.id),
                ("product_id", "=", self.storable_product_ordered.id),
            ]
        )
        storable_stock_move.write({"quantity": 4})

        self.task._compute_stock_move_customer_product_total()
        self.assertEqual(
            self.task.stock_move_customer_product_count,
            7,
            "Reserved quantities of the storable product should be counted into the stock_move_customer_count",
        )

        self.consu_product_ordered.with_user(self.project_user).with_context(
            fsm_task_id=self.task.id
        ).set_fsm_quantity(5)

        self.assertEqual(
            round(
                sum(self.task.sale_order_id.line_ids.move_ids.mapped("product_uom_qty"))
            ),
            12,
        )
        self.task._compute_stock_move_customer_product_total()
        self.assertEqual(
            self.task.stock_move_customer_product_count,
            7,
            "Quantities added through the task shouldn't be counted as product to pick up",
        )

        self.env.user.write({"property_warehouse_id": self.warehouse.id})

        self.task._compute_stock_move_customer_product_total()
        self.assertEqual(self.task.stock_move_customer_product_count, 7)

        self.task.sale_order_id.picking_ids.with_context(
            skip_sms=True
        ).button_validate()

        self.task._compute_stock_move_customer_product_total()
        self.assertEqual(
            self.task.stock_move_customer_product_count,
            0,
            "Once the delivery is validated the stock_move_customer_count should be reset",
        )

    def test_tracking_product_route_order_line_info(self):
        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        sale_order = self.task.sale_order_id
        self._add_lot_product(
            self.product_lot_no_stock, [{"trace_id": self.lot_plns_1.id, "qty": 3}]
        )
        self.env["sale.order.line"].create(
            {
                "product_id": self.storable_product_ordered.id,
                "order_id": sale_order.id,
                "name": "sales order line 0",
                "product_qty": 4,
                "task_id": self.task.id,
            }
        )
        products = (
            self.storable_product_ordered
            | self.storable_product_delivered
            | self.product_lot_no_stock
            | self.product_sn_no_stock
        )
        products_catalog = sale_order.with_context(
            fsm_task_id=self.task.id
        )._get_product_catalog_order_line_info(products.ids)
        for product_id in products_catalog:
            products_catalog[product_id]["price"] = round(
                products_catalog[product_id]["price"], 3
            )
        self.assertDictEqual(
            products_catalog,
            {
                self.product_lot_no_stock.id: {
                    "quantity": 3.0,
                    "readOnly": False,
                    "deliveredQty": 0.0,
                    "tracking": True,
                    "minimumQuantityOnProduct": 0.0,
                    "price": 60,
                    "productType": "consu",
                    "uomDisplayName": "Units",
                    "code": "",
                },
                self.storable_product_ordered.id: {
                    "quantity": 4.0,
                    "readOnly": False,
                    "deliveredQty": 0.0,
                    "tracking": False,
                    "minimumQuantityOnProduct": 0.0,
                    "price": 60,
                    "productType": "consu",
                    "uomDisplayName": "Units",
                    "code": "",
                },
                self.storable_product_delivered.id: {
                    "quantity": 0,
                    "readOnly": False,
                    "deliveredQty": 0,
                    "tracking": False,
                    "minimumQuantityOnProduct": 0,
                    "price": 75.6,
                    "productType": "consu",
                    "uomDisplayName": "Units",
                    "code": "",
                },
                self.product_sn_no_stock.id: {
                    "quantity": 0,
                    "readOnly": False,
                    "deliveredQty": 0,
                    "tracking": True,
                    "minimumQuantityOnProduct": 0,
                    "price": 60,
                    "productType": "consu",
                    "uomDisplayName": "Units",
                    "code": "",
                },
            },
            "The tracked product should have the 'tracking' key set to True, even if the product was not added to the task.",
        )

    def test_fsm_task_and_tracked_product_confirmation(self):
        self.warehouse.delivery_steps = "pick_ship"
        delivery_route_2 = self.warehouse.delivery_route_id
        delivery_route_2.rule_ids[0].write(
            {
                "action": "pull",
                "picking_type_id": self.warehouse.int_type_id.id,
                "location_dest_id": delivery_route_2.rule_ids[1].location_src_id.id,
            }
        )
        delivery_route_2.rule_ids[1].write({"action": "pull"})
        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()

        product = (
            self.env["product.product"]
            .create(
                [
                    {
                        "name": "Product T",
                        "type": "consu",
                        "tracking": "none",
                        "is_storable": True,
                    }
                ]
            )
            .with_context({"fsm_task_id": self.task.id})
        )

        so = self.task.sale_order_id
        so.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_qty": 1,
                            "task_id": self.task.id,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_qty": 1,
                            "task_id": self.task.id,
                        }
                    ),
                ],
            }
        )
        self.assertEqual(
            len(so.picking_ids), 2, "There are two pickings generated, pick and ship"
        )
        picking, _dummy = so.picking_ids
        picking.write({"priority": "1"})
        self.task.with_user(self.project_user).action_fsm_validate()
        self.assertEqual(self.task.fsm_done, True)

    def test_fsm_under_warranty_task(self):
        self.task.write(
            {
                "under_warranty": True,
            }
        )
        self.task.write({"partner_id": self.partner_1.id})
        so = self.task._fsm_get_or_create_sale_order()
        action_stock_tracking = self.product_lot.with_context(
            {"fsm_task_id": self.task.id}
        ).action_assign_serial()
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            action_stock_tracking["res_id"]
        )
        wizard.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_lot.id,
                            "quantity": 3,
                            "trace_id": self.lot_id3.id,
                        }
                    )
                ]
            }
        )
        wizard.action_generate_lot()
        self.assertEqual(so.amount_total, 0)
        so.line_ids.price_unit = 500
        self.assertEqual(so.amount_total, 1500)
        wizard = self.env["wizard.project.task.update.product.lot"].browse(
            action_stock_tracking["res_id"]
        )
        wizard.write(
            {
                "tracking_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_lot.id,
                            "quantity": 8,
                            "trace_id": self.lot_id3.id,
                        }
                    )
                ]
            }
        )
        wizard.action_generate_lot()
        self.assertEqual(so.amount_total, 0)

    def test_kit_product_delivery_validate_when_mark_as_done(self):
        if self.env["ir.module.module"]._get("sale_mrp").state != "installed":
            self.skipTest(
                "If the 'sale_mrp' module isn't installed, we can't test bom!"
            )
        product_a, product_b, final_product = (
            self.env["product.product"]
            .create(
                [
                    {
                        "name": p_name,
                        "type": "consu",
                        "is_storable": True,
                        "seller_ids": [
                            Command.create(
                                {
                                    "partner_id": self.partner_1.id,
                                }
                            )
                        ],
                    }
                    for p_name in ["Comp 1", "Comp 2", "Final Product"]
                ]
            )
            .with_context({"fsm_task_id": self.task.id})
        )
        self.env["mrp.bom"].create(
            {
                "product_id": final_product.id,
                "product_tmpl_id": final_product.product_tmpl_id.id,
                "product_qty": 1,
                "consumption": "flexible",
                "type": "phantom",
                "bom_line_ids": [
                    Command.create({"product_id": product_a.id, "product_qty": 1}),
                    Command.create({"product_id": product_b.id, "product_qty": 1}),
                ],
            }
        )
        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user)._fsm_get_or_create_sale_order()
        so = self.task.sale_order_id
        so.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "product_id": final_product.id,
                            "product_qty": 1,
                            "task_id": self.task.id,
                        }
                    ),
                ],
            }
        )
        self.task.with_user(self.project_user).action_fsm_validate()
        self.assertEqual(so.picking_ids.state, "done")
