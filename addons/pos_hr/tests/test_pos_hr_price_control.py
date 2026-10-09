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
        cls.basic, cls.advanced, cls.minimal = cls.env["hr.employee"].create(
            [
                {"name": "Basic Cashier"},
                {"name": "Advanced Cashier"},
                {"name": "Minimal Cashier"},
            ]
        )
        cls.config.write(
            {
                "module_pos_hr": True,
                "restrict_price_control": True,
                "basic_employee_ids": [Command.set(cls.basic.ids)],
                "advanced_employee_ids": [Command.set(cls.advanced.ids)],
                "minimal_employee_ids": [Command.set(cls.minimal.ids)],
            }
        )

    def _sync(self, employee, **line):
        data = self.create_ui_order_data(
            [{"product": self.product, "quantity": 1, **line}],
            pos_order_ui_args={"employee_id": employee.id},
            payments=[(self.cash_pm1, 80)],
        )
        result = self.env["pos.order"].sync_from_ui([data])
        return self.env["pos.order"].browse(result["pos.order"][0]["id"])

    def test_the_employee_who_cashed_in_decides_price_control(self):
        self._start_pos_session(self.cash_pm1, 0)
        for employee, flagged in ((self.basic, True), (self.advanced, False)):
            with self.subTest(employee=employee.name):
                order = self._sync(employee, price_unit=80)

                self.assertEqual(order.state, "paid")
                self.assertEqual(order.has_pricing_breach, flagged)

    def test_a_minimal_employee_sets_neither_price_nor_discount(self):
        self.config.write({"restrict_price_control": False, "manual_discount": True})
        self._start_pos_session(self.cash_pm1, 0)
        for employee, line, flagged in (
            (self.minimal, {"price_unit": 80}, True),
            (self.minimal, {"discount": 20}, True),
            (self.basic, {"price_unit": 80}, False),
            (self.basic, {"discount": 20}, False),
        ):
            with self.subTest(employee=employee.name, line=line):
                order = self._sync(employee, **line)

                self.assertEqual(order.state, "paid")
                self.assertEqual(order.has_pricing_breach, flagged)
