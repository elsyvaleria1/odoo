from odoo import Command
from odoo.tests import tagged

from odoo.addons.account_collection_telegram.tests.test_collection_flow import (
    TestCollectionFlow,
)


@tagged("post_install", "-at_install")
class TestCashSaleFlow(TestCollectionFlow):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.collector.group_ids = [
            Command.link(cls.env.ref("sale.group_sale_salesman").id)
        ]
        product = cls.env["product.product"].create(
            {
                "name": "Seed",
                "list_price": 750.0,
                "invoice_policy": "ordered",
                "taxes_id": False,
            }
        )
        cls.order = (
            cls.env["sale.order"]
            .with_user(cls.collector)
            .create(
                {
                    "partner_id": cls.customer.id,
                    "user_id": cls.collector.id,
                    "payment_term_id": cls.env.ref(
                        "payment_term.account_payment_term_immediate"
                    ).id,
                    "line_ids": [Command.create({"product_id": product.id})],
                }
            )
        )
        cls.order.action_confirm()

    def test_a_cash_sale_is_invoiced_and_collected_from_telegram(self):
        self._say("/cobro")
        reply = self._say("Sauce")
        self.assertIn("1,750.00", reply)

        self._press(f"cob:o:{self.order.id}")
        self._press("cob:a")
        self._press("cob:m:cash")
        self._press("cob:d:0")
        self._press("cob:x")
        self.assertIn("take the goods now", self._say("Skip"))
        self._press("cob:h:0")
        reply = self._press("cob:ok")

        invoice = self.order.invoice_ids
        self.assertEqual(invoice.state, "posted", reply)
        self.assertEqual(invoice.amount_residual, 0.0)
        payment = self._payments()
        self.assertEqual(payment.amount, 750.0)
        self.assertTrue(payment.is_in_custody)
        self.assertEqual(self.order.invoice_state, "done")
        self.assertNotEqual(self.order.picking_ids.state, "done")

    def test_the_customer_takes_the_goods_from_a_telegram_cash_sale(self):
        self._say("/cobro")
        self._say("Sauce")
        self._press(f"cob:o:{self.order.id}")
        self._press("cob:a")
        self._press("cob:m:cash")
        self._press("cob:d:0")
        self._press("cob:x")
        self._say("Skip")
        self.assertIn("takes the goods now", self._press("cob:h:1"))
        self._press("cob:ok")

        delivery = self.order.picking_ids
        self.assertEqual(delivery.state, "done")
        self.assertTrue(delivery.is_handed_over_at_sale)
