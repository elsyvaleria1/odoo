from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, tagged
from odoo.tools.safe_eval import safe_eval

from odoo.addons.sale_subscription.tests.common_sale_subscription import (
    TestSubscriptionCommon,
)


@tagged("post_install", "-at_install")
class TestSubscriptionInvoiceButtons(TestSubscriptionCommon):
    def _confirmed_order(self, product_key):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.company_data[product_key].id,
                            "product_qty": 2,
                            "tax_ids": False,
                        }
                    ),
                ],
            }
        )
        order.action_confirm()
        return order

    def _shown_invoice_buttons(self, order):
        form = Form(order)
        eval_context = form._prepare_eval_context()
        return sorted(
            button.get("id")
            for button in form._view["tree"].iter("button")
            if button.get("id")
            in ("create_invoice", "create_invoice_sub", "create_invoice_percentage")
            and not safe_eval(button.get("invisible") or "False", eval_context)
        )

    def _wizard(self, order, **values):
        return (
            self.env["wizard.sale.order.invoice"]
            .with_context(
                active_model="sale.order", active_ids=order.ids, active_id=order.id
            )
            .create(values)
        )

    def test_an_undelivered_order_offers_a_down_payment_not_a_regular_invoice(self):
        order = self._confirmed_order("product_delivery_no")

        shown = self._shown_invoice_buttons(order)

        self.assertEqual(order.invoice_state, "to do")
        self.assertEqual(shown, ["create_invoice_percentage"])
        with self.assertRaises(UserError):
            self._wizard(order, advance_payment_method="delivered").create_invoices()

    def test_a_partially_invoiced_order_with_a_new_delivery_offers_the_regular_invoice(
        self,
    ):
        order = self._confirmed_order("product_delivery_no")
        order.line_ids.qty_transferred = 1
        self._wizard(order, advance_payment_method="delivered").create_invoices()
        order.invoice_ids.action_post()

        order.line_ids.qty_transferred = 2

        self.assertEqual(order.invoice_state, "partial")
        self.assertEqual(self._shown_invoice_buttons(order), ["create_invoice"])

    def test_a_subscription_keeps_its_own_invoice_buttons(self):
        subscription = self.subscription
        subscription.action_confirm()

        self.assertEqual(self._shown_invoice_buttons(subscription), ["create_invoice"])

        subscription._create_recurring_invoice()

        self.assertGreater(subscription.next_invoice_date, fields.Date.today())
        self.assertEqual(
            self._shown_invoice_buttons(subscription), ["create_invoice_sub"]
        )

    def test_an_invoiced_period_with_a_one_time_line_offers_the_regular_invoice(self):
        subscription = self.subscription
        subscription.action_confirm()
        subscription._create_recurring_invoice()
        subscription.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.company_data["product_order_no"].id,
                            "product_qty": 1,
                            "tax_ids": False,
                        }
                    )
                ]
            }
        )

        self.assertGreater(subscription.next_invoice_date, fields.Date.today())
        self.assertEqual(subscription.invoice_state, "partial")
        self.assertTrue(subscription.is_invoiceable)
        self.assertEqual(self._shown_invoice_buttons(subscription), ["create_invoice"])

    def test_invoicing_a_subscription_in_advance_defaults_to_a_regular_invoice(self):
        subscription = self.subscription
        subscription.action_confirm()
        subscription._create_recurring_invoice()

        wizard = self._wizard(subscription)

        self.assertFalse(subscription.is_invoiceable)
        self.assertEqual(wizard.advance_payment_method, "delivered")

    def test_a_subscription_starting_later_offers_its_invoice_in_advance(self):
        start = fields.Date.today() + relativedelta(weeks=2)
        subscription = self.subscription
        subscription.write({"start_date": start, "next_invoice_date": start})
        subscription.action_confirm()

        self.assertEqual(set(subscription.line_ids.mapped("invoice_state")), {"no"})
        self.assertEqual(subscription.invoice_state, "to do")
        self.assertFalse(subscription.is_invoiceable)
        self.assertEqual(
            self._shown_invoice_buttons(subscription), ["create_invoice_sub"]
        )
        self._wizard(subscription).create_invoices()
        self.assertEqual(len(subscription.invoice_ids), 1)
