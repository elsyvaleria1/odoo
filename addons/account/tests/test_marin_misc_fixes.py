import io
import zipfile

from odoo import Command
from odoo.tests import tagged
from odoo.tools import SQL

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account.tools import structured_reference as sr
from odoo.addons.account.tools.account_prefix import split_account_prefixes
from odoo.addons.account.tools.zip_archive import unique_filenames


@tagged("post_install", "-at_install")
class TestMarinStructuredReferenceCountry(AccountTestInvoicingCommon):
    def test_country_check_accepts_danish_references(self):
        reference = "+71<000000000000018+12345678<"
        self.assertTrue(sr.is_valid_structured_reference_dk(reference))
        self.assertTrue(sr.is_valid_structured_reference_for_country(reference, "DK"))

    def test_country_check_accepts_iso_references_in_every_country(self):
        for country in ("BE", "FI", "NL", "NO", "SE", "SI", "DK", ""):
            self.assertTrue(
                sr.is_valid_structured_reference_for_country(
                    "RF18 5390 0754 7034", country
                ),
                country,
            )

    def test_country_check_rejects_national_schemes_of_other_countries(self):
        self.assertFalse(sr.is_valid_structured_reference_for_country("1234567", "BE"))
        self.assertFalse(
            sr.is_valid_structured_reference_for_country("79927398713", "BE")
        )
        self.assertFalse(
            sr.is_valid_structured_reference_for_country("+++020/3430/57642+++", "NL")
        )
        self.assertTrue(sr.is_valid_structured_reference_for_country("1234567", "NL"))
        self.assertTrue(
            sr.is_valid_structured_reference_for_country("79927398713", "se")
        )
        self.assertFalse(sr.is_valid_structured_reference_for_country(False, "BE"))


@tagged("post_install", "-at_install")
class TestMarinAnalyticAccountPrefix(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plan = cls.env["account.analytic.plan"].create({"name": "Prefix plan"})
        cls.analytic_account = cls.env["account.analytic.account"].create(
            {"name": "Prefix analytic", "plan_id": cls.plan.id}
        )

    def test_split_account_prefixes_drops_empty_pieces(self):
        self.assertEqual(split_account_prefixes("60, "), ("60",))
        self.assertEqual(split_account_prefixes("60;;61"), ("60", "61"))
        self.assertEqual(split_account_prefixes(" 6 0 , 61;"), ("60", "61"))
        self.assertEqual(split_account_prefixes(False), ())

    def test_distribution_model_prefix_with_trailing_separator(self):
        Model = self.env["account.analytic.distribution.model"]
        for account_prefix in ("60, ", "60;;61"):
            model = Model.create(
                {
                    "account_prefix": account_prefix,
                    "analytic_distribution": {self.analytic_account.id: 100},
                }
            )
            applicable = Model._get_applicable_models(
                {"account_prefix": "400000", "company_id": self.env.company.id}
            )
            self.assertNotIn(model, applicable, account_prefix)
            applicable = Model._get_applicable_models(
                {"account_prefix": "601000", "company_id": self.env.company.id}
            )
            self.assertIn(model, applicable, account_prefix)
            model.unlink()

    def test_prefix_placeholders_tolerate_an_account_without_code(self):
        codeless_company = self.env["res.company"].create({"name": "Codeless Co"})
        self.env.user.company_ids |= codeless_company
        account = (
            self.env["account.account"]
            .with_company(codeless_company)
            .create(
                {
                    "name": "Codeless expense",
                    "code": "612000",
                    "account_type": "expense",
                    "company_ids": [Command.set(codeless_company.ids)],
                }
            )
        )
        self.env.cr.execute(
            SQL(
                "UPDATE account_account SET code_store = NULL WHERE id = %s", account.id
            )
        )
        self.env.invalidate_all()
        env = self.env(
            context=dict(self.env.context, allowed_company_ids=[codeless_company.id])
        )
        self.assertFalse(account.with_env(env).code)
        model = env["account.analytic.distribution.model"].new({})
        self.assertEqual(model.prefix_placeholder, "e.g. 60, 61, 62")
        applicability = env["account.analytic.applicability"].new(
            {"business_domain": "bill"}
        )
        self.assertEqual(applicability.account_prefix_placeholder, "e.g. 60, 61, 62")


@tagged("post_install", "-at_install")
class TestMarinPreferredInvoiceReport(AccountTestInvoicingCommon):
    def test_preferred_report_is_saved_where_it_is_read(self):
        contact = self.env["res.partner"].create(
            {
                "name": "Invoicing contact",
                "type": "invoice",
                "email": "contact@example.com",
                "parent_id": self.partner_a.id,
            }
        )
        invoice = self.init_invoice(
            "out_invoice", partner=contact, amounts=[100.0], post=True
        )
        report = self.env.ref("account.account_invoices_without_payment")
        wizard = self._create_account_move_send_wizard_single(invoice)
        wizard.pdf_report_id = report

        wizard._update_preferred_settings()

        self.assertEqual(self.partner_a.invoice_template_pdf_report_id, report)
        self.assertFalse(contact.invoice_template_pdf_report_id)
        self.assertEqual(
            self.env["mixin.account.move.send"]._get_default_pdf_report_id(invoice),
            report,
        )


@tagged("post_install", "-at_install")
class TestMarinResequenceFirstName(AccountTestInvoicingCommon):
    def _entry(self, name):
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2026-03-01",
                "name": name,
                "journal_id": self.company_data["default_journal_misc"].id,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "debit": 10.0,
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_expense"
                            ].id,
                            "credit": 10.0,
                        }
                    ),
                ],
            }
        )
        move.action_post()
        return move

    def test_first_name_follows_the_sequence_number_not_the_string(self):
        moves = self._entry("TST/2026/9") | self._entry("TST/2026/10")
        self.assertEqual(moves.mapped("sequence_number"), [9, 10])
        wizard = self.env["wizard.account.move.resequence"].create(
            {"move_ids": [Command.set(moves.ids)]}
        )
        self.assertEqual(wizard.first_name, "TST/2026/9")


