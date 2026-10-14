from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestJournalTaxPolicy(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        revenue = cls.company_data["default_account_revenue"]
        cls.optional_journal = cls.company_data["default_journal_sale"]
        cls.forbidden_journal = cls.env["account.journal"].create(
            {
                "name": "Sales Without Taxes",
                "code": "STXF",
                "type": "sale",
                "default_account_id": revenue.id,
                "tax_policy": "forbidden",
            }
        )
        cls.required_journal = cls.env["account.journal"].create(
            {
                "name": "Sales With Taxes",
                "code": "STXR",
                "type": "sale",
                "default_account_id": revenue.id,
                "tax_policy": "required",
            }
        )

    def _invoice(self, journal, products=None, amounts=None, taxes=None):
        return self.init_invoice(
            "out_invoice",
            products=products,
            amounts=amounts,
            taxes=taxes,
            journal=journal,
        )

    def test_only_sale_and_purchase_journals_take_a_policy(self):
        with self.assertRaises(ValidationError):
            self.company_data["default_journal_misc"].tax_policy = "required"

    def test_forbidden_journal_never_fetches_product_taxes(self):
        invoice = self._invoice(self.forbidden_journal, products=self.product_a)
        self.assertFalse(invoice.invoice_line_ids.tax_ids)
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")

    def test_journal_switch_drops_and_restores_automatic_taxes(self):
        invoice = self._invoice(self.optional_journal, products=self.product_a)
        self.assertEqual(invoice.invoice_line_ids.tax_ids, self.tax_sale_a)
        invoice.journal_id = self.forbidden_journal
        self.assertFalse(invoice.invoice_line_ids.tax_ids)
        invoice.journal_id = self.optional_journal
        self.assertEqual(invoice.invoice_line_ids.tax_ids, self.tax_sale_a)

    def test_manual_tax_on_forbidden_journal_is_kept_and_refused(self):
        invoice = self._invoice(self.optional_journal, products=self.product_a)
        invoice.invoice_line_ids.tax_ids = self.tax_sale_b
        invoice.journal_id = self.forbidden_journal
        self.assertEqual(invoice.invoice_line_ids.tax_ids, self.tax_sale_b)
        with self.assertRaisesRegex(UserError, "forbids taxes"):
            invoice.action_post()

    def test_manual_tax_survives_a_product_change(self):
        invoice = self._invoice(self.optional_journal, products=self.product_a)
        line = invoice.invoice_line_ids
        line.tax_ids = self.tax_sale_b
        line.product_id = self.product_b
        self.assertEqual(line.tax_ids, self.tax_sale_b)

    def test_explicit_taxes_on_create_count_as_manual(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "journal_id": self.forbidden_journal.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "tax_ids": [Command.set(self.tax_sale_b.ids)],
                        }
                    )
                ],
            }
        )
        self.assertEqual(invoice.invoice_line_ids.tax_ids, self.tax_sale_b)
        with self.assertRaisesRegex(UserError, "forbids taxes"):
            invoice.action_post()

    def test_required_journal_refuses_an_untaxed_line(self):
        invoice = self._invoice(self.required_journal, amounts=[100.0], taxes=[])
        with self.assertRaisesRegex(UserError, "requires a tax"):
            invoice.action_post()

    def test_required_journal_posts_a_taxed_invoice(self):
        invoice = self._invoice(self.required_journal, products=self.product_a)
        self.assertEqual(invoice.invoice_line_ids.tax_ids, self.tax_sale_a)
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")

    def test_credit_note_mirrors_an_untaxed_original(self):
        invoice = self._invoice(
            self.optional_journal, products=self.product_a, taxes=[]
        )
        invoice.action_post()
        self.optional_journal.tax_policy = "required"
        credit_note = invoice._reverse_moves()
        self.assertFalse(credit_note.invoice_line_ids.tax_ids)
        credit_note.action_post()
        self.assertEqual(credit_note.state, "posted")

    def test_default_journal_search_is_shared(self):
        self.assertEqual(
            self.env["account.journal"]._search_default_journal(
                self.env.company, ["sale"]
            ),
            self.env["account.move"]
            .with_context(default_move_type="out_invoice")
            .new({"move_type": "out_invoice"})
            ._search_default_journal(),
        )
