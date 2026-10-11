from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged

from .common_report_engine import TestAccountReportsCommon


@tagged("post_install", "-at_install")
class TestJournalReport(TestAccountReportsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.report = cls.env.ref("account.journal_report")


        cls.default_bank_journal = cls.company_data["default_journal_bank"]
        cls.default_sale_journal = cls.company_data["default_journal_sale"]

        cls.liquidity_account = cls.default_bank_journal.default_account_id
        cls.move_bank_0 = cls.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2016-01-01",
                "journal_id": cls.company_data["default_journal_bank"].id,
                "line_ids": [
                    Command.create(
                        {
                            "debit": 100.0,
                            "credit": 0.0,
                            "name": "2016_1_1",
                            "account_id": cls.liquidity_account.id,
                        }
                    ),
                    Command.create(
                        {
                            "debit": 0.0,
                            "credit": 100.0,
                            "name": "2016_1_2",
                            "account_id": cls.company_data[
                                "default_account_revenue"
                            ].id,
                        }
                    ),
                ],
            }
        )
        cls.move_bank_0.action_post()

        cls.move_bank_1 = cls.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2017-01-01",
                "journal_id": cls.company_data["default_journal_bank"].id,
                "line_ids": [
                    Command.create(
                        {
                            "debit": 200.0,
                            "credit": 0.0,
                            "name": "2017_1_1",
                            "account_id": cls.liquidity_account.id,
                        }
                    ),
                    Command.create(
                        {
                            "debit": 0.0,
                            "credit": 200.0,
                            "name": "2017_1_2",
                            "account_id": cls.company_data[
                                "default_account_revenue"
                            ].id,
                        }
                    ),
                ],
            }
        )
        cls.move_bank_1.action_post()


        cls.move_sales_0 = cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": cls.partner_a.id,
                "invoice_date": "2017-01-01",
                "journal_id": cls.company_data["default_journal_sale"].id,
                "payment_reference": "ref123",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "quantity": 1,
                            "price_unit": 3000.0,
                            "account_id": cls.company_data[
                                "default_account_revenue"
                            ].id,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        cls.move_sales_0.action_post()

        cls.other_currency = cls.setup_other_currency(
            "EUR", rounding=0.001, rates=[("2016-01-01", 2.0), ("2017-01-01", 2.0)]
        )

        cls.move_sales_1 = cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": cls.partner_a.id,
                "invoice_date": "2017-01-01",
                "journal_id": cls.company_data["default_journal_sale"].id,
                "currency_id": cls.other_currency.id,
                "payment_reference": "ref234",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "quantity": 1,
                            "price_unit": 3000.0,
                            "account_id": cls.company_data[
                                "default_account_revenue"
                            ].id,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        cls.move_sales_1.action_post()

        cls.move_sales_2 = cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": cls.partner_a.id,
                "invoice_date": "2017-01-01",
                "journal_id": cls.company_data["default_journal_sale"].id,
                "currency_id": cls.other_currency.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "quantity": 1,
                            "price_unit": 2000.0,
                            "account_id": cls.company_data[
                                "default_account_revenue"
                            ].id,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        cls.move_sales_2.action_post()
        cls.move_sales_2.payment_reference = ""

        cls.company_data["company"].country_id = cls.env.ref("base.us")
        cls.tax_report = cls.env["report.formula"].create(
            {
                "name": "Tax report",
                "root_report_id": cls.env.ref("account.generic_tax_report").id,
                "country_id": cls.company_data["company"].country_id.id,
                "allow_foreign_vat": True,
                "availability_condition": "country",
                "column_ids": [
                    Command.create(
                        {
                            "name": "Balance",
                            "expression_label": "balance",
                            "sequence": 1,
                        }
                    )
                ],
                "line_ids": [
                    Command.create(
                        {
                            "name": "10%",
                            "code": "c10",
                            "sequence": 1,
                            "expression_ids": [
                                Command.create(
                                    {
                                        "label": "balance",
                                        "engine": "tax_tags",
                                        "formula": "-c10",
                                    }
                                )
                            ],
                        }
                    )
                ],
            }
        )
        cls.test_tax = cls.env["account.tax"].create(
            {
                "name": "Tax 10%",
                "amount": 10.0,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "invoice_repartition_line_ids": [
                    Command.create({"repartition_type": "base"}),
                    Command.create(
                        {
                            "repartition_type": "tax",
                            "tag_ids": [
                                Command.link(
                                    cls.tax_report.line_ids.expression_ids._get_matching_tags().id
                                )
                            ],
                        }
                    ),
                ],
            }
        )
        cls.move_sales_3 = cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": cls.partner_a.id,
                "invoice_date": "2017-01-01",
                "payment_reference": "ref345",
                "journal_id": cls.company_data["default_journal_sale"].id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "quantity": 1,
                            "price_unit": 1500.0,
                            "account_id": cls.company_data[
                                "default_account_revenue"
                            ].id,
                            "tax_ids": [cls.test_tax.id],
                        }
                    )
                ],
            }
        )
        cls.move_sales_3.action_post()

        cls.move_payment_0 = cls.env["account.payment"].create(
            {
                "amount": 370,
                "partner_id": cls.partner_a.id,
                "payment_reference": "PBNK1/2017/00000001",
                "payment_type": "inbound",
                "destination_account_id": cls.company_data[
                    "default_account_revenue"
                ].id,
                "date": "2017-01-01",
            }
        )
        cls.move_payment_0.action_post()

    def _filter_tax_section_lines(self, lines, exclude):
        def filter_condition(line):
            markup = self.report._get_markup(line["id"])
            return exclude ^ (
                isinstance(markup, str) and markup.startswith("tax_report_section")
            )

        return list(filter(filter_condition, lines))

    def assert_journal_vals_for_export(
        self, report, options, actual_journal_vals, expected_journals_data
    ):
        self.assertEqual(len(actual_journal_vals), len(expected_journals_data))
        for actual_item, expected_item in zip(
            actual_journal_vals, expected_journals_data, strict=False
        ):
            if "columns" in expected_item:
                self.assertEqual(
                    expected_item["columns"],
                    [col["label"] for col in actual_item["columns"]],
                )

            if "lines" in expected_item:
                self.assertEqual(len(expected_item["lines"]), len(actual_item["lines"]))
                for expected_line, actual_line in zip(
                    expected_item["lines"], actual_item["lines"], strict=False
                ):
                    self.assertDictEqual(
                        expected_line,
                        {
                            expected_key: actual_line.get(expected_key, {}).get("data")
                            for expected_key in expected_line
                        },
                    )

    def test_journal_lines(self):
        options_2016 = self._generate_options(
            self.report,
            "2016-01-01",
            "2016-01-31",
            default_options={"unfold_all": True, "show_payment_lines": False},
        )
        lines_2016 = self.report._get_lines(options_2016)
        self.assertLinesValues(
            self._filter_tax_section_lines(lines_2016, True),
            [1, 4, 5, 6],
            [
                ("", "", "", ""),
                ("BNK1", 100, 100, ""),
                ("101401", 100, 0, 100),
                ("400000", 0, 100, -100),
            ],
            options_2016,
        )
        tax_summary_lines_2016 = self._filter_tax_section_lines(lines_2016, False)
        self.assertFalse(tax_summary_lines_2016)

        options_2017 = self._generate_options(
            self.report,
            "2017-01-01",
            "2017-01-31",
            default_options={"unfold_all": True, "show_payment_lines": False},
        )
        lines_2017 = self.report._get_lines(options_2017)
        self.assertLinesValues(
            self._filter_tax_section_lines(lines_2017, True),
            [1, 4, 5, 6],
            [
                ("", "", "", ""),
                ("INV", 7150, 7150, ""),
                ("121000", 7150, 0, 7150),
                ("400000", 0, 7150, -7150),
                ("BNK1", 200, 200, ""),
                ("101401", 200, 0, 200),
                ("400000", 0, 200, -200),
            ],
            options_2017,
        )
        tax_summary_lines_2017 = self._filter_tax_section_lines(lines_2017, False)
        tax_tag = self.tax_report.line_ids.expression_ids._get_matching_tags()
        self.assertDictEqual(
            tax_summary_lines_2017[0]["tax_grid_summary_lines"],
            {
                "US": {
                    "c10": {
                        "tag_ids": tax_tag.ids,
                        "balance": "$\xa0150.00",
                        "balance_no_format": 150.0,
                        "+": "$\xa0150.00",
                        "+_no_format": 150.0,
                        "-": "$\xa00.00",
                        "-_no_format": 0.0,
                        "impact": "$\xa0150.00",
                    }
                }
            },
        )
        self.assertEqual(tax_summary_lines_2017[1]["name"], "Global Tax Summary")
        self.assertDictEqual(
            tax_summary_lines_2017[2]["tax_grid_summary_lines"],
            {
                "US": {
                    "c10": {
                        "tag_ids": tax_tag.ids,
                        "balance": "$\xa0150.00",
                        "balance_no_format": 150.0,
                        "+": "$\xa0150.00",
                        "+_no_format": 150.0,
                        "-": "$\xa00.00",
                        "-_no_format": 0.0,
                        "impact": "$\xa0150.00",
                    }
                }
            },
        )

        options_global = self._generate_options(
            self.report,
            "2016-01-01",
            "2017-01-31",
            default_options={"unfold_all": True, "show_payment_lines": False},
        )
        lines_global = self.report._get_lines(options_global)
        self.assertLinesValues(
            self._filter_tax_section_lines(lines_global, True),
            [1, 4, 5, 6],
            [
                ("", "", "", ""),
                ("INV", 7150, 7150, ""),
                ("121000", 7150, 0, 7150),
                ("400000", 0, 7150, -7150),
                ("BNK1", 300, 300, ""),
                ("101401", 300, 0, 300),
                ("400000", 0, 300, -300),
            ],
            options_global,
        )
        tax_summary_lines_global = self._filter_tax_section_lines(lines_global, False)
        self.assertDictEqual(
            tax_summary_lines_global[0]["tax_grid_summary_lines"],
            {
                "US": {
                    "c10": {
                        "tag_ids": tax_tag.ids,
                        "balance": "$\xa0150.00",
                        "balance_no_format": 150.0,
                        "+": "$\xa0150.00",
                        "+_no_format": 150.0,
                        "-": "$\xa00.00",
                        "-_no_format": 0.0,
                        "impact": "$\xa0150.00",
                    }
                }
            },
        )
        self.assertEqual(tax_summary_lines_global[1]["name"], "Global Tax Summary")
        self.assertDictEqual(
            tax_summary_lines_global[2]["tax_grid_summary_lines"],
            {
                "US": {
                    "c10": {
                        "tag_ids": tax_tag.ids,
                        "balance": "$\xa0150.00",
                        "balance_no_format": 150.0,
                        "+": "$\xa0150.00",
                        "+_no_format": 150.0,
                        "-": "$\xa00.00",
                        "-_no_format": 0.0,
                        "impact": "$\xa0150.00",
                    }
                }
            },
        )

    def test_show_payment_lines_option(self):
        options_no_payment = self._generate_options(
            self.report,
            "2017-01-01",
            "2017-01-31",
            default_options={"unfold_all": True, "show_payment_lines": False},
        )
        outstanding_account_code = (
            self.env["account.payment"]
            ._get_outstanding_account(payment_type="inbound")
            .code
        )

        self.assertLinesValues(
            self._filter_tax_section_lines(
                self.report._get_lines(options_no_payment), True
            ),
            [1, 4, 5, 6],
            [
                ("", "", "", ""),
                ("INV", 7150, 7150, ""),
                ("121000", 7150, 0, 7150),
                ("400000", 0, 7150, -7150),
                ("BNK1", 200, 200, ""),
                ("101401", 200, 0, 200),
                ("400000", 0, 200, -200),
            ],
            options_no_payment,
        )

        options_show_payment = self._generate_options(
            self.report,
            "2017-01-01",
            "2017-01-31",
            default_options={"unfold_all": True, "show_payment_lines": True},
        )
        self.assertLinesValues(
            self._filter_tax_section_lines(
                self.report._get_lines(options_show_payment), True
            ),
            [1, 4, 5, 6],
            [
                ("", "", "", ""),
                ("INV", 7150, 7150, ""),
                ("121000", 7150, 0, 7150),
                ("400000", 0, 7150, -7150),
                ("BNK1", 570, 570, ""),
                ("101401", 200, 0, 200),
                (outstanding_account_code, 370, 0, 370),
                ("400000", 0, 570, -570),
            ],
            options_show_payment,
        )

    def test_document_data_basic(self):
        options = self._generate_options(
            self.report,
            "2017-01-01",
            "2017-01-31",
            default_options={"show_payment_lines": False},
        )

        journal_report_handler = self.env[self.report.custom_handler_model_name]
        move_2_pref = self.move_sales_2.payment_reference
        self.assert_journal_vals_for_export(
            self.report,
            options,
            journal_report_handler._generate_document_data_for_export(
                self.report, options, "pdf"
            )["journals_vals"],
            [
                {
                    "id": self.default_sale_journal.id,
                    "columns": [
                        "document",
                        "account_label",
                        "name",
                        "debit",
                        "credit",
                        "taxes",
                        "tax_grids",
                    ],
                    "lines": [
                        {
                            "name": "partner_a ref123",
                            "debit": "$\xa03,000.00",
                            "credit": "$\xa00.00",
                        },
                        {
                            "name": "ref123",
                            "debit": "$\xa00.00",
                            "credit": "$\xa03,000.00",
                        },
                        {
                            "name": "partner_a ref234",
                            "debit": "$\xa01,500.00",
                            "credit": "$\xa00.00",
                        },
                        {
                            "name": "ref234",
                            "debit": "$\xa00.00",
                            "credit": "$\xa01,500.00",
                        },
                        {
                            "currency_id": self.other_currency.id,
                            "amount": 3000,
                        },
                        {
                            "name": f"partner_a {move_2_pref}",
                            "debit": "$\xa01,000.00",
                            "credit": "$\xa00.00",
                        },
                        {
                            "name": move_2_pref,
                            "debit": "$\xa00.00",
                            "credit": "$\xa01,000.00",
                        },
                        {
                            "currency_id": self.other_currency.id,
                            "amount": 2000,
                        },
                        {
                            "name": "partner_a ref345",
                            "debit": "$\xa01,650.00",
                            "credit": "$\xa00.00",
                        },
                        {
                            "name": "ref345",
                            "debit": "$\xa00.00",
                            "credit": "$\xa01,500.00",
                            "taxes": "T: Tax 10%",
                        },
                        {
                            "name": "Tax 10%",
                            "debit": "$\xa00.00",
                            "credit": "$\xa0150.00",
                            "taxes": "B: $\xa0-\ufeff1,500.00",
                        },
                        {},
                        {
                            "name": "Total",
                            "debit": "$\xa07,150.00",
                            "credit": "$\xa07,150.00",
                        },
                    ],
                },
                {
                    "id": self.default_bank_journal.id,
                    "columns": [
                        "document",
                        "account_label",
                        "name",
                        "debit",
                        "credit",
                        "balance",
                    ],
                    "lines": [
                        {"name": "Starting Balance", "balance": "$\xa0100.00"},
                        {
                            "name": "2017_1_2",
                            "debit": "$\xa00.00",
                            "credit": "$\xa0200.00",
                            "balance": "$\xa0300.00",
                        },
                        {},
                        {
                            "name": "Total",
                            "debit": None,
                            "credit": None,
                            "balance": "$\xa0300.00",
                        },
                    ],
                },
            ],
        )

    def test_document_data_for_bank_journal_with_show_payment_option(self):
        options = self._generate_options(
            self.report,
            "2017-01-01",
            "2017-01-31",
            default_options={"show_payment_lines": True},
        )
        journal_report_handler = self.env[self.report.custom_handler_model_name]
        move_2_pref = self.move_sales_2.payment_reference
        self.assert_journal_vals_for_export(
            self.report,
            options,
            journal_report_handler._generate_document_data_for_export(
                self.report, options, "pdf"
            )["journals_vals"],
            [
                {
                    "id": self.default_sale_journal.id,
                    "columns": [
                        "document",
                        "account_label",
                        "name",
                        "debit",
                        "credit",
                        "taxes",
                        "tax_grids",
                    ],
                    "lines": [
                        {
                            "name": "partner_a ref123",
                            "debit": "$\xa03,000.00",
                            "credit": "$\xa00.00",
                        },
                        {
                            "name": "ref123",
                            "debit": "$\xa00.00",
                            "credit": "$\xa03,000.00",
                        },
                        {
                            "name": "partner_a ref234",
                            "debit": "$\xa01,500.00",
                            "credit": "$\xa00.00",
                        },
                        {
                            "name": "ref234",
                            "debit": "$\xa00.00",
                            "credit": "$\xa01,500.00",
                        },
                        {
                            "currency_id": self.other_currency.id,
                            "amount": 3000,
                        },
                        {
                            "name": f"partner_a {move_2_pref}",
                            "debit": "$\xa01,000.00",
                            "credit": "$\xa00.00",
                        },
                        {
                            "name": move_2_pref,
                            "debit": "$\xa00.00",
                            "credit": "$\xa01,000.00",
                        },
                        {
                            "currency_id": self.other_currency.id,
                            "amount": 2000,
                        },
                        {
                            "name": "partner_a ref345",
                            "debit": "$\xa01,650.00",
                            "credit": "$\xa00.00",
                        },
                        {
                            "name": "ref345",
                            "debit": "$\xa00.00",
                            "credit": "$\xa01,500.00",
                            "taxes": "T: Tax 10%",
                        },
                        {
                            "name": "Tax 10%",
                            "debit": "$\xa00.00",
                            "credit": "$\xa0150.00",
                            "taxes": "B: $\xa0-\ufeff1,500.00",
                        },
                        {},
                        {
                            "name": "Total",
                            "debit": "$\xa07,150.00",
                            "credit": "$\xa07,150.00",
                        },
                    ],
                },
                {
                    "id": self.default_bank_journal.id,
                    "columns": [
                        "document",
                        "account_label",
                        "name",
                        "debit",
                        "credit",
                        "balance",
                    ],
                    "lines": [
                        {"name": "Starting Balance", "balance": "$\xa0100.00"},
                        {
                            "name": "2017_1_2",
                            "debit": "$\xa00.00",
                            "credit": "$\xa0200.00",
                            "balance": "$\xa0300.00",
                        },
                        {
                            "name": "Manual Payment",
                            "debit": "$\xa0370.00",
                            "credit": "$\xa00.00",
                            "balance": None,
                        },
                        {
                            "name": "Manual Payment",
                            "debit": "$\xa00.00",
                            "credit": "$\xa0370.00",
                            "balance": None,
                        },
                        {},
                        {
                            "name": "Total",
                            "debit": None,
                            "credit": None,
                            "balance": "$\xa0300.00",
                        },
                    ],
                },
            ],
        )

    def test_document_data_for_bank_multicurrency(self):
        options = self._generate_options(
            self.report,
            "2017-01-01",
            "2017-01-31",
            default_options={"show_payment_lines": True},
        )
        journal_report_handler = self.env[self.report.custom_handler_model_name]
        self.assert_journal_vals_for_export(
            self.report,
            options,
            list(
                filter(
                    lambda x: x["id"] == self.default_bank_journal.id,
                    journal_report_handler._generate_document_data_for_export(
                        self.report, options, "pdf"
                    )["journals_vals"],
                )
            ),
            [
                {
                    "id": self.default_bank_journal.id,
                    "columns": [
                        "document",
                        "account_label",
                        "name",
                        "debit",
                        "credit",
                        "balance",
                    ],
                    "lines": [
                        {"name": "Starting Balance", "balance": "$\xa0100.00"},
                        {
                            "name": "2017_1_2",
                            "debit": "$\xa00.00",
                            "credit": "$\xa0200.00",
                            "balance": "$\xa0300.00",
                        },
                        {
                            "name": "Manual Payment",
                            "debit": "$\xa0370.00",
                            "credit": "$\xa00.00",
                            "balance": None,
                        },
                        {
                            "name": "Manual Payment",
                            "debit": "$\xa00.00",
                            "credit": "$\xa0370.00",
                            "balance": None,
                        },
                        {},
                        {
                            "name": "Total",
                            "debit": None,
                            "credit": None,
                            "balance": "$\xa0300.00",
                        },
                    ],
                }
            ],
        )

        new_bank_move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2017-01-01",
                "journal_id": self.company_data["default_journal_bank"].id,
                "currency_id": self.other_currency.id,
                "line_ids": [
                    Command.create(
                        {
                            "debit": 100.0,
                            "credit": 0.0,
                            "name": "2017_1_3",
                            "account_id": self.liquidity_account.id,
                            "currency_id": self.other_currency.id,
                            "amount_currency": 200,
                        }
                    ),
                    Command.create(
                        {
                            "debit": 0.0,
                            "credit": 100.0,
                            "name": "2017_1_4",
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "currency_id": self.other_currency.id,
                            "amount_currency": -200,
                        }
                    ),
                ],
            }
        )
        new_bank_move.action_post()

        self.assert_journal_vals_for_export(
            self.report,
            options,
            list(
                filter(
                    lambda x: x["id"] == self.default_bank_journal.id,
                    journal_report_handler._generate_document_data_for_export(
                        self.report, options, "pdf"
                    )["journals_vals"],
                )
            ),
            [
                {
                    "id": self.default_bank_journal.id,
                    "columns": [
                        "document",
                        "account_label",
                        "name",
                        "debit",
                        "credit",
                        "balance",
                        "amount_currency",
                    ],
                    "lines": [
                        {"name": "Starting Balance", "balance": "$\xa0100.00"},
                        {
                            "name": "2017_1_2",
                            "debit": "$\xa00.00",
                            "credit": "$\xa0200.00",
                            "balance": "$\xa0300.00",
                        },
                        {
                            "name": "2017_1_4",
                            "debit": "$\xa00.00",
                            "credit": "$\xa0100.00",
                            "balance": "$\xa0400.00",
                            "amount_currency": "200.000\xa0€",
                        },
                        {
                            "name": "Manual Payment",
                            "debit": "$\xa0370.00",
                            "credit": "$\xa00.00",
                            "balance": None,
                        },
                        {
                            "name": "Manual Payment",
                            "debit": "$\xa00.00",
                            "credit": "$\xa0370.00",
                            "balance": None,
                        },
                        {},
                        {
                            "name": "Total",
                            "debit": None,
                            "credit": None,
                            "balance": "$\xa0400.00",
                        },
                    ],
                },
            ],
        )

    def test_tax_summaries_run_the_tax_report_once(self):
        purchase_bill = self.init_invoice(
            "in_invoice",
            partner=self.partner_a,
            invoice_date="2017-01-10",
            amounts=[100.0],
            taxes=self.company_data["default_tax_purchase"],
            post=True,
        )
        options = self._generate_options(
            self.report,
            "2017-01-01",
            "2017-01-31",
            default_options={"unfold_all": True, "show_payment_lines": False},
        )
        tax_report = self.env.ref("account.generic_tax_report")
        report_class = type(self.env["report.formula"])
        get_lines = report_class._get_lines
        tax_report_runs = []

        def counting_get_lines(report, *args, **kwargs):
            if report == tax_report:
                tax_report_runs.append(report)
            return get_lines(report, *args, **kwargs)

        with patch.object(report_class, "_get_lines", counting_get_lines):
            lines = self.report._get_lines(options)

        self.assertEqual(len(tax_report_runs), 1)
        journal_summaries = {
            line["journal_id"]: line
            for line in lines
            if line.get("is_tax_section_line") and line.get("journal_id")
        }
        self.assertEqual(
            set(journal_summaries),
            {self.default_sale_journal.id, purchase_bill.journal_id.id},
        )
        purchase_taxes = [
            tax_line["name"]
            for tax_lines in journal_summaries[purchase_bill.journal_id.id][
                "tax_report_lines"
            ].values()
            for tax_line in tax_lines
        ]
        self.assertEqual(
            purchase_taxes, [self.company_data["default_tax_purchase"].name]
        )

    def test_tax_summary_keeps_a_tax_netting_to_zero_in_its_journal(self):
        sale_tax = self.company_data["default_tax_sale"]
        invoice = self.init_invoice(
            "out_invoice",
            partner=self.partner_a,
            invoice_date="2031-03-01",
            amounts=[100.0],
            taxes=sale_tax,
            post=True,
        )
        invoice._reverse_moves(
            [{"invoice_date": "2031-03-02", "date": "2031-03-02"}]
        ).action_post()
        bill = self.init_invoice(
            "in_invoice",
            partner=self.partner_a,
            invoice_date="2031-03-10",
            amounts=[100.0],
            taxes=self.company_data["default_tax_purchase"],
            post=True,
        )
        options = self._generate_options(
            self.report,
            "2031-03-01",
            "2031-03-31",
            default_options={"unfold_all": True, "show_payment_lines": False},
        )

        summary_taxes = {
            line["journal_id"]: [
                (tax_line["name"], tax_line["tax_amount_no_format"])
                for tax_lines in line["tax_report_lines"].values()
                for tax_line in tax_lines
            ]
            for line in self.report._get_lines(options)
            if line.get("is_tax_section_line") and line.get("journal_id")
        }
        self.assertEqual(summary_taxes[invoice.journal_id.id], [(sale_tax.name, 0.0)])
        self.assertEqual(
            summary_taxes[bill.journal_id.id],
            [(self.company_data["default_tax_purchase"].name, 15.0)],
        )

    def test_journal_lines_are_converted_to_the_report_currency(self):
        company_2 = self.company_data_2["company"]
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2017-01-05",
                "company_id": company_2.id,
                "journal_id": self.company_data_2["default_journal_misc"].id,
                "line_ids": [
                    Command.create(
                        {
                            "debit": 300.0,
                            "account_id": self.company_data_2[
                                "default_account_revenue"
                            ].id,
                        }
                    ),
                    Command.create(
                        {
                            "credit": 300.0,
                            "account_id": self.company_data_2[
                                "default_account_expense"
                            ].id,
                        }
                    ),
                ],
            }
        )
        move.action_post()
        report = self.report.with_context(
            allowed_company_ids=(self.company_data["company"] + company_2).ids
        )
        options = self._generate_options(report, "2017-01-01", "2017-01-31")
        rate = self.env["res.currency"]._get_conversion_rate(
            company_2.currency_id,
            self.company_data["currency"],
            self.company_data["company"],
            "2017-01-31",
        )
        journal_line = next(
            line
            for line in report._get_lines(options)
            if report._get_model_info_from_id(line["id"])
            == ("account.journal", self.company_data_2["default_journal_misc"].id)
        )
        debit = next(
            column["no_format"]
            for column in journal_line["columns"]
            if column["expression_label"] == "debit"
        )
        self.assertAlmostEqual(debit, 300.0 * rate)
        self.assertNotAlmostEqual(rate, 1.0)

    def test_export_lines_are_converted_to_the_report_currency(self):
        company_2 = self.company_data_2["company"]
        bank_journal_2 = self.company_data_2["default_journal_bank"]
        revenue_2 = self.company_data_2["default_account_revenue"]
        for date, amount in (("2016-12-15", 500.0), ("2017-01-10", 200.0)):
            self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "date": date,
                    "company_id": company_2.id,
                    "journal_id": bank_journal_2.id,
                    "line_ids": [
                        Command.create(
                            {
                                "debit": amount,
                                "account_id": bank_journal_2.default_account_id.id,
                            }
                        ),
                        Command.create({"credit": amount, "account_id": revenue_2.id}),
                    ],
                }
            ).action_post()
        report = self.report.with_context(
            allowed_company_ids=(self.company_data["company"] + company_2).ids
        )
        options = self._generate_options(report, "2017-01-01", "2017-01-31")
        rate = self.env["res.currency"]._get_conversion_rate(
            company_2.currency_id,
            self.company_data["currency"],
            self.company_data["company"],
            "2017-01-31",
        )
        self.assertNotAlmostEqual(rate, 1.0)

        journals_vals = report.env[
            report.custom_handler_model_name
        ]._generate_document_data_for_export(report, options, "pdf")["journals_vals"]

        def money(amount):
            return report._format_value(options, amount, "monetary")

        self.assert_journal_vals_for_export(
            report,
            options,
            [vals for vals in journals_vals if vals["id"] == bank_journal_2.id],
            [
                {
                    "id": bank_journal_2.id,
                    "lines": [
                        {"name": "Starting Balance", "balance": money(500.0 * rate)},
                        {
                            "debit": money(0.0),
                            "credit": money(200.0 * rate),
                            "balance": money(700.0 * rate),
                        },
                        {},
                        {"name": "Total", "balance": money(700.0 * rate)},
                    ],
                },
            ],
        )

    def test_global_tax_summary_rounding_unit(self):
        report = self.env.ref("account.journal_report")
        options = self._generate_options(report, "2017-01-01", "2017-01-31")
        options["unfold_all"] = True

        lines = report._get_lines(options)
        tax_lines = list(filter(lambda line: line.get("is_tax_section_line"), lines))

        default_balance = tax_lines[0]["tax_grid_summary_lines"]["US"]["c10"]["+"]
        self.assertEqual(default_balance, "$\xa0150.00")

        options["rounding_unit"] = "thousands"
        report.dispatch_report_action(
            options, "format_column_values_from_client", lines
        )

        thousands_balance = tax_lines[0]["tax_grid_summary_lines"]["US"]["c10"]["+"]
        self.assertEqual(
            thousands_balance, "$\xa00"
        )
