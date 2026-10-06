from datetime import timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.account_collection.tests.common import CollectionCommon


@tagged("post_install", "-at_install")
class TestCreditHold(CollectionCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.company_data["company"].account_config_id
        cls.config.collection_custody_days_cash = 1
        cls.credit_term = cls.env.ref("payment_term.account_payment_term_30days")
        cls.cash_term = cls.env.ref("payment_term.account_payment_term_immediate")
        cls.sales_manager = new_test_user(
            cls.env,
            login="collection_sales_manager",
            groups="base.group_user,sale.group_sale_manager",
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Fertilizer", "list_price": 100.0}
        )

    def _order(self, term):
        return (
            self.env["sale.order"]
            .with_user(self.sales_manager)
            .create(
                {
                    "partner_id": self.partner_a.id,
                    "user_id": self.collector.id,
                    "payment_term_id": term.id,
                    "line_ids": [
                        Command.create(
                            {"product_id": self.product.id, "product_qty": 1}
                        )
                    ],
                }
            )
        )

    def _hold_overdue_custody(self):
        self._collect(
            self._post_invoice(100.0), 100.0, date=self.today - timedelta(days=10)
        )

    def test_an_overdue_collector_credit_sale_is_held(self):
        self.config.collection_hold_credit_sales = True
        self._hold_overdue_custody()
        with self.assertRaises(UserError):
            self._order(self.credit_term).action_confirm()

    def test_a_cash_sale_is_never_held(self):
        self.config.collection_hold_credit_sales = True
        self._hold_overdue_custody()
        order = self._order(self.cash_term)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_nothing_is_held_with_the_switch_off(self):
        self._hold_overdue_custody()
        order = self._order(self.credit_term)
        order.action_confirm()
        self.assertEqual(order.state, "done")
