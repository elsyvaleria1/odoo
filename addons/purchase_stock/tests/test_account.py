from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, new_test_user

from .common import PurchaseTestCommon


class TestPurchaseOrderInvoice(PurchaseTestCommon):
    def test_invoice_standard(self):
        po = self._create_purchase(self.product_standard, price_unit=12)
        self._receive(po)
        bill = self._create_bill(purchase_order=po)

        self.assertTrue(bill)
        self.assertEqual(po.line_ids.qty_invoiced, 1)
        self.assertRecordValues(
            bill.line_ids,
            [
                {"account_id": self.account_expense.id, "debit": 12.0, "credit": 0.0},
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 12.0},
            ],
        )
        closing = self._close()
        self.assertRecordValues(
            closing.line_ids,
            [
                {
                    "account_id": self.account_stock_variation.id,
                    "debit": 0.0,
                    "credit": 10.0,
                },
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 10.0,
                    "credit": 0.0,
                },
            ],
        )

    def test_invoice_standard_auto(self):
        po = self._create_purchase(self.product_standard_auto, price_unit=12)
        self._receive(po)
        bill = self._create_bill(purchase_order=po)

        self.assertTrue(bill)
        self.assertRecordValues(
            bill.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 12.0,
                    "credit": 0.0,
                },
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 12.0},
            ],
        )
        closing = self._close()
        self.assertRecordValues(
            closing.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 0.0,
                    "credit": 2.0,
                },
                {
                    "account_id": self.account_stock_variation.id,
                    "debit": 2.0,
                    "credit": 0.0,
                },
            ],
        )

    def test_invoice_standard_auto_with_pdiff(self):
        self._use_price_diff()
        po = self._create_purchase(self.product_standard_auto, price_unit=12)
        self._receive(po)
        bill = self._create_bill(purchase_order=po)

        self.assertTrue(bill)
        self.assertRecordValues(
            bill.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 12.0,
                    "credit": 0.0,
                },
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 12.0},
                {"account_id": self.account_price_diff.id, "debit": 2.0, "credit": 0.0},
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 0.0,
                    "credit": 2.0,
                },
            ],
        )
        with self.assertRaises(UserError):
            self._close()

    def test_invoice_standard_auto_with_pdiff_and_multi_currencies(self):
        self._use_price_diff()

        today = fields.Date.today()
        tomorrow = today + relativedelta(days=1)
        self._use_multi_currencies(
            [
                (fields.Date.to_string(today), 2.0),
                (fields.Date.to_string(tomorrow), 4.0),
            ]
        )

        po = self._create_purchase(
            self.product_standard_auto,
            quantity=10,
            price_unit=12,
            currency_id=self.other_currency.id,
        )
        self._receive(po)
        with freeze_time(tomorrow):
            bill = self._create_bill(purchase_order=po)

        self.assertRecordValues(
            bill.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 30.0,
                    "credit": 0.0,
                },
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 30.0},
                {
                    "account_id": self.account_price_diff.id,
                    "debit": 0.0,
                    "credit": 70.0,
                },
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 70.0,
                    "credit": 0.0,
                },
            ],
        )

    def test_invoice_standard_auto_rounding_price_unit(self):
        self._use_price_diff()
        self.env.ref("product.decimal_price").digits = 6
        self.product_standard_auto.standard_price = 0.0005

        purchase_order = self._create_purchase(
            self.product_standard_auto, quantity=100000, receive=True
        )
        bill = self._create_bill(purchase_order=purchase_order, post=False)

        bill_form = Form(bill)
        with bill_form.invoice_line_ids.edit(0) as line_form:
            line_form.price_unit = 0.0006
        bill_form.save()
        bill.action_post()
        self.assertEqual(purchase_order.picking_ids.move_ids.value, 60)
        self.assertRecordValues(
            bill.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 60.0,
                    "credit": 0.0,
                },
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 60.0},
                {
                    "account_id": self.account_price_diff.id,
                    "debit": 10.0,
                    "credit": 0.0,
                },
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 0.0,
                    "credit": 10.0,
                },
            ],
        )

    def test_invoice_standard_auto_with_discount(self):
        self._use_price_diff()
        self.product_standard_auto.standard_price = 100
        self.env.ref("product.decimal_discount").digits = 5

        purchase_order = self._create_purchase(
            self.product_standard_auto, price_unit=100, quantity=10000, receive=True
        )
        bill = self._create_bill(purchase_order=purchase_order, post=False)

        bill_form = Form(bill)
        with bill_form.invoice_line_ids.edit(0) as bill_line_form:
            bill_line_form.discount = 0.92431
        bill_form.save()
        bill.action_post()
        self.assertEqual(purchase_order.picking_ids.move_ids.value, 990756.9)
        self.assertRecordValues(
            bill.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 990756.9,
                    "credit": 0.0,
                },
                {
                    "account_id": self.account_payable.id,
                    "debit": 0.0,
                    "credit": 990756.9,
                },
                {
                    "account_id": self.account_price_diff.id,
                    "debit": 0.0,
                    "credit": 9243.1,
                },
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 9243.1,
                    "credit": 0.0,
                },
            ],
        )

    def test_invoice_avco(self):
        po = self._create_purchase(self.product_avco, price_unit=12)
        po_line = po.line_ids
        self._receive(po)
        bill = self._create_bill(purchase_order=po)

        self.assertTrue(bill)
        self.assertEqual(po_line.qty_invoiced, 1)
        self.assertRecordValues(
            bill.line_ids,
            [
                {"account_id": self.account_expense.id, "debit": 12.0, "credit": 0.0},
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 12.0},
            ],
        )
        closing = self._close()
        self.assertRecordValues(
            closing.line_ids,
            [
                {
                    "account_id": self.account_stock_variation.id,
                    "debit": 0.0,
                    "credit": 12.0,
                },
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 12.0,
                    "credit": 0.0,
                },
            ],
        )

    def test_invoice_avco_auto(self):
        po = self._create_purchase(self.product_avco_auto, price_unit=12)
        self._receive(po)
        bill = self._create_bill(purchase_order=po)

        self.assertTrue(bill)
        self.assertRecordValues(
            bill.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 12.0,
                    "credit": 0.0,
                },
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 12.0},
            ],
        )
        with self.assertRaises(UserError):
            self._close()

    def test_invoice_avco_tax_without_account(self):
        tax_with_no_account = self.env["account.tax"].create(
            {
                "name": "Tax with no account",
                "amount_type": "fixed",
                "amount": 5,
                "sequence": 8,
            }
        )
        po = self._create_purchase(
            self.product_avco_auto,
            10,
            10,
            tax_ids=[Command.set(tax_with_no_account.ids)],
        )
        move = self._receive(po)
        self.assertEqual(move.value, 150)

        bill = self._create_bill(purchase_order=po)
        self.assertRecordValues(
            bill.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 100.0,
                    "credit": 0.0,
                },
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 50.0,
                    "credit": 0.0,
                },
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 150.0},
            ],
        )

    def test_invoice_fifo(self):
        po = self._create_purchase(self.product_fifo, price_unit=12)
        self._receive(po)
        bill = self._create_bill(purchase_order=po)

        self.assertTrue(bill)
        self.assertRecordValues(
            bill.line_ids,
            [
                {"account_id": self.account_expense.id, "debit": 12.0, "credit": 0.0},
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 12.0},
            ],
        )
        closing = self._close()
        self.assertRecordValues(
            closing.line_ids,
            [
                {
                    "account_id": self.account_stock_variation.id,
                    "debit": 0.0,
                    "credit": 12.0,
                },
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 12.0,
                    "credit": 0.0,
                },
            ],
        )

    def test_invoice_fifo_auto(self):
        po = self._create_purchase(self.product_fifo_auto, price_unit=12)
        self._receive(po)
        bill = self._create_bill(purchase_order=po)

        self.assertTrue(bill)
        self.assertRecordValues(
            bill.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 12.0,
                    "credit": 0.0,
                },
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 12.0},
            ],
        )

        with self.assertRaises(UserError):
            self._close()

    def test_invoice_refund(self):
        po = self._create_purchase(self.product_avco, price_unit=12)
        po_line = po.line_ids
        self._receive(po)
        bill = self._create_bill(purchase_order=po)

        self.assertTrue(bill)
        self.assertEqual(po_line.qty_invoiced, 1)
        self.assertRecordValues(
            bill.line_ids,
            [
                {"account_id": self.account_expense.id, "debit": 12.0, "credit": 0.0},
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 12.0},
            ],
        )
        closing = self._close()
        self.assertRecordValues(
            closing.line_ids,
            [
                {
                    "account_id": self.account_stock_variation.id,
                    "debit": 0.0,
                    "credit": 12.0,
                },
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 12.0,
                    "credit": 0.0,
                },
            ],
        )
        refund = self._refund(bill)
        self.assertTrue(refund)
        self.assertRecordValues(
            refund.line_ids,
            [
                {"account_id": self.account_expense.id, "debit": 0.0, "credit": 12.0},
                {"account_id": self.account_payable.id, "debit": 12.0, "credit": 0.0},
            ],
        )
        self.assertEqual(po_line.qty_invoiced, 0)
        self.assertEqual(self.product_avco.standard_price, 12.0)
        with self.assertRaises(UserError):
            self._close()
        bill = self._create_bill(purchase_order=po, post=False)
        bill.invoice_line_ids.price_unit = 18
        bill.action_post()
        self.assertEqual(po_line.qty_invoiced, 1)
        closing = self._close()
        self.assertRecordValues(
            closing.line_ids,
            [
                {
                    "account_id": self.account_stock_variation.id,
                    "debit": 0.0,
                    "credit": 6.0,
                },
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 6.0,
                    "credit": 0.0,
                },
            ],
        )

    def test_invoice_refund_auto(self):
        po = self._create_purchase(self.product_fifo_auto, price_unit=12)
        po_line = po.line_ids
        self._receive(po)
        bill = self._create_bill(purchase_order=po)

        self.assertTrue(bill)
        self.assertRecordValues(
            bill.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 12.0,
                    "credit": 0.0,
                },
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 12.0},
            ],
        )

        with self.assertRaises(UserError):
            self._close()
        refund = self._refund(bill)
        self.assertTrue(refund)
        self.assertRecordValues(
            refund.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 0.0,
                    "credit": 12.0,
                },
                {"account_id": self.account_payable.id, "debit": 12.0, "credit": 0.0},
            ],
        )
        self.assertEqual(po_line.qty_invoiced, 0)
        self.assertEqual(self.product_fifo_auto.standard_price, 12.0)

        closing_before_bill = self._close()
        self.assertTrue(closing_before_bill)
        self.assertRecordValues(
            closing_before_bill.line_ids,
            [
                {
                    "account_id": self.account_stock_variation.id,
                    "debit": 0.0,
                    "credit": 12.0,
                },
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 12.0,
                    "credit": 0.0,
                },
            ],
        )

        bill = self._create_bill(purchase_order=po, post=False)
        bill.invoice_line_ids.price_unit = 18
        bill.action_post()
        self.assertRecordValues(
            bill.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 18.0,
                    "credit": 0.0,
                },
                {"account_id": self.account_payable.id, "debit": 0.0, "credit": 18.0},
            ],
        )
        self.assertEqual(po_line.qty_invoiced, 1)
        self.assertEqual(self.product_fifo_auto.standard_price, 18.0)

        closing_after_bill = self._close()
        self.assertTrue(closing_after_bill)
        self.assertRecordValues(
            closing_after_bill.line_ids,
            [
                {
                    "account_id": self.account_stock_valuation.id,
                    "debit": 0.0,
                    "credit": 12.0,
                },
                {
                    "account_id": self.account_stock_variation.id,
                    "debit": 12.0,
                    "credit": 0.0,
                },
            ],
        )

    def _clerk_without_purchases(self, name, rows, verbs=None):
        privilege = self.env["res.groups"].create(
            {"name": f"Probe: {name}", "is_privilege": True}
        )
        self.env["ir.model.data"].create(
            {
                "module": "purchase_stock",
                "name": name,
                "model": "res.groups",
                "res_id": privilege.id,
            }
        )
        Line = self.env["account.move.line"]
        order_links = {
            (Line._fields[field_name].comodel_name, "r")
            for field_name in Line._get_fields_order_line_link()
            if field_name != "purchase_line_ids"
        }
        self.env["ir.access"].create(
            [
                {
                    "name": f"Probe: {name} on {model}",
                    "model_id": self.env["ir.model"]._get_id(model),
                    "group_id": privilege.id,
                    "kind": "permission",
                    "operation": operation,
                }
                for model, operation in {*rows, *order_links}
            ]
        )
        if verbs:
            self.env["ir.access"].create(
                {
                    "name": f"Probe: {name} verbs",
                    "model_id": self.env["ir.model"]._get_id("account.move"),
                    "group_id": privilege.id,
                    "kind": "permission",
                    "verbs": verbs,
                }
            )
        clerk = new_test_user(
            self.env,
            login=name,
            groups="base.group_user",
            company_id=self.company.id,
            company_ids=[Command.set(self.company.ids)],
        )
        self.assertFalse(
            self.env["purchase.order.line"].with_user(clerk).has_access("read")
        )
        return clerk, f"purchase_stock.{name}"

    def test_a_customer_invoice_reads_no_purchase_line(self):
        invoice = self._create_invoice(self.product_standard, price_unit=10, post=False)
        clerk, privilege = self._clerk_without_purchases(
            "probe_read_invoice_lines",
            {("account.move", "r"), ("account.move.line", "r")},
        )
        invoice = invoice.with_user(clerk).with_privilege(privilege)

        self.assertFalse(invoice.invoice_line_ids._get_stock_moves())
        self.assertFalse(any(invoice._get_linked_order_lines()))

    def test_an_entry_is_posted_by_a_clerk_who_reads_no_purchase(self):
        journal = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.company.id)], limit=1
        )
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "line_ids": [
                    Command.create(
                        {"account_id": self.account_stock_valuation.id, "debit": 10.0}
                    ),
                    Command.create(
                        {"account_id": self.account_stock_variation.id, "credit": 10.0}
                    ),
                ],
            }
        )
        clerk, privilege = self._clerk_without_purchases(
            "probe_post_entry",
            {
                ("account.move", "ru"),
                ("account.move.line", "ru"),
                ("account.journal", "r"),
                ("account.partial.reconcile", "r"),
            },
            verbs="post",
        )
        self.env.invalidate_all()

        entry.with_user(clerk).with_privilege(privilege).action_post()

        self.assertEqual(entry.state, "posted")

    def test_a_copied_bill_line_keeps_its_purchase_line_whoever_copies_it(self):
        po = self._create_purchase(self.product_standard, price_unit=12)
        self._receive(po)
        bill = self._create_bill(purchase_order=po, post=False)
        clerk, privilege = self._clerk_without_purchases(
            "probe_copy_bill_lines",
            {("account.move", "r"), ("account.move.line", "r")},
        )

        values = (
            bill.invoice_line_ids.with_user(clerk)
            .with_privilege(privilege)
            .with_context(include_business_fields=True)
            .copy_data()
        )

        self.assertEqual(values[0]["purchase_line_ids"], [Command.set(po.line_ids.ids)])

    def test_a_bill_line_reaches_the_receipt_of_its_purchase_line(self):
        po = self._create_purchase(self.product_standard, price_unit=12)
        receipt_moves = self._receive(po)
        bill = self._create_bill(purchase_order=po, post=False)

        self.assertEqual(bill.invoice_line_ids._get_stock_moves(), receipt_moves)
        self.assertIn(po.line_ids, bill._get_linked_order_lines())