@tagged("post_install", "-at_install")
class TestMarinArchivedBankAccountGuard(AccountTestInvoicingCommon):
    def test_archived_account_is_found_whatever_the_spacing(self):
        account = self.env["res.partner.bank.account"].create(
            {"acc_number": "BE68539007547034", "partner_id": self.partner_a.id}
        )
        account.action_archive()
        with self.assertRaisesRegex(Exception, "archived"):
            self.env["res.partner.bank.account"].create(
                {"acc_number": "BE68 5390 0754 7034", "partner_id": self.partner_a.id}
            )


@tagged("post_install", "-at_install")
class TestMarinBudgetCopy(AccountTestInvoicingCommon):
    def _budget(self):
        account = self.company_data["default_account_revenue"]
        return self.env["account.report.budget"].create(
            {
                "name": "Budget",
                "item_ids": [
                    Command.create(
                        {"account_id": account.id, "amount": 10.0, "date": "2026-01-01"}
                    ),
                    Command.create(
                        {"account_id": account.id, "amount": 20.0, "date": "2026-02-01"}
                    ),
                ],
            }
        )

    def test_copy_keeps_a_passed_name(self):
        budget = self._budget()
        self.assertEqual(budget.copy({"name": "Budget 2027"}).name, "Budget 2027")
        self.assertEqual(budget.copy().name, "Budget (copy)")

    def test_copy_duplicates_every_item(self):
        budgets = self._budget() | self._budget()
        copies = budgets.copy()
        for budget, copy in zip(budgets, copies, strict=True):
            self.assertNotEqual(copy.item_ids, budget.item_ids)
            self.assertEqual(
                sorted(
                    copy.item_ids.mapped(lambda i: (i.account_id, i.amount, i.date))
                ),
                sorted(
                    budget.item_ids.mapped(lambda i: (i.account_id, i.amount, i.date))
                ),
            )


