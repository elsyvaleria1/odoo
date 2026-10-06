from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.purchase.tests.test_purchase_invoice import (
    TestPurchaseToInvoiceCommon,
)


@tagged("-at_install", "post_install")
class TestBillDraftBucket(TestPurchaseToInvoiceCommon):
    """What an order line can be billed for stands in one of three places:
    on a posted bill, on a draft bill, or on none. A draft claims its share
    without billing it, so the order does not read "Fully invoiced" on a bill
    nobody posted, and the line cannot be billed twice either."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.order = cls.env["purchase.order"].create(
            {
                "partner_id": cls.partner_a.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": cls.product_order.name,
                            "product_id": cls.product_order.id,
                            "product_qty": 5.0,
                            "product_uom_id": cls.product_order.uom_id.id,
                            "price_unit": 100.0,
                            "tax_ids": False,
                        }
                    ),
                ],
            }
        )
        cls.line = cls.order.line_ids
        cls.order.action_confirm()

    def _bill(self):
        bill = self.order.create_invoice()
        bill.invoice_date = fields.Date.today()
        return bill

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

    def test_a_confirmed_order_is_wholly_to_bill(self):
        self._assert_buckets(invoiced=0.0, draft=0.0, to_invoice=5.0)
        self.assertEqual(self.order.invoice_state, "to do")

    def test_a_draft_bill_claims_the_line_without_billing_it(self):
        self._bill()

        self._assert_buckets(invoiced=0.0, draft=5.0, to_invoice=0.0)
        self.assertEqual(self.line.invoice_state, "draft")
        self.assertEqual(self.order.invoice_state, "draft")

    def test_posting_the_draft_is_what_bills_the_line(self):
        bill = self._bill()

        bill.action_post()

        self._assert_buckets(invoiced=5.0, draft=0.0, to_invoice=0.0)
        self.assertEqual(self.line.invoice_state, "done")
        self.assertEqual(self.order.invoice_state, "done")

    def test_a_second_bill_carries_nothing_of_a_line_a_draft_claims(self):
        # a purchase order always yields a bill to fill in by hand; what the
        # draft claims is what keeps the second one empty
        self._bill()

        second = self.order.create_invoice()

        self.assertEqual(second.invoice_line_ids.quantity, 0.0)
        self._assert_buckets(invoiced=0.0, draft=5.0, to_invoice=0.0)

    def test_a_draft_for_part_of_the_line_leaves_the_rest_to_bill(self):
        bill = self._bill()

        bill.invoice_line_ids.quantity = 2.0

        self._assert_buckets(invoiced=0.0, draft=2.0, to_invoice=3.0)
        self.assertEqual(self.order.invoice_state, "to do")

        bill.action_post()

        self._assert_buckets(invoiced=2.0, draft=0.0, to_invoice=3.0)
        self.assertEqual(self.order.invoice_state, "partial")

    def test_cancelling_the_draft_frees_what_it_claimed(self):
        bill = self._bill()

        bill.action_cancel()

        self._assert_buckets(invoiced=0.0, draft=0.0, to_invoice=5.0)
        self.assertEqual(self.order.invoice_state, "to do")

    def test_the_analysis_report_shows_the_draft_share(self):
        self._bill()
        self.env.flush_all()

        report = self.env["purchase.report"].search(
            [("order_reference", "=", f"purchase.order,{self.order.id}")]
        )

        self.assertEqual(sum(report.mapped("qty_invoiced")), 0.0)
        self.assertEqual(sum(report.mapped("qty_invoiced_draft")), 5.0)
        self.assertEqual(sum(report.mapped("qty_to_invoice")), 0.0)
