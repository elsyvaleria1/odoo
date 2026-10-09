from odoo import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestPosHrPriceControl(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.env.user.group_ids |= cls.env.ref("hr.group_hr_user")
        cls.product = cls.create_product("Controlled Price", cls.categ_basic, 100)
        cls.basic, cls.advanced = cls.env["hr.employee"].create(
            [{"name": "Basic Cashier"}, {"name": "Advanced Cashier"}]
        )
        cls.config.write(
            {
                "module_pos_hr": True,
                "restrict_price_control": True,
                "basic_employee_ids": [Command.set(cls.basic.ids)],
                "advanced_employee_ids": [Command.set(cls.advanced.ids)],
            }
        )

    def test_the_employee_who_cashed_in_decides_price_control(self):
        self._start_pos_session(self.cash_pm1, 0)
        for employee, flagged in ((self.basic, True), (self.advanced, False)):
            with self.subTest(employee=employee.name):
                data = self.create_ui_order_data(
                    [{"product": self.product, "quantity": 1, "price_unit": 80}],
                    pos_order_ui_args={"employee_id": employee.id},
                    payments=[(self.cash_pm1, 80)],
                )
                result = self.env["pos.order"].sync_from_ui([data])
                order = self.env["pos.order"].browse(result["pos.order"][0]["id"])

                self.assertEqual(order.state, "paid")
                self.assertEqual(order.has_pricing_breach, flagged)
