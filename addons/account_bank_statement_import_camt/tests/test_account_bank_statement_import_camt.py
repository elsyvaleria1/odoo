from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account_bank_statement_import_camt.models.account_journal import (
    _logger as camt_wizard_logger,
)

NORMAL_AMOUNTS = [100, 150, 250]
LARGE_AMOUNTS = [10000, 15000, 25000]


@tagged("post_install", "-at_install")
class TestAccountBankStatementImportCamt(AccountTestInvoicingCommon):
    def test_camt_file_import(self):
        bank_journal = self.env["account.journal"].create(
            {
                "name": "Bank 123456",
                "code": "BNK67",
                "type": "bank",
                "bank_acc_number": "123456",
                "currency_id": self.env.ref("base.USD").id,
            }
        )

        partner_norbert = self.env["res.partner"].create(
            {
                "name": "Norbert Brant",
                "is_company": True,
            }
        )
        bank_norbert = self.env["res.bank"].create({"name": "test"})

        self.env["res.partner.bank.account"].create(
            {
                "acc_number": "BE93999574162167",
                "partner_id": partner_norbert.id,
                "bank_id": bank_norbert.id,
            }
        )
        self.env["res.partner.bank.account"].create(
            {
                "acc_number": "10987654323",
                "partner_id": self.partner_a.id,
                "bank_id": bank_norbert.id,
            }
        )

        camt_file_path = (
            "account_bank_statement_import_camt/test_camt_file/test_camt.xml"
        )
        with file_open(camt_file_path, "rb") as camt_file:
            bank_journal.create_document_from_attachment(
                self.env["ir.attachment"]
                .create(
                    {
                        "mimetype": "application/xml",
                        "name": "test_camt.xml",
                        "raw": camt_file.read(),
                    }
                )
                .ids
            )

        imported_statement = self.env["account.bank.statement"].search(
            [("company_id", "=", self.env.company.id)]
        )
        self.assertRecordValues(
            imported_statement,
            [
                {
                    "name": "0574908765.2015-12-05",
                    "balance_start": 8998.20,
                    "balance_end_real": 2661.49,
                }
            ],
        )
        self.assertRecordValues(
            imported_statement.line_ids.sorted("ref"),
            [
                {
                    "ref": "INNDNL2U20141231000142300002844",
                    "partner_name": "ASUSTeK",
                    "amount": -7379.54,
                    "partner_id": False,
                },
                {
                    "ref": "INNDNL2U20150105000217200000708",
                    "partner_name": partner_norbert.name,
                    "amount": 1636.88,
                    "partner_id": partner_norbert.id,
                },
                {
                    "ref": "TESTBANK/NL/20151129/01206408",
                    "partner_name": "China Export",
                    "amount": -564.05,
                    "partner_id": self.partner_a.id,
                },
            ],
        )

    def test_minimal_camt_file_import(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import("camt_053_minimal.xml", usd_currency)

    def test_minimal_and_multicurrency_camt_file_import(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_minimal_and_multicurrency.xml", usd_currency
        )

    def test_minimal_and_multicurrency_camt_file_import_02(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_minimal_and_multicurrency_02.xml", usd_currency
        )

    def test_minimal_and_multicurrency_camt_file_import_03(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_minimal_and_multicurrency_03.xml", usd_currency
        )

    def test_minimal_and_multicurrency_camt_file_import_04(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_minimal_and_multicurrency_04.xml", usd_currency
        )

    def test_minimal_and_multicurrency_camt_file_import_05(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_minimal_and_multicurrency_05.xml", usd_currency
        )

    def test_minimal_and_multicurrency_camt_file_import_06(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_minimal_and_multicurrency_06.xml", usd_currency
        )

    def test_minimal_and_multicurrency_camt_file_import_07(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_minimal_and_multicurrency_07.xml", usd_currency
        )

    def test_several_minimal_stmt_different_currency(self):
        usd_currency = self.env.ref("base.USD")
        eur_currency = self.env.ref("base.EUR")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_several_minimal_stmt_different_currency.xml", usd_currency
        )
        eur_currency.active = True
        self._test_minimal_camt_file_import(
            "camt_053_several_minimal_stmt_different_currency.xml",
            eur_currency,
            start_balance=2000,
            end_balance=3000,
        )

    def test_journal_with_other_currency(self):
        self.assertEqual(self.env.company.currency_id.id, self.env.ref("base.USD").id)
        self.env.ref("base.EUR").active = True
        self._test_minimal_camt_file_import(
            "camt_053_minimal_EUR.xml", self.env.ref("base.EUR")
        )

    def _import_camt_file(self, camt_file_name, currency):
        BankAccount = self.env["res.partner.bank.account"]
        partner = self.env.user.company_id.partner_id
        bank_account = BankAccount.search(
            [("acc_number", "=", "112233"), ("partner_id", "=", partner.id)]
        ) or BankAccount.create({"acc_number": "112233", "partner_id": partner.id})
        bank_journal = self.env["account.journal"].create(
            {
                "name": "Bank 112233 %s" % currency.name,
                "code": "B-%s" % currency.name,
                "type": "bank",
                "bank_account_id": bank_account.id,
                "currency_id": currency.id,
            }
        )

        camt_file_path = (
            f"account_bank_statement_import_camt/test_camt_file/{camt_file_name}"
        )
        with file_open(camt_file_path, "rb") as camt_file:
            bank_journal.create_document_from_attachment(
                self.env["ir.attachment"]
                .create(
                    {
                        "mimetype": "application/xml",
                        "name": "test_camt.xml",
                        "raw": camt_file.read(),
                    }
                )
                .ids
            )

    def _test_minimal_camt_file_import(
        self, camt_file_name, currency, start_balance=1000, end_balance=1500
    ):
        self._import_camt_file(camt_file_name, currency)
        bank_st_record = (
            self.env["account.bank.statement"]
            .search([("name", "=", "2514988305.2019-02-13")])
            .filtered(lambda bk_stmt: bk_stmt.currency_id == currency)
            .check_singleton()
        )
        self.assertEqual(
            bank_st_record.balance_start, start_balance, "Start balance not matched"
        )
        self.assertEqual(
            bank_st_record.balance_end_real, end_balance, "End balance not matched"
        )

        line = bank_st_record.line_ids.check_singleton()
        self.assertEqual(
            line.amount, end_balance - start_balance, "Transaction not matched"
        )

    def _test_camt_with_several_tx_details(self, filename, expected_amounts=None):
        if expected_amounts is None:
            expected_amounts = NORMAL_AMOUNTS
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._import_camt_file(filename, usd_currency)
        imported_statement = self.env["account.bank.statement"].search(
            [("company_id", "=", self.env.company.id)], order="id desc", limit=1
        )
        self.assertEqual(len(imported_statement.line_ids), 3)
        self.assertEqual(imported_statement.line_ids[0].payment_ref, "label01")
        self.assertEqual(
            usd_currency.round(imported_statement.line_ids[0].amount),
            expected_amounts[0],
        )
        self.assertEqual(imported_statement.line_ids[1].payment_ref, "label02")
        self.assertEqual(
            usd_currency.round(imported_statement.line_ids[1].amount),
            expected_amounts[1],
        )
        self.assertEqual(imported_statement.line_ids[2].payment_ref, "label03")
        self.assertEqual(
            usd_currency.round(imported_statement.line_ids[2].amount),
            expected_amounts[2],
        )

    def test_camt_with_several_tx_details(self):
        self._test_camt_with_several_tx_details("camt_053_several_tx_details.xml")

    def test_camt_with_several_tx_details_and_instructed_amount(self):
        self._test_camt_with_several_tx_details(
            "camt_053_several_tx_details_and_instructed_amount.xml"
        )

    def test_camt_with_several_tx_details_and_instructed_amount_02(self):
        self._test_camt_with_several_tx_details(
            "camt_053_several_tx_details_and_instructed_amount_02.xml"
        )

    def test_camt_with_several_tx_details_and_multicurrency_01(self):
        self._test_camt_with_several_tx_details(
            "camt_053_several_tx_details_and_multicurrency_01.xml"
        )

    def test_camt_with_several_tx_details_and_multicurrency_02(self):
        self._test_camt_with_several_tx_details(
            "camt_053_several_tx_details_and_multicurrency_02.xml"
        )

    def test_camt_with_several_tx_details_and_multicurrency_03(self):
        self._test_camt_with_several_tx_details(
            "camt_053_several_tx_details_and_multicurrency_03.xml"
        )

    def test_camt_with_several_tx_details_and_multicurrency_04(self):
        self._test_camt_with_several_tx_details(
            "camt_053_several_tx_details_and_multicurrency_04.xml",
            expected_amounts=LARGE_AMOUNTS,
        )

    def test_camt_with_several_tx_details_and_multicurrency_05(self):
        self._test_camt_with_several_tx_details(
            "camt_053_several_tx_details_and_multicurrency_05.xml",
            expected_amounts=[-18918.02, -23508.64, -7573.34],
        )

    def test_camt_with_several_tx_details_and_charges(self):
        self._test_camt_with_several_tx_details(
            "camt_053_several_tx_details_and_charges.xml"
        )

    def test_several_ibans_match_journal_camt_file_import(self):
        bank_journal = self.env["account.journal"].create(
            {
                "name": "Bank BE86 6635 9439 7150",
                "code": "BNK69",
                "type": "bank",
                "bank_acc_number": "BE86 6635 9439 7150",
                "currency_id": self.env.ref("base.USD").id,
            }
        )

        camt_file_path = "account_bank_statement_import_camt/test_camt_file/camt_053_several_ibans.xml"
        with file_open(camt_file_path, "rb") as camt_file:
            with self.assertLogs(camt_wizard_logger, level="WARNING") as log_catcher:
                bank_journal.create_document_from_attachment(
                    self.env["ir.attachment"]
                    .create(
                        {
                            "mimetype": "application/xml",
                            "name": "test_camt.xml",
                            "raw": camt_file.read(),
                        }
                    )
                    .ids
                )
        self.assertEqual(
            len(log_catcher.output), 1, "Exactly one warning should be logged"
        )
        self.assertIn(
            "The following statements will not be imported",
            log_catcher.output[0],
            "The logged warning warns about non-imported statements",
        )

        imported_statement = self.env["account.bank.statement"].search(
            [("company_id", "=", self.env.company.id)]
        )
        self.assertRecordValues(
            imported_statement,
            [
                {
                    "name": "2514988305.2019-05-23",
                    "balance_start": 1000.00,
                    "balance_end_real": 1600.00,
                }
            ],
        )
        self.assertRecordValues(
            imported_statement.line_ids.sorted("ref"), [{"amount": 600.00}]
        )

    def test_several_ibans_missing_journal_id_camt_file_import(self):
        bank_journal = self.env["account.journal"].create(
            {
                "name": "Bank BE43 9787 8497 9701",
                "code": "BNK69",
                "type": "bank",
                "currency_id": self.env.ref("base.USD").id,
            }
        )

        camt_file_path = "account_bank_statement_import_camt/test_camt_file/camt_053_several_ibans.xml"
        with file_open(camt_file_path, "rb") as camt_file:
            with self.assertLogs(camt_wizard_logger, level="WARNING") as log_catcher:
                with self.assertRaises(UserError) as error_catcher:
                    bank_journal.create_document_from_attachment(
                        self.env["ir.attachment"]
                        .create(
                            {
                                "mimetype": "application/xml",
                                "name": "test_camt.xml",
                                "raw": camt_file.read(),
                            }
                        )
                        .ids
                    )

        self.assertEqual(
            len(log_catcher.output), 1, "Exactly one warning should be logged"
        )
        self.assertIn(
            "The following statements will not be imported",
            log_catcher.output[0],
            "The logged warning warns about non-imported statements",
        )

        self.assertEqual(
            error_catcher.exception.args[0],
            (
                "All or part of the following file(s) could not be imported:\n"
                "- test_camt.xml: Please set the IBAN account on your bank journal.\n\n"
                "This CAMT file is targeting several IBAN accounts but none match the current journal."
            ),
        )

    def test_date_and_time_format_camt_file_import(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_minimal_datetime.xml", usd_currency
        )

    def test_intraday_camt_file_import(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_minimal_intraday.xml", usd_currency
        )

    def test_charges_camt_file_import(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_minimal_charges.xml", usd_currency
        )

    def test_charges_camt_file_import_02(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_minimal_charges_02.xml", usd_currency
        )

    def test_charges_camt_file_import_03(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import(
            "camt_053_minimal_charges_03.xml", usd_currency
        )

    def test_import_already_fully_imported_catm_without_opening_balance(self):
        bank_journal = self.env["account.journal"].create(
            {
                "name": "Bank 123456",
                "code": "BNK67",
                "type": "bank",
                "bank_acc_number": "112233",
                "currency_id": self.env.ref("base.USD").id,
            }
        )

        camt_file_path = "account_bank_statement_import_camt/test_camt_file/test_camt_no_opening_balance.xml"

        def import_file():
            with file_open(camt_file_path, "rb") as camt_file:
                bank_journal.create_document_from_attachment(
                    self.env["ir.attachment"]
                    .create(
                        {
                            "mimetype": "application/xml",
                            "name": "test_camt_no_opening_balance.xml",
                            "raw": camt_file.read(),
                        }
                    )
                    .ids
                )

        import_file()
        with self.assertRaises(UserError, msg="You already have imported that file."):
            import_file()

    def test_import_camt_with_nordic_tags(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._import_camt_file("camt_053_several_tx_details_nordic.xml", usd_currency)
        imported_statement = self.env["account.bank.statement"].search(
            [("company_id", "=", self.env.company.id)], order="id desc", limit=1
        )
        self.assertEqual(len(imported_statement.line_ids), 3)
        third_line = imported_statement.line_ids[2]
        self.assertEqual(third_line.payment_ref, "Transaction 03 name")
        self.assertEqual(third_line.partner_name, "Ultimate Debtor Name")

    def test_import_camt_additional_entry_info(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._import_camt_file("camt_053_additional_entry_info.xml", usd_currency)
        imported_statement = self.env["account.bank.statement"].search(
            [("company_id", "=", self.env.company.id)], order="id desc", limit=1
        )
        self.assertEqual(len(imported_statement.line_ids), 1)
        self.assertEqual(imported_statement.line_ids.payment_ref, "entry info")

    def test_import_camt_amounts_with_fees(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._import_camt_file("camt_053_exchange_fees.xml", usd_currency)
        imported_statement = self.env["account.bank.statement"].search(
            [("company_id", "=", self.env.company.id)], order="id desc", limit=1
        )
        self.assertEqual(len(imported_statement.line_ids), 1)
        self.assertRecordValues(
            imported_statement.line_ids,
            [
                {
                    "amount": 1672.98,
                }
            ],
        )

    def test_camt_file_import_namespace(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import("camt_053_namespace.xml", usd_currency)

    def test_camt_file_import_custom_code(self):
        usd_currency = self.env.ref("base.USD")
        self.assertEqual(self.env.company.currency_id.id, usd_currency.id)
        self._test_minimal_camt_file_import("camt_053_custom_codes.xml", usd_currency)
        bank_st_record = (
            self.env["account.bank.statement"]
            .search([("name", "=", "2514988305.2019-02-13")])
            .filtered(lambda bk_stmt: bk_stmt.currency_id == usd_currency)
            .check_singleton()
        )
        line = bank_st_record.line_ids.check_singleton()
        self.assertEqual(
            line.transaction_type, "custom_code: custom_family (custom_subfamily)"
        )

    def test_camt_transaction_type_is_written_in_the_importing_user_language(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        self.env = self.env(context=dict(self.env.context, lang="fr_FR"))
        usd_currency = self.env.ref("base.USD")
        self._test_minimal_camt_file_import(
            "camt_053_minimal_and_multicurrency_03.xml", usd_currency
        )
        line = (
            self.env["account.bank.statement"]
            .search([("name", "=", "2514988305.2019-02-13")])
            .line_ids.check_singleton()
        )
        self.assertEqual(
            line.transaction_type, "Paiements: Virements reçus (Virement SEPA)"
        )