@tagged("post_install", "-at_install")
class TestMarinCurrencyTableSharedRates(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shared_currency = cls.env["res.currency"].create(
            {"name": "SHR", "symbol": "S", "rounding": 0.01}
        )
        cls.shared_company = cls.env["res.company"].create(
            {"name": "SHR Co", "currency_id": cls.shared_currency.id}
        )

    def _rate(self, date, rate, company=False):
        self.env["res.currency.rate"].create(
            {
                "name": date,
                "rate": rate,
                "currency_id": self.shared_currency.id,
                "company_id": company and company.id,
            }
        )

    def _table_rate(self, date_to):
        self.env["res.currency"]._create_currency_table(
            self.env.company | self.shared_company, [("period", None, date_to)]
        )
        self.env.cr.execute(
            SQL(
                "SELECT rate FROM account_currency_table WHERE company_id = %s AND rate_type = 'current'",
                self.shared_company.id,
            )
        )
        return self.env.cr.fetchone()[0]

    def _expected(self, date_to):
        main = self.env.company
        main_factor = main.currency_id._get_rates(main, date_to)[main.currency_id.id]
        rate = self.shared_currency._get_rates(main, date_to)[self.shared_currency.id]
        return main_factor / rate

    def test_current_rate_reads_shared_rates(self):
        self._rate("2020-01-01", 4.0)
        self.assertAlmostEqual(
            self._table_rate("2020-06-01"), self._expected("2020-06-01")
        )
        self.assertNotEqual(self._table_rate("2020-06-01"), 1)

    def test_company_rates_take_precedence_over_shared_rates(self):
        self._rate("2020-01-01", 4.0)
        self._rate("2020-03-01", 5.0, self.env.company.root_id)
        self._rate("2020-05-01", 6.0)
        for date_to in ("2020-02-01", "2020-04-01", "2020-06-01"):
            self.assertAlmostEqual(
                self._table_rate(date_to), self._expected(date_to), msg=date_to
            )

    def test_cta_rates_read_shared_rates(self):
        self._rate("2020-01-01", 4.0)
        self.env["res.currency"]._create_currency_table(
            self.env.company | self.shared_company,
            [("period", "2020-01-01", "2020-06-01")],
            use_cta_rates=True,
        )
        self.env.cr.execute(
            SQL(
                "SELECT rate_type, rate FROM account_currency_table WHERE company_id = %s",
                self.shared_company.id,
            )
        )
        rates = dict(self.env.cr.fetchall())
        expected = self._expected("2020-06-01")
        for rate_type in ("current", "historical", "average"):
            self.assertAlmostEqual(rates[rate_type], expected, msg=rate_type)


@tagged("post_install", "-at_install")
class TestMarinBatchSendWizardPreview(AccountTestInvoicingCommon):
    def test_opening_the_batch_wizard_creates_no_partner(self):
        invoices = self.init_invoice(
            "out_invoice", partner=self.partner_a, amounts=[1000], post=True
        ) | self.init_invoice(
            "out_invoice", partner=self.partner_b, amounts=[1000], post=True
        )
        (self.partner_a | self.partner_b).write(
            {"email": "known@example.com", "invoice_sending_method": "email"}
        )
        self.env.ref("account.email_template_edi_invoice").write(
            {"use_default_to": False, "email_cc": "fresh.recipient@example.com"}
        )
        Partner = self.env["res.partner"].with_context(active_test=False)
        domain = [("email_normalized", "=", "fresh.recipient@example.com")]

        wizard = self._create_account_move_send_wizard_multi(invoices)
        summary_data = wizard.summary_data
        alerts = wizard.alerts

        self.assertFalse(Partner.search_count(domain))
        self.assertEqual(summary_data, {"email": {"count": 2, "label": "by Email"}})
        self.assertFalse(alerts)


@tagged("post_install", "-at_install")
class TestMarinZipDuplicateNames(AccountTestInvoicingCommon):
    def test_unique_filenames(self):
        self.assertEqual(
            unique_filenames(["a.pdf", "a (1).pdf", "a.pdf", "a.pdf", "b"]),
            ["a.pdf", "a (1).pdf", "a (2).pdf", "a (3).pdf", "b"],
        )

    def test_attachment_zip_keeps_every_attachment(self):
        attachments = self.env["ir.attachment"].create(
            [{"name": "doc.pdf", "raw": f"content {i}".encode()} for i in range(2)]
        )
        content = attachments._prepare_zip_from_attachments()
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertEqual(archive.namelist(), ["doc.pdf", "doc (1).pdf"])
            self.assertEqual(
                {archive.read(name) for name in archive.namelist()},
                {b"content 0", b"content 1"},
            )


@tagged("post_install", "-at_install")
class TestMarinZipCaseInsensitiveNames(AccountTestInvoicingCommon):
    def test_names_differing_only_by_case_do_not_collide(self):
        self.assertEqual(
            unique_filenames(["INV_1.pdf", "inv_1.pdf", "Inv_1.PDF", "inv_1 (1).pdf"]),
            ["INV_1.pdf", "inv_1 (1).pdf", "Inv_1 (2).PDF", "inv_1 (1) (1).pdf"],
        )

    def test_a_name_that_is_only_an_extension_keeps_it(self):
        self.assertEqual(
            unique_filenames([".pdf", ".pdf", ".PDF"]),
            [".pdf", "(1).pdf", "(2).PDF"],
        )


@tagged("post_install", "-at_install")
class TestMarinAnalyticButtonsCountWhatTheyOpen(AccountTestInvoicingCommon):
    def _move(self, move_type, analytic_account, post):
        move = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-06-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "line",
                            "price_unit": 100.0,
                            "tax_ids": [Command.clear()],
                            "analytic_distribution": {analytic_account.id: 100},
                        }
                    )
                ],
            }
        )
        if post:
            move.action_post()
        return move

    def test_invoice_and_bill_buttons_open_what_they_count(self):
        plan = self.env["account.analytic.plan"].create({"name": "Buttons plan"})
        analytic_account = self.env["account.analytic.account"].create(
            {"name": "Buttons analytic", "plan_id": plan.id}
        )
        posted_invoice = self._move("out_invoice", analytic_account, post=True)
        self._move("out_invoice", analytic_account, post=False)
        posted_bill = self._move("in_invoice", analytic_account, post=True)
        self._move("in_invoice", analytic_account, post=False)

        for count_field, action, posted in (
            ("invoice_count", analytic_account.action_view_invoice, posted_invoice),
            (
                "vendor_bill_count",
                analytic_account.action_view_vendor_bill,
                posted_bill,
            ),
        ):
            opened = self.env["account.move"].search(action()["domain"])
            self.assertEqual(opened, posted, count_field)
            self.assertEqual(analytic_account[count_field], len(opened), count_field)
