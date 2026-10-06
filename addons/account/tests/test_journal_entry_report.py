from lxml import html

from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestJournalEntryReport(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = cls.env.ref("account.action_report_journal_entry")
        cls.other_currency = cls.setup_other_currency("EUR")

    def _make_entry(self, *, post=True, currency=None):
        currency = currency or self.company_data["currency"]
        amount = 100.0 if currency == self.company_data["currency"] else 300.0
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2026-01-01",
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "currency_id": currency.id,
                            "amount_currency": amount,
                            "debit": 100.0,
                            "name": "D",
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_expense"
                            ].id,
                            "currency_id": currency.id,
                            "amount_currency": -amount,
                            "credit": 100.0,
                            "name": "C",
                        }
                    ),
                ],
            }
        )
        if post:
            move.action_post()
        return move

    def _render(self, move):
        content, _ = self.report._render_qweb_html(self.report.report_name, move.ids)
        return html.fromstring(content)

    def _table_widths(self, tree):
        table = "//table[@name='journal_entry_line_table']"
        head = tree.xpath(f"{table}/thead/tr/th")
        rows = tree.xpath(f"{table}/tbody/tr")
        total = tree.xpath(f"{table}/tfoot/tr[@name='tr_total']/td")
        return (
            len(head),
            {len(row.xpath("td")) for row in rows},
            sum(int(td.get("colspan", "1")) for td in total),
            len(rows),
        )

    def test_title_follows_the_state(self):
        draft = self._make_entry(post=False)
        self.assertIn("Draft Journal Entry", self._render(draft).text_content())
        posted = self._make_entry()
        text = self._render(posted).text_content()
        self.assertIn("Journal Entry", text)
        self.assertNotIn("Draft Journal Entry", text)
        self.assertIn(posted.name, text)

    def test_company_currency_entry_has_no_currency_or_tax_column(self):
        head, body, total, rows = self._table_widths(self._render(self._make_entry()))
        self.assertEqual((head, body, total, rows), (5, {5}, 5, 2))

    def test_foreign_currency_entry_shows_the_amount_in_currency(self):
        tree = self._render(self._make_entry(currency=self.other_currency))
        head, body, total, _rows = self._table_widths(tree)
        self.assertEqual((head, body, total), (6, {6}, 6))
        cells = tree.xpath("//td[@name='td_amount_currency']")
        self.assertEqual(len(cells), 2)
        self.assertTrue(all(cell.text_content().strip() for cell in cells))

    def test_invoice_prints_its_accounting_lines_only(self):
        invoice = self.init_invoice(
            "out_invoice",
            partner=self.partner_a,
            invoice_date="2026-01-01",
            products=self.product_a,
            taxes=self.tax_sale_a,
        )
        invoice.invoice_line_ids = [
            Command.create({"display_type": "line_section", "name": "Section"}),
            Command.create({"display_type": "line_note", "name": "Note"}),
        ]
        invoice.action_post()
        accounting_lines = invoice.line_ids.filtered(
            lambda line: (
                line.display_type
                not in ("line_section", "line_subsection", "line_note")
            )
        )
        self.assertLess(len(accounting_lines), len(invoice.line_ids))

        tree = self._render(invoice)
        head, body, total, rows = self._table_widths(tree)
        self.assertEqual(rows, len(accounting_lines))
        self.assertEqual(head, 7, "tax line and taxes columns join the five")
        self.assertEqual(body, {7})
        self.assertEqual(total, 7)
        self.assertNotIn(
            "Section",
            tree.xpath("//table[@name='journal_entry_line_table']")[0].text_content(),
        )

    def test_balanced_entry_has_no_warning(self):
        tree = self._render(self._make_entry())
        self.assertFalse(tree.xpath("//tr[@name='tr_unbalanced']"))
