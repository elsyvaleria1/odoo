from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, new_test_user, tagged

from odoo.addons.account.tests.common_posting_obligation import (
    exemption_notes,
    holding_invoice_posting,
)
from odoo.addons.account_collection.tests.common import CollectionCommon


@tagged("post_install", "-at_install")
class TestCashSale(CollectionCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.seller = new_test_user(
            cls.env,
            login="cash_sale_seller",
            groups="base.group_user,sale.group_sale_salesman,"
            "account_collection.group_collection_collector",
            company_id=cls.company_data["company"].id,
            company_ids=[Command.set(cls.company_data["company"].ids)],
        )
        cls.cash_term = cls.env.ref("payment_term.account_payment_term_immediate")
        cls.credit_term = cls.env.ref("payment_term.account_payment_term_30days")
        cls.product = cls.env["product.product"].create(
            {
                "name": "Fertilizer",
                "list_price": 500.0,
                "invoice_policy": "ordered",
                "taxes_id": False,
            }
        )

    def _order(self, term, confirm=True):
        order = (
            self.env["sale.order"]
            .with_user(self.seller)
            .create(
                {
                    "partner_id": self.partner_a.id,
                    "user_id": self.seller.id,
                    "payment_term_id": term.id,
                    "line_ids": [
                        Command.create(
                            {"product_id": self.product.id, "product_qty": 2}
                        )
                    ],
                }
            )
        )
        if confirm:
            order.action_confirm()
        return order

    def _collect(self, order, **vals):
        action = order.action_open_cash_collect()
        wizard = Form(
            self.env[action["res_model"]]
            .with_user(self.seller)
            .with_context(**action["context"])
        )
        for name, value in vals.items():
            setattr(wizard, name, value)
        return wizard.save().action_collect()

    def test_a_cash_sale_is_invoiced_issued_and_held_in_custody(self):
        order = self._order(self.cash_term)

        action = self._collect(order)

        payment = self.env["account.payment"].browse(action["res_id"])
        invoice = order.invoice_ids
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.invoice_date, self.today)
        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertEqual(payment.amount, 1000.0)
        self.assertEqual(payment.collector_id, self.seller)
        self.assertTrue(payment.is_in_custody)
        self.assertEqual(order.invoice_state, "done")

    def test_a_cash_sale_invoice_does_not_wait_for_approval(self):
        order = self._order(self.cash_term)

        with holding_invoice_posting(self.env):
            self._collect(order)

        self.assertEqual(order.invoice_ids.state, "posted")
        self.assertEqual(
            len(exemption_notes(order.invoice_ids.sudo(), "payment_received")), 1
        )

    def test_a_credit_sale_is_collected_on_its_invoices(self):
        order = self._order(self.credit_term)
        with self.assertRaises(UserError):
            order.action_open_cash_collect()

    def test_a_quotation_is_confirmed_first(self):
        order = self._order(self.cash_term, confirm=False)
        with self.assertRaises(UserError):
            order.action_open_cash_collect()

    def test_a_cash_sale_is_collected_once(self):
        order = self._order(self.cash_term)
        self._collect(order)
        with self.assertRaises(UserError):
            order.action_open_cash_collect()

    def _storable_order(self, stock):
        product = self.env["product.product"].create(
            {
                "name": "Seed",
                "list_price": 100.0,
                "invoice_policy": "ordered",
                "is_storable": True,
                "taxes_id": False,
            }
        )
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        if stock:
            self.env["stock.quant"]._update_available_quantity(
                product, warehouse.lot_stock_id, stock
            )
        order = (
            self.env["sale.order"]
            .with_user(self.seller)
            .create(
                {
                    "partner_id": self.partner_a.id,
                    "user_id": self.seller.id,
                    "payment_term_id": self.cash_term.id,
                    "warehouse_id": warehouse.id,
                    "line_ids": [
                        Command.create({"product_id": product.id, "product_qty": 3})
                    ],
                }
            )
        )
        order.action_confirm()
        return order

    def test_the_customer_takes_the_goods_of_a_cash_sale_now(self):
        order = self._storable_order(stock=10)

        self._collect(order, hand_over=True)

        picking = order.picking_ids
        self.assertEqual(picking.state, "done")
        self.assertTrue(picking.is_handed_over_at_sale)
        self.assertEqual(picking.move_ids.quantity, 3)

    def test_goods_not_at_hand_are_not_handed_over(self):
        order = self._storable_order(stock=1)

        with self.assertRaisesRegex(UserError, "not all at hand"):
            self._collect(order, hand_over=True)

        self.assertFalse(order.invoice_ids)
        self.assertNotEqual(order.picking_ids.state, "done")

    def test_a_cash_sale_without_hand_over_keeps_its_delivery(self):
        order = self._storable_order(stock=10)

        self._collect(order)

        self.assertEqual(order.picking_ids.state, "assigned")
