from odoo import Command
from odoo.tests import tagged

from .common_report_engine import TestAccountReportsCommon


@tagged("post_install", "-at_install")
class TestCurrencyTable(TestAccountReportsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_data["company"].write(
            {"name": "USD Company 1", "sequence": 1, "totals_below_sections": False}
        )
        cls.company_usd_data = cls.company_data
        cls.company_usd_data_2 = cls.setup_other_company(
            name="USD Company 2", sequence=2, currency_id=cls.env.ref("base.USD").id
        )
        cls.company_eur_data = cls.setup_other_company(
            name="EUR Company 1", sequence=3, currency_id=cls.env.ref("base.EUR").id
        )
        cls.company_eur_data_2 = cls.setup_other_company(
            name="EUR Company 2", sequence=4, currency_id=cls.env.ref("base.EUR").id
        )
        cls.company_chf_data = cls.setup_other_company(
            name="CHF Company", sequence=5, currency_id=cls.env.ref("base.CHF").id
        )
        cls.company_mxn_data = cls.setup_other_company(
            name="MXN Company", sequence=5, currency_id=cls.env.ref("base.MXN").id
        )

        for company_data in (
            cls.company_usd_data,
            cls.company_usd_data_2,
            cls.company_eur_data,
            cls.company_eur_data_2,
            cls.company_chf_data,
            cls.company_mxn_data,
        ):
            company_data["equity_account"] = cls.env["account.account"].search(
                [
                    ("company_ids", "=", company_data["company"].id),
                    ("account_type", "=", "equity"),
                ],
                limit=1,
            )

        cls.report = cls.env["report.formula"].create(
            {
                "name": "Currency Table Test",
                "filter_multi_company": "selector",
                "currency_translation": "cta",
                "column_ids": [
                    Command.create({"name": "Balance", "expression_label": "balance"})
                ],
                "line_ids": [
                    Command.create(
                        {
                            "name": "Asset",
                            "groupby": "company_id",
                            "expression_ids": [
                                Command.create(
                                    {
                                        "label": "balance",
                                        "engine": "domain",
                                        "formula": "[('account_id.internal_group', '=', 'asset')]",
                                        "subformula": "sum",
                                    }
                                ),
                            ],
                        }
                    ),
                    Command.create(
                        {
                            "name": "Income",
                            "groupby": "company_id",
                            "expression_ids": [
                                Command.create(
                                    {
                                        "label": "balance",
                                        "engine": "domain",
                                        "formula": "[('account_id.internal_group', '=', 'income')]",
                                        "subformula": "sum",
                                    }
                                ),
                            ],
                        }
                    ),
                    Command.create(
                        {
                            "name": "Equity",
                            "groupby": "company_id",
                            "expression_ids": [
                                Command.create(
                                    {
                                        "label": "balance",
                                        "engine": "domain",
                                        "formula": "[('account_id.internal_group', '=', 'equity')]",
                                        "subformula": "sum",
                                    }
                                ),
                            ],
                        }
                    ),
                ],
            }
        )

    def _generate_equity_move(self, company_data, date, amount):
        rslt = self.env["account.move"].create(
            {
                "company_id": company_data["company"].id,
                "date": date,
                "line_ids": [
                    Command.create(
                        {
                            "debit": 0,
                            "credit": amount,
                            "account_id": company_data["default_account_expense"].id,
                        }
                    ),
                    Command.create(
                        {
                            "debit": amount,
                            "credit": 0,
                            "account_id": company_data["equity_account"].id,
                        }
                    ),
                ],
            }
        )
        rslt.action_post()
        return rslt

    def test_currency_table_multicurrency(self):
        self.init_invoice(
            "out_invoice",
            company=self.company_usd_data["company"],
            invoice_date="2020-05-12",
            amounts=[10],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=self.company_usd_data_2["company"],
            invoice_date="2020-08-23",
            amounts=[25],
            post=True,
        )
        self._generate_equity_move(self.company_usd_data, "2020-11-11", 42)
        self._generate_equity_move(self.company_usd_data, "2020-12-01", 88)
        self._generate_equity_move(self.company_usd_data_2, "2020-02-01", 11)

        self.setup_other_currency(
            "EUR",
            rates=[
                ("2018-10-10", 7),
                ("2019-12-22", 11),
                ("2020-01-01", 2),
                ("2020-03-12", 5),
                ("2020-03-30", 20),
                ("2020-04-01", 4),
            ],
        )

        self.init_invoice(
            "out_invoice",
            company=self.company_eur_data["company"],
            invoice_date="2020-01-15",
            amounts=[23],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=self.company_eur_data["company"],
            invoice_date="2020-02-20",
            amounts=[64],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=self.company_eur_data["company"],
            invoice_date="2020-03-30",
            amounts=[100],
            post=True,
        )
        equity_unaffected_account = self.env["account.account"].search(
            [
                ("account_type", "=", "equity_unaffected"),
                *self.env["account.account"]._check_company_domain(
                    self.company_eur_data["company"]
                ),
            ],
            limit=1,
        )
        self.env["account.move"].create(
            {
                "date": "2020-02-15",
                "company_id": self.company_eur_data["company"].id,
                "line_ids": [
                    Command.create(
                        {"account_id": equity_unaffected_account.id, "debit": 100.0}
                    ),
                    Command.create(
                        {
                            "account_id": self.company_eur_data[
                                "default_account_receivable"
                            ].id,
                            "credit": 100.0,
                        }
                    ),
                ],
            },
        ).action_post()
        self._generate_equity_move(self.company_eur_data, "2020-03-15", 20)
        self._generate_equity_move(self.company_eur_data, "2020-03-31", 5)

        self.init_invoice(
            "out_invoice",
            company=self.company_eur_data_2["company"],
            invoice_date="2020-03-14",
            amounts=[54],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=self.company_eur_data_2["company"],
            invoice_date="2020-04-10",
            amounts=[77],
            post=True,
        )
        self._generate_equity_move(self.company_eur_data_2, "2020-05-21", 40)

        self.setup_other_currency(
            "CHF",
            rates=[
                ("2018-03-01", 10),
                ("2019-01-01", 3),
                ("2020-03-30", 7),
                ("2020-05-10", 8),
                ("2020-12-25", 2),
            ],
        )

        self.init_invoice(
            "out_invoice",
            company=self.company_chf_data["company"],
            invoice_date="2020-01-16",
            amounts=[58],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=self.company_chf_data["company"],
            invoice_date="2020-05-01",
            amounts=[99],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=self.company_chf_data["company"],
            invoice_date="2020-12-31",
            amounts=[22],
            post=True,
        )
        self._generate_equity_move(self.company_chf_data, "2020-03-15", 20)

        self.setup_other_currency("MXN", rates=[("2020-05-10", 2)])
        self.init_invoice(
            "out_invoice",
            company=self.company_mxn_data["company"],
            invoice_date="2020-01-01",
            amounts=[10],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=self.company_mxn_data["company"],
            invoice_date="2020-07-01",
            amounts=[21],
            post=True,
        )
        self._generate_equity_move(self.company_mxn_data, "2020-03-15", 2)

        self.report.currency_translation = "cta"
        cta_options_range = self._generate_options(
            self.report, "2019-12-22", "2020-12-31"
        )
        self.assertLinesValues(
            self.report._get_lines(cta_options_range),
            [0, 1],
            [
                ("Asset", 194.50),
                ("USD Company 1", 10.00),
                ("USD Company 2", 25.00),
                ("EUR Company 1", 21.75),
                ("EUR Company 2", 32.75),
                ("CHF Company", 89.50),
                ("MXN Company", 15.50),
                ("Income", -182.13),
                ("USD Company 1", -10.00),
                ("USD Company 2", -25.00),
                ("EUR Company 1", -54.14),
                ("EUR Company 2", -37.93),
                ("CHF Company", -33.79),
                ("MXN Company", -21.27),
                ("Equity", 192.87),
                ("USD Company 1", 130.00),
                ("USD Company 2", 11.00),
                ("EUR Company 1", 33.20),
                ("EUR Company 2", 10.00),
                ("CHF Company", 6.67),
                ("MXN Company", 2.00),
            ],
            cta_options_range,
        )

        self.report.currency_translation = "cta"
        self.report.filter_date_range = False
        cta_options_single = self._generate_options(
            self.report, "2020-12-31", "2020-12-31"
        )

        self.assertLinesValues(
            self.report._get_lines(cta_options_single),
            [0, 1],
            [
                ("Asset", 194.50),
                ("USD Company 1", 10.00),
                ("USD Company 2", 25.00),
                ("EUR Company 1", 21.75),
                ("EUR Company 2", 32.75),
                ("CHF Company", 89.50),
                ("MXN Company", 15.50),
                ("Income", -182.88),
                ("USD Company 1", -10.00),
                ("USD Company 2", -25.00),
                ("EUR Company 1", -55.15),
                ("EUR Company 2", -38.64),
                ("CHF Company", -33.09),
                ("MXN Company", -21.01),
                ("Equity", 193.41),
                ("USD Company 1", 130.00),
                ("USD Company 2", 11.00),
                ("EUR Company 1", 33.74),
                ("EUR Company 2", 10.00),
                ("CHF Company", 6.67),
                ("MXN Company", 2.00),
            ],
            cta_options_single,
        )

        current_expected_lines = [
            ("Asset", 194.50),
            ("USD Company 1", 10.00),
            ("USD Company 2", 25.00),
            ("EUR Company 1", 21.75),
            ("EUR Company 2", 32.75),
            ("CHF Company", 89.50),
            ("MXN Company", 15.50),
            ("Income", -219.50),
            ("USD Company 1", -10.00),
            ("USD Company 2", -25.00),
            ("EUR Company 1", -46.75),
            ("EUR Company 2", -32.75),
            ("CHF Company", -89.50),
            ("MXN Company", -15.50),
            ("Equity", 193.25),
            ("USD Company 1", 130.00),
            ("USD Company 2", 11.00),
            ("EUR Company 1", 31.25),
            ("EUR Company 2", 10.00),
            ("CHF Company", 10.00),
            ("MXN Company", 1.00),
        ]

        self.report.currency_translation = "current"

        current_options_range = self._generate_options(
            self.report, "2020-01-01", "2020-12-31"
        )
        self.assertLinesValues(
            self.report._get_lines(current_options_range),
            [0, 1],
            current_expected_lines,
            current_options_range,
        )

        self.report.filter_date_range = False
        current_options_single = self._generate_options(
            self.report, "2020-12-31", "2020-12-31"
        )
        self.assertLinesValues(
            self.report._get_lines(current_options_single),
            [0, 1],
            current_expected_lines,
            current_options_single,
        )

    def test_currency_table_monocurrency(self):
        self.init_invoice(
            "out_invoice",
            company=self.company_usd_data["company"],
            invoice_date="2020-01-01",
            amounts=[63],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=self.company_usd_data_2["company"],
            invoice_date="2020-01-01",
            amounts=[42],
            post=True,
        )
        self._generate_equity_move(self.company_usd_data, "2020-11-11", 88)
        self._generate_equity_move(self.company_usd_data_2, "2020-11-11", 92)

        companies = (
            self.company_usd_data["company"] + self.company_usd_data_2["company"]
        )
        self.env = self.env(
            context=dict(self.env.context, allowed_company_ids=companies.ids)
        )
        options = self._generate_options(self.report, "2020-01-01", "2020-12-31")
        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 1],
            [
                ("Asset", 105.00),
                ("USD Company 1", 63.00),
                ("USD Company 2", 42.00),
                ("Income", -105.00),
                ("USD Company 1", -63.00),
                ("USD Company 2", -42.00),
                ("Equity", 180.00),
                ("USD Company 1", 88.00),
                ("USD Company 2", 92.00),
            ],
            options,
        )

    def test_currency_table_comparison(self):
        self.setup_other_currency(
            "EUR",
            rates=[
                ("2018-01-01", 7),
                ("2019-01-01", 2),
                ("2020-03-12", 5),
                ("2021-03-30", 20),
                ("2022-04-01", 4),
            ],
        )

        self.init_invoice(
            "out_invoice",
            company=self.company_eur_data["company"],
            invoice_date="2019-01-01",
            amounts=[14],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=self.company_eur_data["company"],
            invoice_date="2020-01-01",
            amounts=[24],
            post=True,
        )
        self._generate_equity_move(self.company_eur_data, "2019-11-11", 55)
        self._generate_equity_move(self.company_eur_data, "2020-11-11", 99)

        self.setup_other_currency(
            "CHF",
            rates=[
                ("2018-01-01", 10),
                ("2019-01-01", 4),
                ("2019-03-12", 5),
                ("2021-03-30", 20),
                ("2022-04-01", 4),
            ],
        )

        self.init_invoice(
            "out_invoice",
            company=self.company_chf_data["company"],
            invoice_date="2019-01-01",
            amounts=[20],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=self.company_chf_data["company"],
            invoice_date="2020-01-01",
            amounts=[66],
            post=True,
        )
        self._generate_equity_move(self.company_chf_data, "2019-11-11", 12)
        self._generate_equity_move(self.company_chf_data, "2020-11-11", 84)

        options = self._generate_options(self.report, "2020-01-01", "2020-12-31")
        options = self._update_comparison_filter(
            options, self.report, "previous_period", 1
        )

        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 1, 2],
            [
                ("Asset", 18.00, 11.00),
                ("EUR Company 1", 4.80, 7.00),
                ("CHF Company", 13.20, 4.00),
                ("Income", -19.40, -11.19),
                ("EUR Company 1", -6.20, -7.00),
                ("CHF Company", -13.20, -4.19),
                ("Equity", 36.60, 29.90),
                ("EUR Company 1", 19.80, 27.50),
                ("CHF Company", 16.80, 2.40),
            ],
            options,
        )

    def test_currency_table_comparison_ascending_periods(self):
        self.setup_other_currency(
            "EUR",
            rates=[("2018-01-01", 7), ("2019-01-01", 2), ("2020-03-12", 5)],
        )
        self._generate_equity_move(self.company_eur_data, "2019-11-11", 55)
        self._generate_equity_move(self.company_eur_data, "2020-11-11", 99)

        options = self._generate_options(self.report, "2020-01-01", "2020-12-31")
        options = self._update_comparison_filter(
            options, self.report, "previous_period", 1, period_order="ascending"
        )

        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 1, 2],
            [
                ("Asset", 0.0, 0.0),
                ("Income", 0.0, 0.0),
                ("Equity", 27.50, 19.80),
                ("EUR Company 1", 27.50, 19.80),
            ],
            options,
        )

    def test_currency_table_external_value_with_comparisons(self):
        self.setup_other_currency("EUR", rates=[("2018-01-01", 2)])
        report = self.env["report.formula"].create(
            {
                "name": "External Currency Table Test",
                "filter_multi_company": "selector",
                "currency_translation": "current",
                "column_ids": [
                    Command.create({"name": "Balance", "expression_label": "balance"})
                ],
                "line_ids": [
                    Command.create(
                        {
                            "name": "Manual",
                            "expression_ids": [
                                Command.create(
                                    {
                                        "label": "balance",
                                        "engine": "external",
                                        "formula": "sum",
                                        "figure_type": "monetary",
                                        "date_scope": "strict_range",
                                    }
                                ),
                            ],
                        }
                    ),
                ],
            }
        )
        self.env["report.formula.external.value"].create(
            {
                "name": "Manual value",
                "value": 100.0,
                "date": "2020-06-01",
                "target_report_expression_id": report.line_ids.expression_ids.id,
                "company_id": self.company_eur_data["company"].id,
            }
        )

        options = self._generate_options(report, "2020-01-01", "2020-12-31")
        options = self._update_comparison_filter(options, report, "previous_period", 2)

        self.assertLinesValues(
            report._get_lines(options),
            [0, 1, 2, 3],
            [("Manual", 50.0, 0.0, 0.0)],
            options,
        )

    def test_currency_table_account_codes_balance_character_rounds_half_away_from_zero(
        self,
    ):
        self.setup_other_currency("EUR", rates=[("2018-01-01", 2)])
        eur_company = self.company_eur_data["company"]
        expense_code = (
            self.company_eur_data["default_account_expense"]
            .with_company(eur_company)
            .code
        )
        report = self.env["report.formula"].create(
            {
                "name": "Balance Character Rounding Test",
                "filter_multi_company": "selector",
                "currency_translation": "current",
                "column_ids": [
                    Command.create({"name": "Balance", "expression_label": "balance"})
                ],
                "line_ids": [
                    Command.create(
                        {
                            "name": name,
                            "expression_ids": [
                                Command.create(
                                    {
                                        "label": "balance",
                                        "engine": "account_codes",
                                        "formula": f"{expense_code}{balance_character}",
                                    }
                                ),
                            ],
                        }
                    )
                    for name, balance_character in (("Credit", "C"), ("Debit", "D"))
                ],
            }
        )
        self._generate_equity_move(self.company_eur_data, "2020-06-01", 0.01)

        options = self._generate_options(report, "2020-01-01", "2020-12-31")
        self.assertEqual(
            [
                (line["name"], line["columns"][0]["no_format"])
                for line in report._get_lines(options)
            ],
            [("Credit", -0.005), ("Debit", 0.0)],
        )

    def test_currency_table_branches(self):
        usd_branch_data = self.setup_other_company(
            name="USD Branch",
            parent_id=self.company_usd_data["company"].id,
            sequence=self.company_usd_data["company"].sequence,
        )

        eur_branch_data = self.setup_other_company(
            name="EUR Branch",
            parent_id=self.company_eur_data["company"].id,
            sequence=self.company_eur_data["company"].sequence,
        )

        usd_branch_data["company"].account_config_id.totals_below_sections = False

        usd_branch_data["equity_account"] = self.company_usd_data["equity_account"]
        eur_branch_data["equity_account"] = self.company_eur_data["equity_account"]

        self.setup_other_currency(
            "EUR", rates=[("2020-01-01", 4), ("2020-03-01", 2), ("2020-12-01", 5)]
        )

        self.init_invoice(
            "out_invoice",
            company=self.company_usd_data["company"],
            invoice_date="2020-11-01",
            amounts=[10],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=usd_branch_data["company"],
            invoice_date="2020-09-01",
            amounts=[20],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=self.company_eur_data["company"],
            invoice_date="2020-06-25",
            amounts=[30],
            post=True,
        )
        self.init_invoice(
            "out_invoice",
            company=eur_branch_data["company"],
            invoice_date="2020-02-23",
            amounts=[40],
            post=True,
        )

        self._generate_equity_move(self.company_usd_data, "2020-11-12", 50)
        self._generate_equity_move(usd_branch_data, "2020-01-21", 60)
        self._generate_equity_move(self.company_eur_data, "2020-05-12", 70)
        self._generate_equity_move(eur_branch_data, "2020-09-09", 80)

        companies = (
            usd_branch_data["company"]
            + eur_branch_data["company"]
            + self.company_usd_data["company"]
            + self.company_eur_data["company"]
        )
        self.env = self.env(
            context=dict(self.env.context, allowed_company_ids=companies.ids)
        )
        self.report = self.report.with_env(self.env)

        options = self._generate_options(self.report, "2020-01-01", "2020-12-31")
        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 1],
            [
                ("Asset", 44.00),
                ("USD Branch", 20.00),
                ("USD Company 1", 10.00),
                ("EUR Branch", 8.00),
                ("EUR Company 1", 6.00),
                ("Income", -60.35),
                ("USD Branch", -20.00),
                ("USD Company 1", -10.00),
                ("EUR Branch", -17.34),
                ("EUR Company 1", -13.01),
                ("Equity", 185.00),
                ("USD Branch", 60.00),
                ("USD Company 1", 50.00),
                ("EUR Branch", 40.00),
                ("EUR Company 1", 35.00),
            ],
            options,
        )

    def test_currency_table_no_rate(self):
        self.init_invoice(
            "out_invoice",
            company=self.company_usd_data["company"],
            invoice_date="2020-11-01",
            amounts=[10],
            post=True,
        )
        self._generate_equity_move(self.company_usd_data, "2020-11-12", 20)
        self.init_invoice(
            "out_invoice",
            company=self.company_eur_data["company"],
            invoice_date="2020-02-23",
            amounts=[30],
            post=True,
        )
        self._generate_equity_move(self.company_eur_data, "2020-05-12", 40)

        options = self._generate_options(self.report, "2020-01-01", "2020-12-31")
        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 1],
            [
                ("Asset", 40.00),
                ("USD Company 1", 10.00),
                ("EUR Company 1", 30.00),
                ("Income", -40.00),
                ("USD Company 1", -10.00),
                ("EUR Company 1", -30.00),
                ("Equity", 60.00),
                ("USD Company 1", 20.00),
                ("EUR Company 1", 40.00),
            ],
            options,
        )

    def test_currency_table_non_1_domestic_rate(self):
        self.setup_other_currency("USD", rates=[("2020-01-01", 0.5)])
        self.setup_other_currency(
            "EUR", rates=[("2020-01-01", 4), ("2020-03-01", 2), ("2020-12-01", 5)]
        )

        self.init_invoice(
            "out_invoice",
            company=self.company_usd_data["company"],
            invoice_date="2020-11-01",
            amounts=[10],
            post=True,
        )
        self._generate_equity_move(self.company_usd_data, "2020-11-12", 20)

        self.init_invoice(
            "out_invoice",
            company=self.company_eur_data["company"],
            invoice_date="2020-02-23",
            amounts=[30],
            post=True,
        )
        self._generate_equity_move(self.company_eur_data, "2020-05-12", 40)

        options = self._generate_options(self.report, "2020-01-01", "2020-12-31")
        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 1],
            [
                ("Asset", 13.00),
                ("USD Company 1", 10.00),
                ("EUR Company 1", 3.00),
                ("Income", -16.50),
                ("USD Company 1", -10.00),
                ("EUR Company 1", -6.50),
                ("Equity", 30.00),
                ("USD Company 1", 20.00),
                ("EUR Company 1", 10.00),
            ],
            options,
        )

    def test_currency_manual_line_expansion(self):
        self.setup_other_currency("EUR", rates=[("2020-01-01", 2)])
        self.init_invoice(
            "out_invoice",
            company=self.company_eur_data["company"],
            invoice_date="2020-12-22",
            amounts=[42],
            post=True,
        )

        self.report.line_ids.foldable = True

        options = self._generate_options(self.report, "2020-01-01", "2020-12-31")
        line_to_expand_id = self.report._get_generic_line_id(
            "report.formula.line", self.report.line_ids[0].id
        )
        self.assertLinesValues(
            self.report.get_expanded_lines(
                options,
                line_to_expand_id,
                "company_id",
                "_report_expand_unfoldable_line_with_groupby",
                0,
                0,
                None,
            ),
            [0, 1],
            [
                ("EUR Company 1", 21.00),
            ],
            options,
        )
