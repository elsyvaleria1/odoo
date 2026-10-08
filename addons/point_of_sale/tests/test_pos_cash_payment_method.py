import odoo
from odoo.exceptions import UserError

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@odoo.tests.tagged("post_install", "-at_install")
class TestPosCashPaymentMethod(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.product = cls.create_product("Cash Probe", cls.categ_basic, 10.0, 5)

    def _sync_with_change(self, change):
        order_data = self.create_ui_order_data(
            [(self.product, 1)],
            pos_order_ui_args={"amount_return": change},
            payments=[(self.cash_pm1, 10.0 - change)],
        )
        return self.env["pos.order"].sync_from_ui([order_data])

    def test_the_session_and_its_config_name_one_cash_method(self):
        self._start_pos_session(self.cash_pm1, 0)
        self.assertEqual(self.config._get_cash_payment_method(), self.cash_pm1)
        self.assertTrue(self.config.cash_control)
        self.assertEqual(self.pos_session.cash_journal_id, self.cash_pm1.journal_id)

    def test_change_is_given_back_on_the_cash_method(self):
        self._start_pos_session(self.cash_pm1, 0)
        result = self._sync_with_change(-5.0)
        order = self.env["pos.order"].browse(result["pos.order"][0]["id"])
        change = order.payment_ids.filtered("is_change")
        self.assertEqual(change.payment_method_id, self.cash_pm1)
        self.assertEqual(order.amount_paid, 10.0)

    def test_change_without_a_cash_method_is_refused(self):
        non_cash = self.config.payment_method_ids.filtered(
            lambda method: not method.is_cash_count
        )
        self.config.payment_method_ids = non_cash
        self.assertFalse(self.config.cash_control)
        self._start_pos_session(non_cash, 0)
        order_data = self.create_ui_order_data(
            [(self.product, 1)],
            pos_order_ui_args={"amount_return": -5.0},
            payments=[(non_cash[:1], 15.0)],
        )
        with self.assertRaisesRegex(UserError, "No cash statement found"):
            self.env["pos.order"].sync_from_ui([order_data])
