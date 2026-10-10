from odoo import Command
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestMarinUnsavedTaxTotals(AccountTestInvoicingCommon):
    def _move_with_manual_tax(self, move_type):
        tax = (
            self.company_data["default_tax_purchase"]
            if move_type == "in_invoice"
            else self.company_data["default_tax_sale"]
        )
        self.assertEqual(tax.amount, 15.0)
        move = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "taxed",
                            "quantity": 1,
                            "price_unit": 10.0,
                            "tax_ids": [Command.set(tax.ids)],
                        }
                    ),
                    Command.create(
                        {
                            "name": "untaxed",
                            "quantity": 1,
                            "price_unit": 5.0,
                            "tax_ids": [Command.clear()],
                        }
                    ),
                ],
            }
        )
        tax_line = self._tax_line(move)
        move.write(
            {
                "line_ids": [
                    Command.update(
                        tax_line.id,
                        {"amount_currency": 1.60 * move.direction_sign},
                    )
                ]
            }
        )
        self.assertAlmostEqual(move.tax_totals["tax_amount_currency"], 1.60)
        return move

    def _tax_line(self, move):
        return move.line_ids.filtered(lambda line: line.display_type == "tax")

    def _edit_line_in_form(self, move, name, price_unit):
        names = move.invoice_line_ids.mapped("name")
        with Form(move) as move_form:
            with move_form.invoice_line_ids.edit(names.index(name)) as line_form:
                line_form.price_unit = price_unit
            return move_form.tax_totals["tax_amount_currency"]

    def _assert_saved_tax(self, move, tax_amount, total):
        self.assertAlmostEqual(
            self._tax_line(move).amount_currency, tax_amount * move.direction_sign
        )
        self.assertAlmostEqual(move.tax_totals["tax_amount_currency"], tax_amount)
        self.assertAlmostEqual(move.amount_total, total)

    def test_bill_untaxed_line_edit_keeps_manual_tax_in_form(self):
        bill = self._move_with_manual_tax("in_invoice")
        self.assertAlmostEqual(self._edit_line_in_form(bill, "untaxed", 6.0), 1.60)
        self._assert_saved_tax(bill, 1.60, 17.60)

    def test_invoice_untaxed_line_edit_keeps_manual_tax_in_form(self):
        invoice = self._move_with_manual_tax("out_invoice")
        self.assertAlmostEqual(self._edit_line_in_form(invoice, "untaxed", 6.0), 1.60)
        self._assert_saved_tax(invoice, 1.60, 17.60)

    def test_bill_taxed_line_edit_recomputes_tax_in_form(self):
        bill = self._move_with_manual_tax("in_invoice")
        self.assertAlmostEqual(self._edit_line_in_form(bill, "taxed", 20.0), 3.00)
        self._assert_saved_tax(bill, 3.00, 28.00)

    def test_invoice_taxed_line_edit_recomputes_tax_in_form(self):
        invoice = self._move_with_manual_tax("out_invoice")
        self.assertAlmostEqual(self._edit_line_in_form(invoice, "taxed", 20.0), 3.00)
        self._assert_saved_tax(invoice, 3.00, 28.00)

    def test_unsaved_terms_follow_kept_manual_tax(self):
        invoice = self._move_with_manual_tax("out_invoice")
        unsaved = invoice.new(origin=invoice)
        unsaved.invoice_line_ids.filtered(
            lambda line: line.name == "untaxed"
        ).price_unit = 6.0
        self.assertAlmostEqual(unsaved.tax_totals["tax_amount_currency"], 1.60)
        self.assertEqual(
            [values["amount_currency"] for values in unsaved.needed_terms.values()],
            [17.60],
        )
