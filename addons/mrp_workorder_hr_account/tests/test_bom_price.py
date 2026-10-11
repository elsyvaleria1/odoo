from odoo.libs.numbers import float_compare, float_round
from odoo.tests import Form

from odoo.addons.mrp_account.tests.common import TestBomPriceCommon


class TestBomPrice(TestBomPriceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        workcenter_from1 = Form(cls.env["mrp.workcenter"])
        workcenter_from1.name = "Workcenter"
        workcenter_from1.time_efficiency = 80
        workcenter_from1.oee_target = 100
        workcenter_from1.time_start = 15
        workcenter_from1.time_stop = 15
        workcenter_from1.costs_hour = 100
        workcenter_from1.employee_costs_hour = 200
        workcenter_1 = workcenter_from1.save()
        (
            cls.bom_1.write(
                {
                    "operation_ids": [
                        (
                            0,
                            0,
                            {
                                "name": "Cutting",
                                "workcenter_id": workcenter_1.id,
                                "time_mode": "manual",
                                "time_cycle_manual": 20,
                                "sequence": 1,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": "Drilling",
                                "workcenter_id": workcenter_1.id,
                                "time_mode": "manual",
                                "time_cycle_manual": 25,
                                "sequence": 2,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": "Fitting",
                                "workcenter_id": workcenter_1.id,
                                "time_mode": "manual",
                                "time_cycle_manual": 30,
                                "sequence": 3,
                            },
                        ),
                    ],
                }
            ),
        )
        (
            cls.bom_2.write(
                {
                    "operation_ids": [
                        (
                            0,
                            0,
                            {
                                "name": "Cutting",
                                "workcenter_id": workcenter_1.id,
                                "time_mode": "manual",
                                "time_cycle_manual": 20,
                                "sequence": 1,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": "Drilling",
                                "workcenter_id": workcenter_1.id,
                                "time_mode": "manual",
                                "time_cycle_manual": 25,
                                "sequence": 2,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": "Fitting",
                                "workcenter_id": workcenter_1.id,
                                "time_mode": "manual",
                                "time_cycle_manual": 30,
                                "sequence": 3,
                            },
                        ),
                    ],
                }
            ),
        )

    def test_compute_price_operation_cost_hr_01(self):
        self.assertEqual(
            self.dining_table.standard_price,
            1000,
            "Initial price of the Product should be 1000",
        )
        self.dining_table.button_bom_cost()
        self.assertEqual(
            float_round(self.dining_table.standard_price, precision_digits=2),
            2556.25,
        )
        self.Product.browse(
            [self.dining_table.id, self.table_head.id]
        ).action_bom_cost()
        self.assertEqual(
            float_compare(
                self.dining_table.standard_price, 2556.25, precision_digits=2
            ),
            0,
            "selecting the kit too does not change the rolled-up cost",
        )
