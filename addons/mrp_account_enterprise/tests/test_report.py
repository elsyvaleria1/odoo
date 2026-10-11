from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.addons.mrp_account.tests.common import TestBomPriceOperationCommon


class TestReportsCommon(TestBomPriceOperationCommon):
    @freeze_time("2022-05-28")
    def test_mrp_avg_cost_calculation(self):
        self.table_head.categ_id = self.category_avco
        self.bom_2.type = "normal"
        self.bom_2.product_uom_id = self.uom

        mo_1 = self._create_mo(self.bom_2, 10)
        mo_1.button_plan()
        wo = mo_1.workorder_ids
        wo.button_start()
        wo.duration = 100
        wo.qty_producing = 10

        mo_1.button_mark_done()

        self.plywood_sheet.standard_price = 300
        self.glass.standard_price = 30
        mo_2 = self._create_mo(self.bom_2, 20)
        mo_2.button_plan()
        wo = mo_2.workorder_ids
        wo.button_start()
        wo.duration = 200
        wo.qty_producing = 20

        mo_2.button_mark_done()

        self.env.flush_all()

        report = self.env["mrp.report"]._read_group(
            [("product_id", "=", self.table_head.id)],
            aggregates=[
                "unit_cost:avg",
                "unit_component_cost:avg",
                "unit_operation_cost:avg",
                "unit_duration:avg",
            ],
        )[0]
        unit_cost, unit_component_cost, unit_operation_cost, unit_duration = report
        self.assertEqual(self.company.currency_id.round(unit_cost), 6475)
        self.assertEqual(self.company.currency_id.round(unit_component_cost), 6425)
        self.assertEqual(self.company.currency_id.round(unit_operation_cost), 50)
        self.assertEqual(self.company.currency_id.round(unit_duration), 30)

    @freeze_time("2022-05-28")
    def test_two_operators_on_one_machine_cost_one_machine_hour(self):
        second_operator = self.env["res.users"].create(
            {"name": "Second operator", "login": "second_operator"}
        )
        self.bom_2.type = "normal"
        self.bom_2.product_uom_id = self.uom
        mo = self._create_mo(self.bom_2, 10)
        mo.button_plan()
        productive = self.env.ref("mrp.block_reason7")
        start = datetime(2022, 5, 27, 9, 0)
        for workorder in mo.workorder_ids:
            self.env["mrp.workcenter.productivity"].create(
                [
                    {
                        "workorder_id": workorder.id,
                        "workcenter_id": workorder.workcenter_id.id,
                        "loss_id": productive.id,
                        "user_id": user.id,
                        "date_start": start,
                        "date_end": start + timedelta(minutes=60),
                    }
                    for user in (self.env.user, second_operator)
                ]
            )
            workorder.qty_producing = 10
        mo.button_mark_done()
        self.env.flush_all()
        self.assertEqual(
            mo.workorder_ids.mapped("duration"), [60.0] * len(mo.workorder_ids)
        )
        (duration,) = self.env["mrp.report"]._read_group(
            [("production_id", "=", mo.id)], aggregates=["duration:sum"]
        )[0]
        self.assertEqual(duration, 60 * len(mo.workorder_ids))
