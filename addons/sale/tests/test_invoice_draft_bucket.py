from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.sale.tests.common import TestSaleCommon


@tagged("-at_install", "post_install")
class TestInvoiceDraftBucket(TestSaleCommon):
    """What an order line can be invoiced for stands in one of three places:
    on a posted invoice, on a draft invoice, or on none.

    The fork read a draft both ways before. Counted as invoiced, the order
    said "Fully invoiced" while nothing was posted; left uncounted, the same
    line could be invoiced twice. A draft now claims its share without
    invoicing it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.order = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner_a.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": cls.company_data["product_order_no"].id,
                            "product_qty": 5.0,
                            "price_unit": 100.0,
                            "tax_ids": False,
                        }
                    ),
                ],
            }
        )
        cls.line = cls.order.line_ids
        cls.order.action_confirm()

    def _assert_buckets(self, invoiced, draft, to_invoice):
        self.assertRecordValues(
            self.line,
            [
                {
                    "qty_invoiced": invoiced,
                    "qty_invoiced_draft": draft,
                    "qty_to_invoice": to_invoice,
                    "amount_taxexc_invoiced": invoiced * 100.0,
                    "amount_taxexc_invoiced_draft": draft * 100.0,
                    "amount_taxexc_to_invoice": to_invoice * 100.0,
                    "amount_taxinc_invoiced": invoiced * 100.0,
                    "amount_taxinc_invoiced_draft": draft * 100.0,
                    "amount_taxinc_to_invoice": to_invoice * 100.0,
                }
            ],
        )

    def test_a_confirmed_order_is_wholly_to_invoice(self):
        self._assert_buckets(invoiced=0.0, draft=0.0, to_invoice=5.0)
        self.assertEqual(self.line.invoice_state, "to do")
        self.assertEqual(self.order.invoice_state, "to do")

    def test_a_draft_invoice_claims_the_line_without_invoicing_it(self):
        self.order._create_invoices()

        self._assert_buckets(invoiced=0.0, draft=5.0, to_invoice=0.0)
        self.assertEqual(self.line.invoice_state, "draft")
        self.assertEqual(self.order.invoice_state, "draft")
        self.assertRecordValues(
            self.order,
            [
                {
                    "amount_taxexc_invoiced": 0.0,
                    "amount_taxexc_invoiced_draft": 500.0,
                    "amount_taxexc_to_invoice": 0.0,
                }
            ],
        )

    def test_posting_the_draft_is_what_invoices_the_line(self):
        invoice = self.order._create_invoices()

        invoice.action_post()

        self._assert_buckets(invoiced=5.0, draft=0.0, to_invoice=0.0)
        self.assertEqual(self.line.invoice_state, "done")
        self.assertEqual(self.order.invoice_state, "done")

    def test_a_line_on_a_draft_invoice_cannot_be_invoiced_again(self):
        self.order._create_invoices()

        with self.assertRaises(UserError):
            self.order._create_invoices()

    def test_a_draft_for_part_of_the_line_leaves_the_rest_to_invoice(self):
        invoice = self.order._create_invoices()

        invoice.invoice_line_ids.quantity = 2.0

        self._assert_buckets(invoiced=0.0, draft=2.0, to_invoice=3.0)
        self.assertEqual(self.line.invoice_state, "to do")
        self.assertEqual(self.order.invoice_state, "to do")

        invoice.action_post()

        self._assert_buckets(invoiced=2.0, draft=0.0, to_invoice=3.0)
        self.assertEqual(self.line.invoice_state, "partial")
        self.assertEqual(self.order.invoice_state, "partial")

    def test_a_posted_part_and_a_draft_for_the_rest_read_draft(self):
        first = self.order._create_invoices()
        first.invoice_line_ids.quantity = 2.0
        first.action_post()

        self.order._create_invoices()

        self._assert_buckets(invoiced=2.0, draft=3.0, to_invoice=0.0)
        self.assertEqual(self.line.invoice_state, "draft")
        self.assertEqual(self.order.invoice_state, "draft")

    def test_cancelling_the_draft_frees_what_it_claimed(self):
        invoice = self.order._create_invoices()

        invoice.action_cancel()

        self._assert_buckets(invoiced=0.0, draft=0.0, to_invoice=5.0)
        self.assertEqual(self.order.invoice_state, "to do")

    def test_resetting_a_posted_invoice_to_draft_takes_the_line_back(self):
        invoice = self.order._create_invoices()
        invoice.action_post()

        invoice.action_draft()

        self._assert_buckets(invoiced=0.0, draft=5.0, to_invoice=0.0)
        self.assertEqual(self.order.invoice_state, "draft")

    def test_the_price_is_locked_while_the_invoice_is_a_draft(self):
        self.order._create_invoices()

        with self.assertRaises(UserError):
            self.line.set_manual_price(90.0)

    def test_a_draft_invoice_does_not_move_the_credit_still_to_invoice(self):
        self.env.company.account_use_credit_limit = True
        partner = self.partner_a.commercial_partner_id
        partner.invalidate_recordset(["credit_to_invoice"])
        before = partner.credit_to_invoice

        invoice = self.order._create_invoices()
        partner.invalidate_recordset(["credit_to_invoice"])
        self.assertAlmostEqual(partner.credit_to_invoice, before, places=2)

        invoice.action_post()
        partner.invalidate_recordset(["credit_to_invoice"])
        self.assertAlmostEqual(partner.credit_to_invoice, before - 500.0, places=2)

    def test_the_draft_state_can_be_searched(self):
        self.order._create_invoices()

        self.assertIn(
            self.order,
            self.env["sale.order"].search([("invoice_state", "=", "draft")]),
        )
        self.assertNotIn(
            self.order,
            self.env["sale.order"].search(
                [("invoice_state", "in", ("to do", "partial", "done"))]
            ),
        )
