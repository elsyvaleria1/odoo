from freezegun import freeze_time

from odoo import Command
from odoo.tests import Form

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mrp.tests.common import TestMrpCommon


class TestMrpReportEmployeeCost(TestMrpCommon):
    @freeze_time("2022-05-28")
    def test_mrp_report_no_operations(self):

        self.bom_4.operation_ids = [Command.clear()]

        self.product_1.standard_price = 20
        production_form = Form(self.env["mrp.production"])
        production_form.bom_id = self.bom_4
        production_form.product_qty = 10
        mo = production_form.save()
        mo.action_confirm()

        mo_form = Form(mo)
        mo_form.qty_producing = 10
        mo = mo_form.save()
        mo.button_mark_done()

        self.env.flush_all()

        report = self.env["mrp.report"].search([("production_id", "=", mo.id)])

        self.assertEqual(report["unit_operation_cost"], 0)
        self.assertEqual(report["unit_duration"], 0)
        self.assertEqual(report["unit_component_cost"], 20)
        self.assertEqual(report["unit_cost"], 20)

    @freeze_time("2022-05-28")
    def test_mrp_report_expected_cost_fields(self):
        self.workcenter_2.write(
            {
                "costs_hour": 20,
                "employee_costs_hour": 30,
            }
        )
        comp_product = self.product_1
        comp_product.standard_price = 100
        bom_1_comp = self.bom_4
        bom_2_comp = self.bom_4.copy()
        bom_2_comp.product_qty = 2
        bom_2_comp.bom_line_ids.product_qty = 2

        mo_1 = self.env["mrp.production"].create(
            {
                "product_qty": 1,
                "bom_id": bom_1_comp.id,
            }
        )
        mo_1.action_assign()
        mo_1.button_plan()
        wo = mo_1.workorder_ids[0]
        wo.button_start()
        wo.record_production()
        mo_1.move_raw_ids.quantity = 1
        mo_1.move_raw_ids.picked = True
        mo_1.button_mark_done()
        mo_2 = self.env["mrp.production"].create(
            {
                "product_qty": 2,
                "bom_id": bom_2_comp.id,
            }
        )
        mo_2.action_assign()
        mo_2.button_plan()
        wo = mo_2.workorder_ids[0]
        wo.button_start()
        wo.record_production()
        mo_2.move_raw_ids.quantity = 2
        mo_2.move_raw_ids.picked = True
        mo_2.button_mark_done()
        self.env.flush_all()
        self.assertRecordValues(
            self.env["mrp.report"].search(
                [("production_id", "in", (mo_1.id, mo_2.id))]
            ),
            [
                {
                    "expected_component_cost_unit": 100.0,
                    "expected_employee_cost_unit": 30.0,
                    "expected_operation_cost_unit": 20.0,
                    "expected_total_cost_unit": 150.0,
                }
                for _ in range(2)
            ],
        )

    def test_mrp_report_estimated_cost(self):
        self.workcenter_2.write(
            {
                "costs_hour": 20,
                "employee_costs_hour": 33,
            }
        )
        self.bom_4.operation_ids.write(
            {
                "time_mode": "manual",
                "time_cycle": 60,
                "cost_mode": "estimated",
            }
        )
        estimated_cost_bom = self.bom_4.copy()
        estimated_cost_bom.operation_ids.cost_mode = "estimated"

        mo = self.env["mrp.production"].create(
            {
                "product_qty": 2,
                "bom_id": self.bom_4.id,
            }
        )
        mo.action_assign()
        mo.button_plan()
        mo.workorder_ids.button_start()
        mo.workorder_ids.record_production()
        mo.workorder_ids.duration = 10
        mo.move_raw_ids.quantity = 1
        mo.move_raw_ids.picked = True
        mo.button_mark_done()

        self.env.flush_all()
        self.assertRecordValues(
            self.env["mrp.report"].search([("production_id", "=", mo.id)]),
            [
                {
                    "duration": 120.0,
                    "employee_cost": 66.0,
                    "operation_cost": 40.0,
                    "total_cost": 106.0,
                    "unit_duration": 60.0,
                    "unit_employee_cost": 33.0,
                    "unit_operation_cost": 20.0,
                    "unit_cost": 53.0,
                }
            ],
        )

    def test_the_expected_operation_cost_is_the_operations_own_cost(self):
        workcenter = self.env["mrp.workcenter"].create(
            {
                "name": "Timed",
                "costs_hour": 60,
                "employee_costs_hour": 0,
                "time_start": 10,
                "time_stop": 5,
            }
        )
        workcenter.time_efficiency = 50
        operation = self.bom_4.operation_ids
        operation.write({"workcenter_id": workcenter.id, "time_mode_batch": 10})
        productions = self.env["mrp.production"]
        for _ in range(2):
            production = self.env["mrp.production"].create(
                {"product_qty": 1, "bom_id": self.bom_4.id}
            )
            production.action_confirm()
            production.workorder_ids.duration = 75
            production.qty_producing = 1
            production.move_raw_ids.picked = True
            production.button_mark_done()
            productions |= production
        self.assertEqual(productions.workorder_ids.mapped("duration"), [75, 75])
        expected = operation.with_context(
            product=self.product_6, quantity=1, unit=self.product_6.uom_id
        ).cost
        self.assertEqual(expected, 75, "(75 - 15) at 50 % is a 30-minute cycle")
        self.env.flush_all()
        manager = mail_new_test_user(
            self.env,
            login="routing_manager",
            groups="mrp.group_mrp_manager,mrp.group_mrp_routings",
        )
        for reader in (self.env.user, manager):
            self.assertEqual(
                self.env["mrp.report"]
                .with_user(reader)
                .search([("production_id", "in", productions.ids)])
                .mapped("expected_operation_cost_unit"),
                [expected, expected],
                reader.name,
            )
