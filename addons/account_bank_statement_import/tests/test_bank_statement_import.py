from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestBankStatementImportHub(AccountTestInvoicingCommon):
    def test_find_additional_data_multi_match_raises_user_error(self):
        company_2 = self.env["res.company"].create({"name": "Other Co"})
        bank = self.env["res.bank"].create({"name": "Shared Bank"})
        acc_number = "BE68539007547034"
        bank_account_1 = self.env["res.partner.bank.account"].create(
            {
                "acc_number": acc_number,
                "partner_id": self.env.company.partner_id.id,
                "bank_id": bank.id,
            }
        )
        bank_account_2 = self.env["res.partner.bank.account"].create(
            {
                "acc_number": acc_number,
                "partner_id": company_2.partner_id.id,
                "bank_id": bank.id,
            }
        )
        self.env["account.journal"].with_company(self.env.company).create(
            {
                "name": "Journal 1",
                "code": "HUB1",
                "type": "bank",
                "company_id": self.env.company.id,
                "bank_account_id": bank_account_1.id,
            }
        )
        self.env["account.journal"].with_company(company_2).create(
            {
                "name": "Journal 2",
                "code": "HUB2",
                "type": "bank",
                "company_id": company_2.id,
                "bank_account_id": bank_account_2.id,
            }
        )
        multi_company_journal = self.env["account.journal"].with_context(
            allowed_company_ids=[self.env.company.id, company_2.id]
        )
        with self.assertRaises(UserError):
            multi_company_journal.browse()._find_additional_data(False, acc_number)

    def test_complete_bank_statement_vals_always_links_attachment(self):
        journal = self.company_data["default_journal_bank"]
        attachment = self.env["ir.attachment"].create(
            {"name": "statement.txt", "raw": b"dummy"}
        )
        stmts_vals = [{"reference": "already-set-by-parser", "transactions": []}]
        result = journal._complete_bank_statement_vals(
            stmts_vals, journal, "BE68539007547034", attachment
        )
        self.assertEqual(result[0]["reference"], "already-set-by-parser")
        self.assertEqual(result[0]["attachment_ids"][0][2], attachment.ids)

    def test_create_bank_statements_skips_duplicate_and_rebalances(self):
        journal = self.company_data["default_journal_bank"]
        first_batch = [
            {
                "reference": "batch-1",
                "balance_start": 0.0,
                "balance_end_real": 100.0,
                "transactions": [
                    {
                        "name": "line 1",
                        "date": "2026-01-01",
                        "amount": 100.0,
                        "unique_import_id": "dup-txn-1",
                    }
                ],
            }
        ]
        statement_ids, ignored_qty = journal._create_bank_statements(first_batch)
        self.assertEqual(ignored_qty, 0)
        self.assertEqual(len(statement_ids), 1)

        second_batch = [
            {
                "reference": "batch-2",
                "balance_start": 0.0,
                "balance_end_real": 150.0,
                "transactions": [
                    {
                        "name": "line 1 (duplicate)",
                        "date": "2026-01-01",
                        "amount": 100.0,
                        "unique_import_id": "dup-txn-1",
                    },
                    {
                        "name": "line 2",
                        "date": "2026-01-02",
                        "amount": 50.0,
                        "unique_import_id": "new-txn-2",
                    },
                ],
            }
        ]
        statement_ids_2, ignored_qty_2 = journal._create_bank_statements(second_batch)
        self.assertEqual(ignored_qty_2, 1)
        statement_2 = self.env["account.bank.statement"].browse(statement_ids_2)
        self.assertEqual(statement_2.balance_start, 100.0)
        self.assertEqual(len(statement_2.line_ids), 1)
        self.assertEqual(statement_2.balance_end, statement_2.balance_end_real)
        self.assertTrue(statement_2.is_complete)

    def test_create_bank_statements_zero_amount_line_is_not_counted_as_duplicate(self):
        journal = self.company_data["default_journal_bank"]
        batch = [
            {
                "reference": "zero-batch",
                "balance_start": 0.0,
                "balance_end_real": 10.0,
                "transactions": [
                    {
                        "name": "informational zero line",
                        "date": "2026-01-01",
                        "amount": 0.0,
                        "unique_import_id": "zero-txn-never-seen",
                    },
                    {
                        "name": "real line",
                        "date": "2026-01-01",
                        "amount": 10.0,
                        "unique_import_id": "real-txn-1",
                    },
                ],
            }
        ]
        statement_ids, ignored_qty = journal._create_bank_statements(batch)
        self.assertEqual(ignored_qty, 0)
        statement = self.env["account.bank.statement"].browse(statement_ids)
        self.assertEqual(len(statement.line_ids), 1)
        self.assertEqual(statement.balance_start, 0.0)

    def test_create_bank_statements_filters_duplicate_within_same_import(self):
        journal = self.company_data["default_journal_bank"]
        batch = [
            {
                "reference": "intra-1",
                "balance_start": 0.0,
                "balance_end_real": 25.0,
                "transactions": [
                    {
                        "name": "line",
                        "date": "2026-02-01",
                        "amount": 25.0,
                        "unique_import_id": "intra-dup-1",
                    }
                ],
            },
            {
                "reference": "intra-2",
                "balance_start": 25.0,
                "balance_end_real": 50.0,
                "transactions": [
                    {
                        "name": "line repeated",
                        "date": "2026-02-02",
                        "amount": 25.0,
                        "unique_import_id": "intra-dup-1",
                    }
                ],
            },
        ]
        statement_ids, ignored_qty = journal._create_bank_statements(batch)
        self.assertEqual(ignored_qty, 1)
        self.assertEqual(len(statement_ids), 1)

    def test_create_bank_statements_duplicate_check_is_batched(self):
        journal = self.company_data["default_journal_bank"]
        n_lines = 20

        def batch(reference):
            return [
                {
                    "reference": reference,
                    "balance_start": 0.0,
                    "balance_end_real": float(n_lines),
                    "transactions": [
                        {
                            "name": "line %d" % i,
                            "date": "2026-03-01",
                            "amount": 1.0,
                            "unique_import_id": "batched-%d" % i,
                        }
                        for i in range(n_lines)
                    ],
                }
            ]

        journal._create_bank_statements(batch("first"))
        self.env.flush_all()
        queries_before = self.env.cr.sql_log_count
        statement_ids, ignored_qty = journal._create_bank_statements(
            batch("second"), raise_no_imported_file=False
        )
        queries_after = self.env.cr.sql_log_count
        self.assertEqual(ignored_qty, n_lines)
        self.assertFalse(statement_ids)
        self.assertLess(queries_after - queries_before, n_lines)

    def test_a_statement_that_does_not_add_up_is_created_and_says_so(self):
        journal = self.company_data["default_journal_bank"]
        statement_ids, _ignored = journal._create_bank_statements(
            [
                {
                    "reference": "does-not-add-up",
                    "balance_start": 0.0,
                    "balance_end_real": 999.0,
                    "transactions": [
                        {
                            "name": "the only transaction in the file",
                            "date": "2026-01-01",
                            "amount": 100.0,
                            "unique_import_id": "mismatch-txn-1",
                        }
                    ],
                }
            ]
        )
        statement = self.env["account.bank.statement"].browse(statement_ids)
        self.assertEqual(statement.balance_end, 100.0)
        self.assertEqual(statement.balance_end_real, 999.0)
        self.assertFalse(statement.is_complete)
        self.assertTrue(statement.problem_description)

    def test_a_statement_that_adds_up_reports_no_problem(self):
        journal = self.company_data["default_journal_bank"]
        statement_ids, _ignored = journal._create_bank_statements(
            [
                {
                    "reference": "adds-up",
                    "balance_start": 0.0,
                    "balance_end_real": 100.0,
                    "transactions": [
                        {
                            "name": "the only transaction in the file",
                            "date": "2026-01-01",
                            "amount": 100.0,
                            "unique_import_id": "matching-txn-1",
                        }
                    ],
                }
            ]
        )
        statement = self.env["account.bank.statement"].browse(statement_ids)
        self.assertEqual(statement.balance_end, statement.balance_end_real)
        self.assertTrue(statement.is_complete)

    def test_import_bank_statement_aggregates_errors_across_attachments(self):
        journal = self.company_data["default_journal_bank"]
        good_attachment = self.env["ir.attachment"].create(
            {"name": "good.txt", "raw": b"good"}
        )
        bad_attachment = self.env["ir.attachment"].create(
            {"name": "bad.txt", "raw": b"bad"}
        )

        def fake_parse(self, raw_file):
            if raw_file == b"bad":
                raise UserError("boom")
            return [
                (
                    False,
                    False,
                    [
                        {
                            "reference": "good-ref",
                            "transactions": [
                                {
                                    "name": "line",
                                    "date": "2026-01-01",
                                    "amount": 10.0,
                                    "unique_import_id": "hub-agg-txn",
                                }
                            ],
                        }
                    ],
                )
            ]

        AccountJournal = type(self.env["account.journal"])
        with patch.object(AccountJournal, "_parse_bank_statement_file", fake_parse):
            action = journal._import_bank_statement(good_attachment + bad_attachment)

        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "warning")
        self.assertIn("bad.txt", action["params"]["message"])
        self.assertTrue(action["params"]["next"])
        self.assertTrue(
            self.env["account.bank.statement.line"].search_count(
                [("unique_import_id", "like", "hub-agg-txn")]
            )
        )

    def test_import_bank_statement_does_not_clobber_online_sync_source(self):
        journal = self.company_data["default_journal_bank"]
        journal.bank_statements_source = "online_sync"
        attachment = self.env["ir.attachment"].create(
            {"name": "statement.txt", "raw": b"good"}
        )

        def fake_parse(self, raw_file):
            return [
                (
                    False,
                    False,
                    [
                        {
                            "reference": "online-sync-ref",
                            "transactions": [
                                {
                                    "name": "line",
                                    "date": "2026-01-01",
                                    "amount": 10.0,
                                    "unique_import_id": "hub-online-sync-txn",
                                }
                            ],
                        }
                    ],
                )
            ]

        AccountJournal = type(self.env["account.journal"])
        with patch.object(AccountJournal, "_parse_bank_statement_file", fake_parse):
            journal._import_bank_statement(attachment)

        self.assertEqual(journal.bank_statements_source, "online_sync")

    def test_import_bank_statement_still_defaults_undefined_source(self):
        journal = self.company_data["default_journal_bank"]
        self.assertEqual(journal.bank_statements_source, "undefined")
        attachment = self.env["ir.attachment"].create(
            {"name": "statement.txt", "raw": b"good"}
        )

        def fake_parse(self, raw_file):
            return [
                (
                    False,
                    False,
                    [
                        {
                            "reference": "undefined-source-ref",
                            "transactions": [
                                {
                                    "name": "line",
                                    "date": "2026-01-01",
                                    "amount": 10.0,
                                    "unique_import_id": "hub-undefined-txn",
                                }
                            ],
                        }
                    ],
                )
            ]

        AccountJournal = type(self.env["account.journal"])
        with patch.object(AccountJournal, "_parse_bank_statement_file", fake_parse):
            journal._import_bank_statement(attachment)

        self.assertEqual(journal.bank_statements_source, "file_import")

    def test_parse_bank_statement_attachment_no_embedded_propagates_original(self):
        journal = self.company_data["default_journal_bank"]
        attachment = self.env["ir.attachment"].create(
            {"name": "statement.txt", "raw": b"orig"}
        )
        AccountJournal = type(self.env["account.journal"])

        def fake_parse(self, raw_file):
            raise UserError("original failure")

        with (
            patch.object(AccountJournal, "_parse_bank_statement_file", fake_parse),
            patch.object(
                AccountJournal,
                "_get_embedded_statement_files",
                lambda self, attachment: [],
            ),
        ):
            with self.assertRaises(UserError) as capture:
                journal._parse_bank_statement_attachment(attachment)
        self.assertEqual(capture.exception.args[0], "original failure")

    def test_parse_bank_statement_attachment_uses_first_successful_embedded(self):
        journal = self.company_data["default_journal_bank"]
        attachment = self.env["ir.attachment"].create(
            {"name": "statement.pdf", "raw": b"orig"}
        )
        AccountJournal = type(self.env["account.journal"])

        def fake_parse(self, raw_file):
            if raw_file == b"orig":
                raise UserError("original failure")
            if raw_file == b"embed_bad":
                raise UserError("embedded failure")
            if raw_file == b"embed_good":
                return "PARSED"
            raise AssertionError("unexpected raw_file: %r" % raw_file)

        with (
            patch.object(AccountJournal, "_parse_bank_statement_file", fake_parse),
            patch.object(
                AccountJournal,
                "_get_embedded_statement_files",
                lambda self, attachment: [b"embed_bad", b"embed_good"],
            ),
        ):
            result = journal._parse_bank_statement_attachment(attachment)
        self.assertEqual(result, "PARSED")

    def test_parse_bank_statement_attachment_all_embedded_fail_reraises_original(self):
        journal = self.company_data["default_journal_bank"]
        attachment = self.env["ir.attachment"].create(
            {"name": "statement.pdf", "raw": b"orig"}
        )
        AccountJournal = type(self.env["account.journal"])

        def fake_parse(self, raw_file):
            if raw_file == b"orig":
                raise UserError("original failure")
            raise UserError("embedded failure")

        with (
            patch.object(AccountJournal, "_parse_bank_statement_file", fake_parse),
            patch.object(
                AccountJournal,
                "_get_embedded_statement_files",
                lambda self, attachment: [b"embed_bad_1", b"embed_bad_2"],
            ),
        ):
            with self.assertRaises(UserError) as capture:
                journal._parse_bank_statement_attachment(attachment)
        self.assertEqual(capture.exception.args[0], "original failure")
