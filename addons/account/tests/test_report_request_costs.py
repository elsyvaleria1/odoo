import copy
import datetime
from unittest.mock import patch

import odoo.tools.formatting
from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.models.account_aged_partner_balance import (
    AccountAgedPartnerBalanceReportHandler,
)
from odoo.addons.account.models.account_general_ledger import (
    AccountGeneralLedgerReportHandler,
)
from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon


@tagged("post_install", "-at_install")
class TestReportRequestCosts(TestAccountReportsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(cls.env.context, allowed_company_ids=cls.env.company.ids)
        )
        cls.revenue = cls.company_data["default_account_revenue"]
        cls.receivable = cls.company_data["default_account_receivable"]
        cls._post_entry("2016-06-01", [100.0])
        cls._post_entry("2017-03-01", [10.0, 20.0, 30.0, 40.0, 50.0])

    @classmethod
    def _post_entry(cls, date, revenue_amounts, journal=None):
        move = cls.env["account.move"].create(
            {
                "move_type": "entry",
                "date": date,
                "journal_id": (journal or cls.company_data["default_journal_misc"]).id,
                "line_ids": [
                    Command.create(
                        {
                            "name": f"revenue {amount}",
                            "account_id": cls.revenue.id,
                            "credit": amount,
                        }
                    )
                    for amount in revenue_amounts
                ]
                + [
                    Command.create(
                        {
                            "name": "receivable",
                            "account_id": cls.receivable.id,
                            "partner_id": cls.partner_a.id,
                            "debit": sum(revenue_amounts),
                        }
                    )
                ],
            }
        )
        move.action_post()
        return move

    def _aged_scans(self, queries):
        return [query for query in queries if "period_table" in query]

    def test_general_ledger_unfold_all_reads_one_page_per_account(self):
        report = self.env.ref("account.general_ledger_report")
        report.load_more_limit = 2
        options = self._generate_options(report, "2017-01-01", "2017-12-31")
        account_line_id = report._get_generic_line_id(
            "account.account",
            self.revenue.id,
            markup={"groupby": "account_id"},
            parent_line_id=report._get_generic_line_id(
                "report.formula.line",
                self.env.ref("account.general_ledger_custom_engine_line").id,
            ),
        )
        paged_lines = report._get_lines(
            {**options, "unfolded_lines": [account_line_id]}
        )

        handed_rows = {}
        engine_rows = AccountGeneralLedgerReportHandler._get_unfold_all_engine_rows

        def spy(handler, *args, **kwargs):
            for key, rows in engine_rows(handler, *args, **kwargs):
                handed_rows[key] = len(rows)
                yield key, rows

        with patch.object(
            AccountGeneralLedgerReportHandler, "_get_unfold_all_engine_rows", spy
        ):
            unfolded_lines = report._get_lines({**options, "unfold_all": True})

        revenue_key = next(
            key
            for key in handed_rows
            if key.endswith(
                f"account_id:{self.revenue.id}=>id_with_accumulated_balance"
            )
        )
        self.assertEqual(handed_rows[revenue_key], 3)

        def revenue_page(lines):
            return [
                (line["name"], [column.get("no_format") for column in line["columns"]])
                for line in lines
                if line.get("parent_id") == account_line_id
            ]

        self.assertEqual(revenue_page(unfolded_lines), revenue_page(paged_lines))
        self.assertEqual(revenue_page(unfolded_lines)[2][0], "Load more...")

    def test_aged_receivable_scans_its_lines_once(self):
        report = self.env.ref("account.aged_receivable_report")
        options = self._generate_options(report, "2017-12-31", "2017-12-31")
        for unfold_all in (False, True):
            with self.subTest(unfold_all=unfold_all):
                self.env.invalidate_all()
                with self.capturedQueries() as queries:
                    lines = report._get_lines({**options, "unfold_all": unfold_all})
                self.assertEqual(len(self._aged_scans(queries)), 1)
                with patch.object(
                    AccountAgedPartnerBalanceReportHandler,
                    "_get_aged_expansion_groupby",
                    lambda *args: None,
                ):
                    separate_scans = report._get_lines(
                        {**options, "unfold_all": unfold_all}
                    )
                self.assertEqual(lines, separate_scans)
                self.assertFalse(
                    [key for key in self.env.cr.cache if "account.aged" in str(key)]
                )

    def test_journal_report_unfold_all_reads_every_journal_at_once(self):
        report = self.env.ref("account.journal_report")
        self._post_entry(
            "2017-04-01", [7.0], journal=self.company_data["default_journal_sale"]
        )
        options = self._generate_options(report, "2017-01-01", "2017-12-31")
        handler = self.env[report.custom_handler_model_name]
        with patch.object(
            type(handler), "_custom_unfold_all_batch_data_generator", lambda *a: {}
        ):
            journal_by_journal = report._get_lines({**options, "unfold_all": True})
        with self.capturedQueries() as queries:
            batched = report._get_lines({**options, "unfold_all": True})

        self.assertEqual(batched, journal_by_journal)
        grouped_by_account = [
            query
            for query in queries
            if "AS grouping_key" in query and "journal_code" in query
        ]
        self.assertEqual(len(grouped_by_account), 2)

    def test_journal_tax_summaries_read_every_journal_at_once(self):
        report = self.env.ref("account.journal_report")
        self.init_invoice(
            "out_invoice",
            self.partner_a,
            "2017-05-01",
            amounts=[100.0],
            taxes=self.tax_sale_a,
            post=True,
        )
        self.init_invoice(
            "in_invoice",
            self.partner_a,
            "2017-05-02",
            amounts=[80.0],
            taxes=self.tax_purchase_a,
            post=True,
        )
        options = self._generate_options(report, "2017-01-01", "2017-12-31")

        with patch.object(
            type(self.env["report.formula"]),
            "_get_column_group_partition",
            lambda *args: None,
        ):
            journal_by_journal = report._get_lines({**options, "unfold_all": True})
        with self.capturedQueries() as queries:
            partitioned = report._get_lines({**options, "unfold_all": True})

        self.assertEqual(partitioned, journal_by_journal)
        summaries = [line for line in partitioned if line.get("is_tax_section_line")]
        self.assertEqual(len(summaries), 3)
        base_amount_reads = [
            query
            for query in queries
            if "account_move_line_account_tax_rel tax_rel" in query
        ]
        self.assertEqual(len(base_amount_reads), 1)

    def test_fiscal_year_bounds_of_all_companies_take_one_query(self):
        company, company_2 = (
            self.company_data["company"],
            self.company_data_2["company"],
        )
        self.env = self.env(
            context=dict(
                self.env.context, allowed_company_ids=[company.id, company_2.id]
            )
        )
        fiscal_years = self.env["account.fiscal.year"].create(
            [
                {
                    "name": "Short year",
                    "date_from": "2016-07-01",
                    "date_to": "2017-02-28",
                    "company_id": company.id,
                },
                {
                    "name": "Half year",
                    "date_from": "2017-01-01",
                    "date_to": "2017-06-30",
                    "company_id": company_2.id,
                },
            ]
        )
        half_year = fiscal_years[1]
        company, company_2 = company.with_env(self.env), company_2.with_env(self.env)
        companies = company | company_2
        companies._compute_fiscalyear_dates_by_company(datetime.date(2016, 6, 1))
        self.env.invalidate_all()
        with self.assertQueryCount(3):
            bounds = companies._compute_fiscalyear_dates_by_company(
                datetime.date(2017, 6, 1)
            )
        self.assertEqual(
            bounds,
            {
                company.id: {
                    "date_from": datetime.date(2017, 3, 1),
                    "date_to": datetime.date(2017, 12, 31),
                },
                company_2.id: {
                    "date_from": datetime.date(2017, 1, 1),
                    "date_to": datetime.date(2017, 6, 30),
                    "record": half_year,
                },
            },
        )

    def test_formatting_resolves_the_language_once_per_pass(self):
        report = self.env.ref("account.general_ledger_report")
        options = self._generate_options(report, "2017-01-01", "2017-12-31")
        lines = report._get_lines({**options, "unfold_all": True})
        expected = copy.deepcopy(lines)
        report._format_column_values(options, expected, force_format=True)

        with patch.object(
            odoo.tools.formatting, "get_lang", wraps=odoo.tools.formatting.get_lang
        ) as language_lookup:
            report._format_column_values(options, lines, force_format=True)

        monetary_cells = [
            column
            for line in lines
            for column in line["columns"]
            if column.get("figure_type") == "monetary"
        ]
        self.assertGreater(len(monetary_cells), 5)
        self.assertEqual(language_lookup.call_count, 0)
        self.assertEqual(lines, expected)
