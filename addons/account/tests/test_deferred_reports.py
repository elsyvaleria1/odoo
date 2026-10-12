from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, HttpCase, tagged

from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon


@tagged("post_install", "-at_install")
class TestDeferredReports(TestAccountReportsCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.deferred_expense_report = cls.env.ref("account.deferred_expense_report")
        cls.deferred_revenue_report = cls.env.ref("account.deferred_revenue_report")
        cls.handler = cls.env["account.deferred.expense.report.handler"]

        cls.expense_accounts = [
            cls.env["account.account"].create(
                {
                    "name": f"Expense {i}",
                    "code": f"EXP{i}",
                    "account_type": "expense",
                }
            )
            for i in range(10)
        ]
        cls.revenue_accounts = [
            cls.env["account.account"].create(
                {
                    "name": f"Revenue {i}",
                    "code": f"REV{i}",
                    "account_type": "income",
                }
            )
            for i in range(3)
        ]

        cls.company = cls.company_data["company"]
        cls.deferral_account = cls.company_data["default_account_deferred_expense"]
        cls.company.account_config_id.deferred_expense_journal_id = cls.company_data[
            "default_journal_misc"
        ].id
        cls.company.account_config_id.deferred_revenue_journal_id = cls.company_data[
            "default_journal_misc"
        ].id
        cls.company.account_config_id.deferred_expense_account_id = cls.company_data[
            "default_account_deferred_expense"
        ].id
        cls.company.account_config_id.deferred_revenue_account_id = cls.company_data[
            "default_account_deferred_revenue"
        ].id

        cls.expense_lines = [
            [
                cls.expense_accounts[0],
                1000,
                "2023-01-01",
                "2023-04-30",
            ],
            [
                cls.expense_accounts[0],
                1050,
                "2023-01-16",
                "2023-04-30",
            ],
            [
                cls.expense_accounts[1],
                1225,
                "2023-01-01",
                "2023-04-15",
            ],
            [
                cls.expense_accounts[2],
                1680,
                "2023-01-21",
                "2023-04-14",
            ],
            [
                cls.expense_accounts[2],
                225,
                "2023-04-01",
                "2023-04-15",
            ],
        ]
        cls.revenue_lines = [
            [
                cls.revenue_accounts[0],
                1000,
                "2023-01-01",
                "2023-04-30",
            ],
            [
                cls.revenue_accounts[0],
                1050,
                "2023-01-16",
                "2023-04-30",
            ],
            [
                cls.revenue_accounts[1],
                1225,
                "2023-01-01",
                "2023-04-15",
            ],
            [
                cls.revenue_accounts[2],
                1680,
                "2023-01-21",
                "2023-04-14",
            ],
            [
                cls.revenue_accounts[2],
                225,
                "2023-04-01",
                "2023-04-15",
            ],
        ]

    def create_invoice(
        self,
        invoice_lines,
        move_type="in_invoice",
        invoice_date="2023-01-01",
        post=True,
    ):
        journal = self.company_data["default_journal_sale"]
        if move_type.startswith("in_"):
            journal = self.company_data["default_journal_purchase"]
        move = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner_a.id,
                "date": invoice_date,
                "invoice_date": invoice_date,
                "journal_id": journal.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "quantity": 1,
                            "account_id": invoice_line[0].id,
                            "price_unit": invoice_line[1],
                            "deferred_start_date": invoice_line[2],
                            "deferred_end_date": invoice_line[3],
                        }
                    )
                    for invoice_line in invoice_lines
                ],
            }
        )
        if post:
            move.action_post()
        return move

    def get_options(self, from_date, to_date, report=None):
        report = report or self.deferred_expense_report
        return self._generate_options(report, from_date, to_date)

    def get_lines(self, options, report=None):
        report = report if report is not None else self.deferred_expense_report
        self.env.cr.cache.pop("report_deferred_lines", None)
        return report._get_lines(options)

    def generate_deferral_entries(self, options, report_handler=None):
        report_handler = report_handler if report_handler is not None else self.handler
        self.env.cr.cache.pop("report_deferred_lines", None)
        return report_handler._generate_deferral_entry(options)

    def test_deferred_expense_report_months(self):
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "month"
        )
        self.create_invoice(self.expense_lines)

        options = self.get_options("2022-12-01", "2022-12-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5],
            [],
            options,
        )

        options = self.get_options("2023-01-01", "2023-01-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000 + 1050, 0, 0, 250 + 150, 400, 750 + 900),
                ("EXP1 Expense 1", 1225, 0, 0, 350, 350, 875),
                (
                    "EXP2 Expense 2",
                    1680 + 225,
                    225,
                    0,
                    600 * (10 / 30) + 0,
                    600 * (10 / 30),
                    600 * (2 + 14 / 30) + 225,
                ),
                ("Total", 5180, 225, 0, 950, 950, 4230),
            ],
            options,
        )

        options = self.get_options("2023-02-01", "2023-02-28")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                (
                    "EXP0 Expense 0",
                    1000 + 1050,
                    0,
                    250 + 150,
                    250 + 300,
                    950,
                    500 + 600,
                ),
                ("EXP1 Expense 1", 1225, 0, 350, 350, 700, 525),
                (
                    "EXP2 Expense 2",
                    1680 + 225,
                    225,
                    600 * (10 / 30) + 0,
                    600 + 0,
                    600 * (10 / 30) + 600,
                    600 * (1 + 14 / 30) + 225,
                ),
                ("Total", 5180, 225, 950, 1500, 950 + 1500, 2730),
            ],
            options,
        )

        options = self.get_options("2023-04-01", "2023-04-30")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000 + 1050, 0, 750 + 750, 250 + 300, 2050, 0),
                ("EXP1 Expense 1", 1225, 0, 1050, 175, 1225, 0),
                (
                    "EXP2 Expense 2",
                    1680 + 225,
                    0,
                    600 * (2 + 10 / 30),
                    600 * (14 / 30) + 225,
                    600 * (2 + 10 / 30) + 600 * (14 / 30) + 225,
                    0,
                ),
                ("Total", 5180, 0, 3950, 1230, 3950 + 1230, 0),
            ],
            options,
        )

        options = self.get_options("2023-05-01", "2023-05-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [],
            options,
        )

        options = self.get_options("2023-01-01", "2023-03-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000 + 1050, 0, 0, 750 + 750, 750 + 750, 550),
                ("EXP1 Expense 1", 1225, 0, 0, 1050, 1050, 175),
                (
                    "EXP2 Expense 2",
                    1680 + 225,
                    225,
                    0,
                    600 * (2 + 10 / 30) + 0,
                    600 * (2 + 10 / 30),
                    280 + 225,
                ),
                ("Total", 5180, 225, 0, 3950, 3950, 1230),
            ],
            options,
        )

        options = self.get_options("2023-04-01", "2023-06-30")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                (
                    "EXP0 Expense 0",
                    1000 + 1050,
                    0,
                    750 + 750,
                    250 + 300,
                    750 + 750 + 250 + 300,
                    0,
                ),
                ("EXP1 Expense 1", 1225, 0, 1050, 175, 1050 + 175, 0),
                (
                    "EXP2 Expense 2",
                    1680 + 225,
                    0,
                    600 * (2 + 10 / 30),
                    600 * (14 / 30) + 225,
                    600 * (2 + 10 / 30) + 600 * (14 / 30) + 225,
                    0,
                ),
                ("Total", 5180, 0, 3950, 1230, 3950 + 1230, 0),
            ],
            options,
        )

        options = self.get_options("2022-01-01", "2022-12-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5],
            [],
            options,
        )

        options = self.get_options("2023-01-01", "2023-12-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5],
            [],
            options,
        )

    def test_deferred_revenue_report(self):
        self.company.account_config_id.deferred_revenue_amount_computation_method = (
            "month"
        )
        self.create_invoice(self.revenue_lines, "out_invoice")

        options = self.get_options(
            "2022-12-01", "2022-12-31", self.deferred_revenue_report
        )
        lines = self.get_lines(options, self.deferred_revenue_report)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5],
            [],
            options,
        )

        options = self.get_options(
            "2023-01-01", "2023-01-31", self.deferred_revenue_report
        )
        lines = self.get_lines(options, self.deferred_revenue_report)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("REV0 Revenue 0", 1000 + 1050, 0, 0, 250 + 150, 250 + 150, 750 + 900),
                ("REV1 Revenue 1", 1225, 0, 0, 350, 350, 875),
                (
                    "REV2 Revenue 2",
                    1680 + 225,
                    225,
                    0,
                    600 * (10 / 30) + 0,
                    600 * (10 / 30),
                    600 * (2 + 14 / 30) + 225,
                ),
                ("Total", 5180, 225, 0, 950, 950, 4230),
            ],
            options,
        )

        options = self.get_options(
            "2023-02-01", "2023-02-28", self.deferred_revenue_report
        )
        lines = self.get_lines(options, self.deferred_revenue_report)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                (
                    "REV0 Revenue 0",
                    1000 + 1050,
                    0,
                    250 + 150,
                    250 + 300,
                    250 + 150 + 250 + 300,
                    500 + 600,
                ),
                ("REV1 Revenue 1", 1225, 0, 350, 350, 350 + 350, 525),
                (
                    "REV2 Revenue 2",
                    1680 + 225,
                    225,
                    600 * (10 / 30) + 0,
                    600,
                    600 * (10 / 30) + 0 + 600 + 0,
                    600 * (1 + 14 / 30) + 225,
                ),
                ("Total", 5180, 225, 950, 1500, 950 + 1500, 2730),
            ],
            options,
        )

        options = self.get_options(
            "2023-04-01", "2023-04-30", self.deferred_revenue_report
        )
        lines = self.get_lines(options, self.deferred_revenue_report)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                (
                    "REV0 Revenue 0",
                    1000 + 1050,
                    0,
                    750 + 750,
                    250 + 300,
                    750 + 750 + 250 + 300,
                    0,
                ),
                ("REV1 Revenue 1", 1225, 0, 1050, 175, 1050 + 175, 0),
                (
                    "REV2 Revenue 2",
                    1680 + 225,
                    0,
                    600 * (2 + 10 / 30),
                    600 * (14 / 30) + 225,
                    600 * (2 + 10 / 30) + 600 * (14 / 30) + 225,
                    0,
                ),
                ("Total", 5180, 0, 3950, 1230, 3950 + 1230, 0),
            ],
            options,
        )

        options = self.get_options(
            "2023-05-01", "2023-05-31", self.deferred_revenue_report
        )
        lines = self.get_lines(options, self.deferred_revenue_report)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5],
            [],
            options,
        )

        options = self.get_options(
            "2023-01-01", "2023-03-31", self.deferred_revenue_report
        )
        lines = self.get_lines(options, self.deferred_revenue_report)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("REV0 Revenue 0", 1000 + 1050, 0, 0, 750 + 750, 750 + 750, 550),
                ("REV1 Revenue 1", 1225, 0, 0, 1050, 1050, 175),
                (
                    "REV2 Revenue 2",
                    1680 + 225,
                    225,
                    0,
                    600 * (2 + 10 / 30) + 0,
                    600 * (2 + 10 / 30) + 0,
                    280 + 225,
                ),
                ("Total", 5180, 225, 0, 3950, 3950, 1230),
            ],
            options,
        )

        options = self.get_options(
            "2023-04-01", "2023-06-30", self.deferred_revenue_report
        )
        lines = self.get_lines(options, self.deferred_revenue_report)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                (
                    "REV0 Revenue 0",
                    1000 + 1050,
                    0,
                    750 + 750,
                    250 + 300,
                    750 + 750 + 250 + 300,
                    0,
                ),
                ("REV1 Revenue 1", 1225, 0, 1050, 175, 1050 + 175, 0),
                (
                    "REV2 Revenue 2",
                    1680 + 225,
                    0,
                    600 * (2 + 10 / 30),
                    600 * (14 / 30) + 225,
                    600 * (2 + 10 / 30) + 600 * (14 / 30) + 225,
                    0,
                ),
                ("Total", 5180, 0, 3950, 1230, 3950 + 1230, 0),
            ],
            options,
        )

        options = self.get_options(
            "2022-01-01", "2022-12-31", self.deferred_revenue_report
        )
        lines = self.get_lines(options, self.deferred_revenue_report)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5],
            [],
            options,
        )

        options = self.get_options(
            "2023-01-01", "2023-12-31", self.deferred_revenue_report
        )
        lines = self.get_lines(options, self.deferred_revenue_report)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5],
            [],
            options,
        )

    def test_deferred_expense_report_days(self):
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "day"
        )
        self.create_invoice(self.expense_lines)

        options = self.get_options("2022-12-01", "2022-12-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5],
            [],
            options,
        )

        options = self.get_options("2023-01-01", "2023-01-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000 + 1050, 0, 0, 418.33, 418.33, 1631.67),
                ("EXP1 Expense 1", 1225, 0, 0, 361.67, 361.67, 863.33),
                ("EXP2 Expense 2", 1680 + 225, 225, 0, 220, 220, 1460 + 225),
                ("Total", 5180, 225, 0, 1000, 1000, 4180),
            ],
            options,
        )

        options = self.get_options("2023-02-01", "2023-02-28")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                (
                    "EXP0 Expense 0",
                    1000 + 1050,
                    0,
                    418.33,
                    513.33,
                    418.33 + 513.34,
                    1118.33,
                ),
                ("EXP1 Expense 1", 1225, 0, 361.67, 326.67, 361.67 + 326.66, 536.67),
                ("EXP2 Expense 2", 1680 + 225, 225, 220, 560, 220 + 560, 900 + 225),
                ("Total", 5180, 225, 1000, 1400, 1000 + 1400, 2780),
            ],
            options,
        )

        options = self.get_options("2023-04-01", "2023-04-30")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000 + 1050, 0, 1500, 550, 1500 + 550, 0),
                ("EXP1 Expense 1", 1225, 0, 1050, 175, 1050 + 175, 0),
                ("EXP2 Expense 2", 1680 + 225, 0, 1400, 505, 1400 + 505, 0),
                ("Total", 5180, 0, 3950, 1230, 3950 + 1230, 0),
            ],
            options,
        )

        options = self.get_options("2023-01-01", "2023-03-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000 + 1050, 0, 0, 1500, 1500, 550),
                ("EXP1 Expense 1", 1225, 0, 0, 1050, 1050, 175),
                ("EXP2 Expense 2", 1680 + 225, 225, 0, 1400, 1400, 280 + 225),
                ("Total", 5180, 225, 0, 3950, 3950, 1230),
            ],
            options,
        )

    def test_deferred_expense_report_filter_all_entries(self):
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "day"
        )
        self.create_invoice(self.expense_lines, post=True)
        self.create_invoice(self.expense_lines, post=False)

        options = self.get_options("2023-02-01", "2023-02-28")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                (
                    "EXP0 Expense 0",
                    1000 + 1050,
                    0,
                    418.33,
                    513.33,
                    418.33 + 513.34,
                    1118.33,
                ),
                ("EXP1 Expense 1", 1225, 0, 361.67, 326.67, 361.67 + 326.66, 536.67),
                ("EXP2 Expense 2", 1680 + 225, 225, 220, 560, 220 + 560, 900 + 225),
                ("Total", 5180, 225, 1000, 1400, 1000 + 1400, 2780),
            ],
            options,
        )

    def test_deferred_expense_report_comparison(self):
        self.create_invoice(self.expense_lines)

        options = self.get_options("2023-04-01", "2023-04-30")
        options = self._update_comparison_filter(
            options, self.deferred_expense_report, "previous_period", 4
        )
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            [
                ("EXP0 Expense 0", 2050, 0, 0, 0, 400, 550, 550, 550, 2050, 0),
                ("EXP1 Expense 1", 1225, 0, 0, 0, 350, 350, 350, 175, 1225, 0),
                ("EXP2 Expense 2", 1905, 0, 0, 0, 200, 600, 600, 505, 1905, 0),
                ("Total", 5180, 0, 0, 0, 950, 1500, 1500, 1230, 5180, 0),
            ],
            options,
        )

    def test_deferred_expense_report_partially_deductible_tax(self):
        partially_deductible_tax = self.env["account.tax"].create(
            {
                "name": "Partially deductible Tax",
                "amount": 40,
                "amount_type": "percent",
                "type_tax_use": "purchase",
                "invoice_repartition_line_ids": [
                    Command.create({"repartition_type": "base"}),
                    Command.create(
                        {
                            "factor_percent": 50,
                            "repartition_type": "tax",
                            "use_in_tax_closing": False,
                        }
                    ),
                    Command.create(
                        {
                            "factor_percent": 50,
                            "repartition_type": "tax",
                            "account_id": self.company_data[
                                "default_account_tax_purchase"
                            ].id,
                            "use_in_tax_closing": True,
                        }
                    ),
                ],
                "refund_repartition_line_ids": [
                    Command.create({"repartition_type": "base"}),
                    Command.create(
                        {
                            "factor_percent": 50,
                            "repartition_type": "tax",
                            "use_in_tax_closing": False,
                        }
                    ),
                    Command.create(
                        {
                            "factor_percent": 50,
                            "repartition_type": "tax",
                            "account_id": self.company_data[
                                "default_account_tax_purchase"
                            ].id,
                            "use_in_tax_closing": True,
                        }
                    ),
                ],
            }
        )

        move_form = Form(
            self.env["account.move"].with_context(default_move_type="in_invoice")
        )
        move_form.partner_id = self.partner_a
        move_form.invoice_date = fields.Date.from_string("2022-01-01")
        for year in (2022, 2023, 2023):
            with move_form.invoice_line_ids.new() as line_form:
                line_form.name = f"Car {year}"
                line_form.quantity = 1
                line_form.price_unit = 1000
                line_form.deferred_start_date = f"{year}-01-01"
                line_form.deferred_end_date = f"{year}-03-31"
                line_form.tax_ids.add(partially_deductible_tax)
                line_form.account_id = self.expense_accounts[0]
        move = move_form.save()
        move.action_post()

        self.assertEqual(
            len(
                move.line_ids.filtered(
                    lambda l: l.account_id == self.expense_accounts[0]
                )
            ),
            5,
        )

        options = self.get_options("2023-02-01", "2023-02-28")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 2400, 0, 800, 800, 1600, 800),
                ("Total", 2400, 0, 800, 800, 1600, 800),
            ],
            options,
        )

    def test_deferred_expense_report_credit_notes(self):
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "day"
        )
        self.create_invoice(self.expense_lines, move_type="in_refund")

        options = self.get_options("2023-02-01", "2023-02-28")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                (
                    "EXP0 Expense 0",
                    -1000 - 1050,
                    0,
                    -418.33,
                    -513.33,
                    -931.67,
                    -1118.33,
                ),
                ("EXP1 Expense 1", -1225, 0, -361.67, -326.67, -688.33, -536.67),
                (
                    "EXP2 Expense 2",
                    -1680 - 225,
                    -225,
                    -220,
                    -560,
                    -220 - 560,
                    -900 - 225,
                ),
                ("Total", -5180, -225, -1000, -1400, -1000 - 1400, -2780),
            ],
            options,
        )

    def test_deferred_expense_report_compute_method_full_months(self):
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "full_months"
        )
        self.create_invoice(
            [[self.expense_accounts[0], 1200, "2023-01-31", "2024-01-30"]]
        )
        self.create_invoice(
            [[self.expense_accounts[1], 1200, "2023-02-01", "2023-03-31"]]
        )
        self.create_invoice(
            [[self.expense_accounts[2], 1200, "2023-02-01", "2023-03-16"]]
        )
        self.create_invoice(
            [[self.expense_accounts[3], 1200, "2023-02-05", "2023-03-16"]]
        )
        self.create_invoice(
            [[self.expense_accounts[4], 1200, "2023-02-05", "2023-03-31"]]
        )
        self.create_invoice(
            [[self.expense_accounts[5], 1200, "2023-02-13", "2023-04-30"]]
        )
        self.create_invoice(
            [[self.expense_accounts[6], 1200, "2023-03-01", "2023-06-18"]]
        )
        self.create_invoice(
            [[self.expense_accounts[7], 1200, "2023-03-05", "2023-06-30"]]
        )
        self.create_invoice(
            [[self.expense_accounts[8], 1200, "2023-03-13", "2024-03-12"]]
        )
        self.create_invoice(
            [[self.expense_accounts[9], 1200, "2023-03-14", "2023-03-18"]]
        )

        options = self.get_options("2023-03-01", "2023-03-31")
        lines = self.get_lines(options)

        for line in lines:
            total = line["columns"][0]["no_format"]
            before = line["columns"][2]["no_format"]
            current = line["columns"][3]["no_format"]
            later = line["columns"][5]["no_format"]
            self.assertAlmostEqual(total, before + current + later, 3)

        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1200, 0, 200, 100, 300, 900),
                ("EXP1 Expense 1", 1200, 0, 600, 600, 1200, 0),
                ("EXP2 Expense 2", 1200, 0, 1200, 0, 1200, 0),
                ("EXP3 Expense 3", 1200, 0, 1200, 0, 1200, 0),
                ("EXP4 Expense 4", 1200, 0, 600, 600, 1200, 0),
                ("EXP5 Expense 5", 1200, 0, 400, 400, 800, 400),
                ("EXP6 Expense 6", 1200, 0, 0, 400, 400, 800),
                ("EXP7 Expense 7", 1200, 0, 0, 300, 300, 900),
                ("EXP8 Expense 8", 1200, 0, 0, 100, 100, 1100),
                ("EXP9 Expense 9", 1200, 0, 0, 1200, 1200, 0),
                ("Total", 12000, 0, 4200, 3700, 7900, 4100),
            ],
            options,
        )

    def assert_invoice_lines(self, deferred_move, expected_values):
        for line, expected_value in zip(
            deferred_move.line_ids, expected_values, strict=False
        ):
            expected_account, expected_debit, expected_credit = expected_value
            self.assertRecordValues(
                line,
                [
                    {
                        "account_id": expected_account.id,
                        "debit": expected_debit,
                        "credit": expected_credit,
                    }
                ],
            )

    def test_deferred_expense_report_accounting_date(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        self.create_invoice([self.expense_lines[0]], invoice_date="2023-02-15")

        options = self.get_options("2023-01-01", "2023-01-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5],
            [],
            options,
        )
        self.assertFalse(self.generate_deferral_entries(options).exists())

        options = self.get_options("2023-02-01", "2023-02-28")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000, 0, 250, 250, 500, 500),
                ("Total", 1000, 0, 250, 250, 500, 500),
            ],
            options,
        )

        options = self.get_options("2023-03-01", "2023-03-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000, 0, 500, 250, 750, 250),
                ("Total", 1000, 0, 500, 250, 750, 250),
            ],
            options,
        )

        options = self.get_options("2023-04-01", "2023-04-30")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000, 0, 750, 250, 1000, 0),
                ("Total", 1000, 0, 750, 250, 1000, 0),
            ],
            options,
        )

        options = self.get_options("2023-05-01", "2023-05-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5],
            [],
            options,
        )

    def test_deferred_expense_generate_grouped_entries_method(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )

        options = self.get_options("2023-01-01", "2023-01-31")

        self.assertFalse(self.generate_deferral_entries(options).exists())

        for expense_line in self.expense_lines[:3]:
            self.create_invoice([expense_line])

        self.assertEqual(
            self.env["account.move.line"].search_count(
                [("account_id", "=", self.deferral_account.id)]
            ),
            0,
        )

        generated_entries_january = self.generate_deferral_entries(options)

        deferred_move_january = generated_entries_january[0]
        self.assertRecordValues(
            deferred_move_january,
            [
                {
                    "state": "posted",
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-01-31"),
                }
            ],
        )
        expected_values_january = [
            [self.expense_accounts[0], 0, 1000 + 1050],
            [self.expense_accounts[0], 250 + 150, 0],
            [self.expense_accounts[1], 0, 1225],
            [self.expense_accounts[1], 350, 0],
            [self.deferral_account, 1000 + 1050 + 1225 - 250 - 150 - 350, 0],
        ]
        self.assert_invoice_lines(deferred_move_january, expected_values_january)

        deferred_inverse_january = generated_entries_january[1]
        self.assertEqual(deferred_inverse_january.move_type, "entry")
        self.assertEqual(deferred_inverse_january.state, "posted")
        self.assertEqual(
            deferred_inverse_january.date, fields.Date.from_string("2023-02-01")
        )

        self.assertFalse(self.generate_deferral_entries(options).exists())

        generated_entries_february = self.generate_deferral_entries(
            self.get_options("2023-02-01", "2023-02-28")
        )
        deferred_move_february = generated_entries_february[0]
        expected_values_february = [
            [self.expense_accounts[0], 0, 1000 + 1050],
            [self.expense_accounts[0], 500 + 450, 0],
            [self.expense_accounts[1], 0, 1225],
            [self.expense_accounts[1], 700, 0],
            [self.deferral_account, 1000 + 1050 + 1225 - 500 - 450 - 700, 0],
        ]
        self.assert_invoice_lines(deferred_move_february, expected_values_february)

    def _test_deferred_expense_partially_generate_grouped_entries_method_common(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )

        options = self.get_options("2023-01-01", "2023-01-31")

        self.create_invoice([self.expense_lines[0]])
        self.create_invoice([self.expense_lines[1]])

        generated_entries_january = self.generate_deferral_entries(options)

        deferred_move_january, deferred_inverse_january = generated_entries_january
        self.assertRecordValues(
            deferred_move_january,
            [
                {
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-01-31"),
                }
            ],
        )
        expected_values_january = [
            [self.expense_accounts[0], 0, 1000 + 1050],
            [self.expense_accounts[0], 250 + 150, 0],
            [self.deferral_account, 1000 + 1050 - 250 - 150, 0],
        ]
        self.assert_invoice_lines(deferred_move_january, expected_values_january)

        self.assertRecordValues(
            deferred_inverse_january,
            [
                {
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-02-01"),
                }
            ],
        )

        self.assertFalse(self.generate_deferral_entries(options).exists())

        self.create_invoice([self.expense_lines[2]])

        generated_entries_january2 = self.generate_deferral_entries(options)
        deferred_move_january2 = generated_entries_january2[0]
        self.assertRecordValues(
            deferred_move_january2,
            [
                {
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-01-31"),
                }
            ],
        )
        expected_values_january2 = [
            [self.expense_accounts[1], 0, 1225],
            [self.expense_accounts[1], 350, 0],
            [self.deferral_account, 1225 - 350, 0],
        ]
        self.assert_invoice_lines(deferred_move_january2, expected_values_january2)
        return deferred_move_january, deferred_inverse_january

    def test_deferred_expense_partially_generate_grouped_entries_method_past_period(
        self,
    ):
        deferred_move_january, deferred_inverse_january = (
            self._test_deferred_expense_partially_generate_grouped_entries_method_common()
        )
        self.assertEqual(deferred_move_january.state, "posted")
        self.assertEqual(deferred_inverse_january.state, "posted")

    @freeze_time("2023-01-01")
    def test_deferred_expense_partially_generate_grouped_entries_method_current_period(
        self,
    ):
        deferred_move_january, deferred_inverse_january = (
            self._test_deferred_expense_partially_generate_grouped_entries_method_common()
        )
        self.assertEqual(deferred_move_january.state, "draft")
        self.assertEqual(deferred_inverse_january.state, "draft")

    @freeze_time("2023-01-01")
    def test_deferred_expense_partially_generate_grouped_entries_method_later_period(
        self,
    ):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )

        options = self.get_options("2023-02-01", "2023-02-28")

        self.create_invoice([self.expense_lines[0]])
        self.create_invoice([self.expense_lines[1]])

        generated_entries_february = self.generate_deferral_entries(options)

        deferred_move_february, deferred_inverse_february = generated_entries_february
        self.assertRecordValues(
            deferred_move_february,
            [
                {
                    "state": "draft",
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-02-28"),
                }
            ],
        )
        expected_values_february = [
            [self.expense_accounts[0], 0, 1000 + 1050],
            [self.expense_accounts[0], 500 + 450, 0],
            [self.deferral_account, 1000 + 1050 - 500 - 450, 0],
        ]
        self.assert_invoice_lines(deferred_move_february, expected_values_february)

        self.assertRecordValues(
            deferred_inverse_february,
            [
                {
                    "state": "draft",
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-03-01"),
                }
            ],
        )

        self.assertFalse(self.generate_deferral_entries(options).exists())

        self.create_invoice([self.expense_lines[2]])

        generated_entries_february2 = self.generate_deferral_entries(options)
        deferred_move_february2 = generated_entries_february2[0]
        self.assertRecordValues(
            deferred_move_february2,
            [
                {
                    "state": "draft",
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-02-28"),
                }
            ],
        )
        expected_values_february2 = [
            [self.expense_accounts[1], 0, 1225],
            [self.expense_accounts[1], 700, 0],
            [self.deferral_account, 1225 - 700, 0],
        ]
        self.assert_invoice_lines(deferred_move_february2, expected_values_february2)

    def test_deferred_expense_generate_future_deferrals_grouped(self):
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "month"
        )
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        self.create_invoice(
            [[self.expense_accounts[0], 750, "2023-03-01", "2023-04-15"]]
        )

        generated_entries_january = self.generate_deferral_entries(
            self.get_options("2023-01-01", "2023-01-31")
        )

        deferred_move_january = generated_entries_january[0]
        self.assertRecordValues(
            deferred_move_january,
            [
                {
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-01-31"),
                }
            ],
        )
        expected_values_january = [
            [self.expense_accounts[0], 0, 750],
            [self.deferral_account, 750, 0],
        ]
        self.assert_invoice_lines(deferred_move_january, expected_values_january)

        deferred_inverse_january = generated_entries_january[1]
        self.assertRecordValues(
            deferred_inverse_january,
            [
                {
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-02-01"),
                }
            ],
        )
        expected_values_inverse_january = [
            [self.expense_accounts[0], 750, 0],
            [self.deferral_account, 0, 750],
        ]
        self.assert_invoice_lines(
            deferred_inverse_january, expected_values_inverse_january
        )

        generated_entries_february = self.generate_deferral_entries(
            self.get_options("2023-02-01", "2023-02-28")
        )

        deferred_move_february = generated_entries_february[0]
        self.assertRecordValues(
            deferred_move_february,
            [
                {
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-02-28"),
                }
            ],
        )
        expected_values_february = [
            [self.expense_accounts[0], 0, 750],
            [self.deferral_account, 750, 0],
        ]
        self.assert_invoice_lines(deferred_move_february, expected_values_february)

        deferred_inverse_february = generated_entries_february[1]
        self.assertRecordValues(
            deferred_inverse_february,
            [
                {
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-03-01"),
                }
            ],
        )
        expected_values_inverse_february = [
            [self.expense_accounts[0], 750, 0],
            [self.deferral_account, 0, 750],
        ]
        self.assert_invoice_lines(
            deferred_inverse_february, expected_values_inverse_february
        )

        generated_entries_march = self.generate_deferral_entries(
            self.get_options("2023-03-01", "2023-03-31")
        )

        deferred_move_march = generated_entries_march[0]
        self.assertRecordValues(
            deferred_move_march,
            [
                {
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-03-31"),
                }
            ],
        )
        expected_values_march = [
            [self.expense_accounts[0], 0, 750],
            [self.expense_accounts[0], 500, 0],
            [self.deferral_account, 250, 0],
        ]
        self.assert_invoice_lines(deferred_move_march, expected_values_march)

        deferred_inverse_march = generated_entries_march[1]
        self.assertRecordValues(
            deferred_inverse_march,
            [
                {
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-04-01"),
                }
            ],
        )
        expected_values_inverse_march = [
            [self.expense_accounts[0], 750, 0],
            [self.expense_accounts[0], 0, 500],
            [self.deferral_account, 0, 250],
        ]
        self.assert_invoice_lines(deferred_inverse_march, expected_values_inverse_march)

        self.assertFalse(
            self.generate_deferral_entries(
                self.get_options("2023-04-01", "2023-04-30")
            ).exists()
        )

    def test_deferred_revenue_generate_grouped_without_taxes(self):
        self.company.account_config_id.generate_deferred_revenue_entries_method = (
            "manual"
        )
        deferral_account = self.company_data["default_account_deferred_revenue"]
        revenue_account_with_taxes = self.env["account.account"].create(
            {
                "name": "Revenue with Taxes",
                "code": "REVWTAXES",
                "account_type": "income",
                "tax_ids": [Command.set(self.tax_sale_a.ids)],
            }
        )
        options = self.get_options(
            "2023-01-01", "2023-01-31", self.deferred_revenue_report
        )
        revenue_handler = self.env["account.deferred.revenue.report.handler"]

        self.create_invoice(
            [[revenue_account_with_taxes, 1000, "2023-01-01", "2023-04-30"]],
            move_type="out_invoice",
        )

        self.assertEqual(
            self.env["account.move.line"].search_count(
                [("account_id", "=", deferral_account.id)]
            ),
            0,
        )

        generated_entries_january = self.generate_deferral_entries(
            options, revenue_handler
        )

        deferred_move_january = generated_entries_january[0]
        self.assertRecordValues(
            deferred_move_january,
            [
                {
                    "state": "posted",
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-01-31"),
                }
            ],
        )
        expected_values_january = [
            [revenue_account_with_taxes, 1000, 0],
            [revenue_account_with_taxes, 0, 250],
            [deferral_account, 0, 750],
        ]
        self.assert_invoice_lines(deferred_move_january, expected_values_january)
        self.assertFalse(deferred_move_january.line_ids.tax_line_id)

    def test_deferred_values_rounding(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "day"
        )
        self.create_invoice(
            [[self.expense_accounts[0], 600, "2023-04-04", "2023-05-25"]]
        )
        self.create_invoice(
            [[self.expense_accounts[1], 600, "2023-04-05", "2023-05-16"]]
        )
        self.create_invoice(
            [[self.expense_accounts[0], 600, "2023-04-04", "2023-05-08"]]
        )

        self.generate_deferral_entries(self.get_options("2023-04-01", "2023-04-30"))

    def test_deferred_single_rounding(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "month"
        )
        self.create_invoice(
            [[self.expense_accounts[0], 4.95, "2023-01-01", "2023-10-31"]]
        )

        generated_entries = self.generate_deferral_entries(
            self.get_options("2023-01-01", "2023-01-31")
        )

        deferral_move = generated_entries[0]
        expected_values = [
            [self.expense_accounts[0], 0, 4.95],
            [self.expense_accounts[0], 0.50, 0],
            [self.deferral_account, 4.46, 0],
            [self.deferral_account, 0, 0.01],
        ]
        self.assert_invoice_lines(deferral_move, expected_values)

    def test_deferred_fully_inside_report_period(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "month"
        )

        move1 = self.create_invoice(
            [[self.expense_accounts[0], 600, "2023-01-15", "2023-01-30"]],
            invoice_date="2023-01-15",
        )
        options_january = self.get_options("2023-01-01", "2023-01-31")
        lines = self.get_lines(options_january)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4],
            [],
            options_january,
        )
        self.assertFalse(self.generate_deferral_entries(options_january).exists())

        move1.action_cancel()

        self.create_invoice(
            [[self.expense_accounts[0], 1000, "2023-02-10", "2023-02-28"]],
            invoice_date="2023-01-01",
        )

        lines = self.get_lines(options_january)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000, 1000, 0, 0, 0, 1000),
                ("Total", 1000, 1000, 0, 0, 0, 1000),
            ],
            options_january,
        )

        generated_entries = self.generate_deferral_entries(options_january)

        deferral_move_january = generated_entries[0]
        self.assertEqual(deferral_move_january.date, fields.Date.to_date("2023-01-31"))
        expected_values_january = [
            [self.expense_accounts[0], 0, 1000],
            [self.deferral_account, 1000, 0],
        ]
        self.assert_invoice_lines(deferral_move_january, expected_values_january)

        options_february = self.get_options("2023-02-01", "2023-02-28")
        lines = self.get_lines(options_february)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000, 0, 0, 1000, 1000, 0),
                ("Total", 1000, 0, 0, 1000, 1000, 0),
            ],
            options_february,
        )

        self.assertFalse(self.generate_deferral_entries(options_january).exists())

    def test_deferred_same_date(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "month"
        )
        self.create_invoice(
            [[self.expense_accounts[0], 1000, "2023-10-30", "2023-10-30"]]
        )

        options_sept = self.get_options("2023-09-01", "2023-09-30")
        lines = self.get_lines(options_sept)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000, 1000, 0, 0, 0, 1000),
                ("Total", 1000, 1000, 0, 0, 0, 1000),
            ],
            options_sept,
        )

        generated_entries = self.generate_deferral_entries(options_sept)

        deferral_move = generated_entries[0]
        self.assertEqual(deferral_move.date, fields.Date.to_date("2023-09-30"))
        expected_values = [
            [self.expense_accounts[0], 0, 1000],
            [self.deferral_account, 1000, 0],
        ]
        self.assert_invoice_lines(deferral_move, expected_values)

    def test_deferred_expense_change_grouped_entries_method(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "on_validation"
        )

        self.create_invoice([self.expense_lines[0]])
        self.assertEqual(
            self.env["account.move.line"].search_count(
                [("account_id", "=", self.deferral_account.id)]
            ),
            5,
        )

        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        self.assertFalse(
            self.generate_deferral_entries(
                self.get_options("2023-02-01", "2023-02-28")
            ).exists()
        )

    def test_deferred_expense_manual_generation_totally_deferred(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )

        self.create_invoice(
            [[self.expense_accounts[0], 1000, "2023-01-01", "2023-04-30"]]
        )
        self.generate_deferral_entries(self.get_options("2023-03-01", "2023-03-31"))
        self.assertEqual(
            self.env["account.move.line"].search_count(
                [("account_id", "=", self.deferral_account.id)]
            ),
            2,
        )

        self.assertFalse(
            self.generate_deferral_entries(
                self.get_options("2023-04-01", "2023-04-30")
            ).exists()
        )

        move2 = self.create_invoice(
            [[self.expense_accounts[1], 1000, "2023-01-01", "2023-05-31"]]
        )
        generated_entry = self.generate_deferral_entries(
            self.get_options("2023-04-01", "2023-04-30")
        )[0]
        self.assertEqual(len(generated_entry.line_ids), 3)
        self.assertEqual(generated_entry.deferred_original_move_ids, move2)

    def test_deferred_expense_manual_generation_only_posted(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )

        self.create_invoice([self.expense_lines[0]], post=False)
        options = self.get_options("2023-01-01", "2023-01-31")
        options["all_entries"] = True
        self.assertFalse(self.generate_deferral_entries(options).exists())

    def test_deferred_expense_manual_generation_after_on_validation(self):
        move = self.create_invoice([self.expense_lines[0]])
        self.assertEqual(len(move.deferred_move_ids), 5)

        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        self.create_invoice([self.expense_lines[0]])

        options = self.get_options("2023-01-01", "2023-01-31")
        generated_entries_jan = self.generate_deferral_entries(options)

        deferred_move_jan = generated_entries_jan[0]
        self.assertRecordValues(
            deferred_move_jan,
            [
                {
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-01-31"),
                }
            ],
        )
        expected_values_jan = [
            [self.expense_accounts[0], 0, 1000],
            [self.expense_accounts[0], 250, 0],
            [self.deferral_account, 750, 0],
        ]
        self.assert_invoice_lines(deferred_move_jan, expected_values_jan)

        deferred_inverse_jan = generated_entries_jan[1]
        self.assertRecordValues(
            deferred_inverse_jan,
            [
                {
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-02-01"),
                }
            ],
        )
        expected_values_inverse_jan = [
            [self.expense_accounts[0], 1000, 0],
            [self.expense_accounts[0], 0, 250],
            [self.deferral_account, 0, 750],
        ]
        self.assert_invoice_lines(deferred_inverse_jan, expected_values_inverse_jan)

    def test_deferred_expense_manual_generation_old_moves(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "month"
        )

        self.create_invoice(
            [(self.expense_accounts[0], 1200, "2022-01-01", "2022-12-31")]
        )
        self.create_invoice(
            [(self.expense_accounts[0], 1200, "2023-01-01", "2023-12-31")]
        )

        options = self.get_options("2023-03-01", "2023-03-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1200, 0, 200, 100, 300, 900),
                ("Total", 1200, 0, 200, 100, 300, 900),
            ],
            options,
        )

        expected_values = (
            (self.expense_accounts[0], 0, 1200),
            (self.expense_accounts[0], 300, 0),
            (self.deferral_account, 900, 0),
        )
        deferral = self.generate_deferral_entries(options)[0]
        self.assert_invoice_lines(deferral, expected_values)

    def test_deferred_expense_manual_generation_inactive_account(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "month"
        )

        self.create_invoice([self.expense_lines[0]])
        self.expense_accounts[0].active = False

        options = self.get_options("2023-03-01", "2023-03-31")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000, 0, 500, 250, 750, 250),
                ("Total", 1000, 0, 500, 250, 750, 250),
            ],
            options,
        )

        entries = self.generate_deferral_entries(options)
        expected_values = [
            [self.expense_accounts[0], 0, 1000],
            [self.expense_accounts[0], 750, 0],
            [self.deferral_account, 250, 0],
        ]
        self.assert_invoice_lines(entries[0], expected_values)

    def test_deferred_expense_manual_generation_go_backwards_in_time(self):
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "month"
        )
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )

        options_august = self.get_options("2023-08-01", "2023-08-31")
        self.assertFalse(self.generate_deferral_entries(options_august).exists())

        self.create_invoice(
            [[self.expense_accounts[0], 600, "2023-07-01", "2023-09-30"]]
        )

        self.assertEqual(
            self.env["account.move.line"].search_count(
                [("account_id", "=", self.deferral_account.id)]
            ),
            0,
        )

        generated_entries_august = self.generate_deferral_entries(options_august)
        deferred_move_august = generated_entries_august[0]
        expected_values_august = (
            (self.expense_accounts[0], 0, 600),
            (self.expense_accounts[0], 400, 0),
            (self.deferral_account, 200, 0),
        )
        self.assert_invoice_lines(deferred_move_august, expected_values_august)

        self.assertFalse(self.generate_deferral_entries(options_august).exists())

        options_july = self.get_options("2023-07-01", "2023-07-31")
        generated_entries_july = self.generate_deferral_entries(options_july)
        self.assertRecordValues(
            generated_entries_july,
            [
                {
                    "state": "posted",
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-07-31"),
                },
                {
                    "state": "posted",
                    "move_type": "entry",
                    "date": fields.Date.to_date("2023-08-01"),
                },
            ],
        )
        deferred_move_july, reversed_deferred_move_july = generated_entries_july
        expected_values_july = (
            (self.expense_accounts[0], 0, 600),
            (self.expense_accounts[0], 200, 0),
            (self.deferral_account, 400, 0),
        )
        expected_values_july_reversed = (
            (self.expense_accounts[0], 600, 0),
            (self.expense_accounts[0], 0, 200),
            (self.deferral_account, 0, 400),
        )
        self.assert_invoice_lines(deferred_move_july, expected_values_july)
        self.assert_invoice_lines(
            reversed_deferred_move_july, expected_values_july_reversed
        )

        self.assertFalse(self.generate_deferral_entries(options_july).exists())

    def test_deferred_expense_manual_generation_single_period(self):
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "month"
        )
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )

        self.create_invoice(
            [[self.expense_accounts[0], 1000, "2023-02-01", "2023-02-28"]]
        )

        self.generate_deferral_entries(self.get_options("2023-01-01", "2023-01-31"))
        self.assertEqual(
            self.env["account.move.line"].search_count(
                [("account_id", "=", self.deferral_account.id)]
            ),
            2,
        )

    def test_deferred_expense_generation_lock_date(self):
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "month"
        )
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )

        move = self.create_invoice(
            [[self.expense_accounts[0], 1000, "2023-01-01", "2023-04-30"]]
        )

        move.company_id.account_config_id.fiscalyear_lock_date = fields.Date.to_date(
            "2023-02-28"
        )

        with self.assertRaisesRegex(
            UserError, "You cannot generate entries for a period that is locked."
        ):
            self.generate_deferral_entries(self.get_options("2023-01-01", "2023-01-31"))

    def test_deferred_expense_manual_generation_reset_to_draft(self):

        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "month"
        )
        move = self.create_invoice(
            [(self.expense_accounts[0], 1680, "2023-01-21", "2023-04-14")]
        )
        self.assertEqual(len(move.deferred_move_ids), 5)
        move.action_draft()
        self.assertFalse(move.deferred_move_ids)
        move.action_post()

        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )

        move.action_draft()
        self.assertFalse(move.deferred_move_ids)

        move3 = self.create_invoice(
            [(self.expense_accounts[0], 1680, "2023-03-21", "2023-06-14")]
        )
        self.generate_deferral_entries(self.get_options("2023-03-01", "2023-03-31"))
        move3.action_draft()
        self.assertFalse(move.deferred_move_ids)

        move4 = self.create_invoice(
            [(self.expense_accounts[0], 1680, "2023-03-21", "2023-06-14")]
        )
        move5 = self.create_invoice(
            [(self.expense_accounts[0], 1680, "2023-03-21", "2023-06-14")]
        )
        self.generate_deferral_entries(self.get_options("2023-03-01", "2023-03-31"))
        with self.assertRaisesRegex(
            UserError,
            "You cannot reset to draft an invoice that is grouped in deferral entry. You can create a credit note instead.",
        ):
            move4.action_draft()
        with self.assertRaisesRegex(
            UserError,
            "You cannot reset to draft an invoice that is grouped in deferral entry. You can create a credit note instead.",
        ):
            move5.action_draft()

    def test_deferred_expense_on_validation_generation_analytic_distribution(self):

        analytic_plan_a = self.env["account.analytic.plan"].create(
            {
                "name": "Plan A",
            }
        )
        aa_a1 = self.env["account.analytic.account"].create(
            {"name": "Account A1", "plan_id": analytic_plan_a.id}
        )
        aa_a2 = self.env["account.analytic.account"].create(
            {"name": "Account A2", "plan_id": analytic_plan_a.id}
        )
        move = self.create_invoice([self.expense_lines[0]], post=False)
        move.write(
            {
                "invoice_line_ids": [
                    Command.update(
                        move.invoice_line_ids.id,
                        {
                            "analytic_distribution": {
                                str(aa_a1.id): 60.0,
                                str(aa_a2.id): 40.0,
                            }
                        },
                    ),
                ]
            }
        )
        self.env["account.move.line"].flush_model()
        move.action_post()
        expected_analytic_distribution = {str(aa_a1.id): 60.0, str(aa_a2.id): 40.0}
        for line in move.deferred_move_ids.line_ids:
            self.assertEqual(line.analytic_distribution, expected_analytic_distribution)

    def test_deferred_expense_manual_generation_analytic_distribution(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )

        analytic_plan_a = self.env["account.analytic.plan"].create(
            {
                "name": "Plan A",
            }
        )
        analytic_plan_b = self.env["account.analytic.plan"].create(
            {
                "name": "Plan B",
            }
        )
        aa_a1 = self.env["account.analytic.account"].create(
            {"name": "Account A1", "plan_id": analytic_plan_a.id}
        )
        aa_a2 = self.env["account.analytic.account"].create(
            {"name": "Account A2", "plan_id": analytic_plan_a.id}
        )
        aa_a3 = self.env["account.analytic.account"].create(
            {"name": "Account A3", "plan_id": analytic_plan_a.id}
        )
        aa_b1 = self.env["account.analytic.account"].create(
            {"name": "Account B1", "plan_id": analytic_plan_b.id}
        )
        aa_b2 = self.env["account.analytic.account"].create(
            {"name": "Account B2", "plan_id": analytic_plan_b.id}
        )

        invoice_lines = [
            [self.expense_accounts[0], 1200, "2023-01-01", "2023-12-31"],
            [self.expense_accounts[0], 2400, "2023-01-01", "2023-12-31"],
            [self.expense_accounts[1], 1200, "2023-01-01", "2023-12-31"],
            [self.expense_accounts[1], 1200, "2023-01-01", "2023-12-31"],
        ]
        move = self.create_invoice(invoice_lines, post=False)
        move.write(
            {
                "invoice_line_ids": [
                    Command.update(
                        move.invoice_line_ids[0].id,
                        {
                            "analytic_distribution": {
                                str(aa_a1.id): 60.0,
                                str(aa_a2.id): 40.0,
                                str(aa_b1.id): 50.0,
                                str(aa_b2.id): 50.0,
                            }
                        },
                    ),
                    Command.update(
                        move.invoice_line_ids[1].id,
                        {"analytic_distribution": {str(aa_a1.id): 100.0}},
                    ),
                    Command.update(
                        move.invoice_line_ids[2].id,
                        {
                            "analytic_distribution": {
                                str(aa_a1.id): 50.0,
                                str(aa_a3.id): 50.0,
                            }
                        },
                    ),
                ]
            }
        )
        self.env["account.move.line"].flush_model()
        move.action_post()

        generated_entries = self.generate_deferral_entries(
            self.get_options("2023-01-01", "2023-08-31")
        )

        expected_analytic_distribution = {
            self.expense_accounts[0].id: {
                str(aa_a1.id): 86.67,
                str(aa_a2.id): 13.33,
                str(aa_b1.id): 16.67,
                str(aa_b2.id): 16.67,
            },
            self.expense_accounts[1].id: {str(aa_a1.id): 25.0, str(aa_a3.id): 25.0},
            self.deferral_account.id: {
                str(aa_a1.id): 62.0,
                str(aa_a2.id): 8.0,
                str(aa_b1.id): 10.0,
                str(aa_b2.id): 10.0,
                str(aa_a3.id): 10.0,
            },
        }
        expected_analytic_amount = [
            {
                aa_a1.id: (3120.12, 0.00),
                aa_a2.id: (479.88, 0.00),
                aa_b1.id: (0.00, 600.12),
                aa_b2.id: (0.00, 600.12),
            },
            {
                aa_a1.id: (-2080.08, 0.00),
                aa_a2.id: (-319.92, 0.00),
                aa_b1.id: (0.00, -400.08),
                aa_b2.id: (0.00, -400.08),
            },
            {
                aa_a1.id: (600.00, 0.00),
                aa_a3.id: (600.00, 0.00),
            },
            {
                aa_a1.id: (-400.00, 0.00),
                aa_a3.id: (-400.00, 0.00),
            },
            {
                aa_a1.id: (-1240.00, 0.00),
                aa_a2.id: (-160.00, 0.00),
                aa_a3.id: (-200.00, 0.00),
                aa_b1.id: (0.00, -200.00),
                aa_b2.id: (0.00, -200.00),
            },
        ]
        for index, line in enumerate(generated_entries[0].line_ids):
            self.assertEqual(
                line.analytic_distribution,
                expected_analytic_distribution[line.account_id.id],
            )
            for al in line.analytic_line_ids:
                fname_a = analytic_plan_a._column_name()
                fname_b = analytic_plan_b._column_name()
                fname, idx = (fname_a, 0) if al[fname_a] else (fname_b, 1)
                self.assertAlmostEqual(
                    al.amount, expected_analytic_amount[index][al[fname].id][idx]
                )
        for index, line in enumerate(generated_entries[1].line_ids):
            self.assertEqual(
                line.analytic_distribution,
                expected_analytic_distribution[line.account_id.id],
            )
            for al in line.analytic_line_ids:
                fname_a = analytic_plan_a._column_name()
                fname_b = analytic_plan_b._column_name()
                fname, idx = (fname_a, 0) if al[fname_a] else (fname_b, 1)
                self.assertAlmostEqual(
                    al.amount, -expected_analytic_amount[index][al[fname].id][idx]
                )

    def test_deferred_revenue_manual_generation_analytic_distribution(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        move = self.create_invoice(self.revenue_lines)
        analytic_plan = self.env["account.analytic.plan"].create({"name": "Plan"})
        analytic_account = self.env["account.analytic.account"].create(
            {
                "name": "Account",
                "plan_id": analytic_plan.id,
            }
        )
        move.invoice_line_ids[0]["analytic_distribution"] = {analytic_account.id: 100}
        options = self.get_options(
            "2023-02-01", "2023-02-28", report=self.deferred_revenue_report
        )
        options["analytic_accounts"] = [analytic_account.id]
        revenue_handler = self.env["account.deferred.revenue.report.handler"]
        deferral_move = self.generate_deferral_entries(
            options, report_handler=revenue_handler
        )[0]
        analytic_distributions = deferral_move.line_ids.mapped("analytic_distribution")
        expected_distributions = [{str(analytic_account.id): 100}] * 3
        self.assertEqual(analytic_distributions, expected_distributions)

    def test_deferred_expense_report_invalid_period(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        self.create_invoice([self.expense_lines[0]])

        options = self.get_options("2023-03-01", "2023-03-15")
        lines = self.get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6],
            [
                ("EXP0 Expense 0", 1000, 0, 500, 125, 625, 375),
                ("Total", 1000, 0, 500, 125, 625, 375),
            ],
            options,
        )

        with self.assertRaisesRegex(
            UserError,
            "You cannot generate entries for a period that does not end at the end of the month.",
        ):
            self.generate_deferral_entries(options)

    def audit_cell(self, options, line, column_name):
        audit_cell_res = self.handler.action_audit_cell(
            options,
            {
                "report_line_id": line["id"],
                "calling_line_dict_id": line["id"],
                "expression_label": column_name,
                "column_group_key": next(iter(options["column_groups"])),
            },
        )
        __, account_id = self.deferred_expense_report._get_model_info_from_id(
            line["id"]
        )
        return (
            self.env["account.move.line"]
            .search(audit_cell_res["domain"])
            .filtered(lambda l: l.account_id.id == account_id)
            .sorted(lambda l: (l.date, not l.deferred_start_date, l.id))
        )

    def get_audited_line_to_assert(self, date, balance):
        return {"date": fields.Date.to_date(date), "balance": balance}

    def test_deferred_expense_report_audit_cell_on_validation_mode(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "on_validation"
        )

        inv1 = self.create_invoice(
            [[self.expense_accounts[0], 1000, "2023-01-01", "2023-04-30"]]
        )
        inv2 = self.create_invoice(
            [[self.expense_accounts[0], 100, "2023-04-01", "2023-05-31"]]
        )
        inv3 = self.create_invoice(
            [
                [
                    self.expense_accounts[0],
                    10,
                    "2023-01-01",
                    "2023-02-28",
                ],
                [
                    self.expense_accounts[0],
                    1,
                    "2023-01-01",
                    "2023-05-31",
                ],
            ]
        )
        inv4 = self.create_invoice(
            [
                [
                    self.expense_accounts[0],
                    10000,
                    "2023-03-01",
                    "2023-04-30",
                ],
                [
                    self.expense_accounts[0],
                    1998,
                    "2023-03-01",
                    "2023-03-31",
                ],
            ],
            invoice_date="2023-03-01",
        )
        options = self.get_options("2023-03-01", "2023-03-31")
        lines = self.get_lines(options)

        audit_lines = self.audit_cell(options, lines[0], "total")
        self.assertEqual(
            audit_lines,
            inv1.invoice_line_ids
            + inv2.invoice_line_ids
            + inv3.invoice_line_ids.sorted("id")[1]
            + inv4.invoice_line_ids.sorted("id")[0],
        )

        audit_lines = self.audit_cell(options, lines[0], "not_started")
        self.assertEqual(audit_lines, inv2.invoice_line_ids)

        audit_lines = self.audit_cell(options, lines[0], "before").sorted("id")
        self.assertRecordValues(
            audit_lines,
            [
                self.get_audited_line_to_assert("2023-01-01", 1000),
                self.get_audited_line_to_assert("2023-01-01", -1000),
                self.get_audited_line_to_assert("2023-01-31", 250),
                self.get_audited_line_to_assert("2023-02-28", 250),
                self.get_audited_line_to_assert("2023-01-01", 100),
                self.get_audited_line_to_assert("2023-01-01", -100),
                self.get_audited_line_to_assert("2023-01-01", 1),
                self.get_audited_line_to_assert("2023-01-01", -10),
                self.get_audited_line_to_assert("2023-01-01", -1),
                self.get_audited_line_to_assert("2023-01-31", 5),
                self.get_audited_line_to_assert("2023-02-28", 5),
                self.get_audited_line_to_assert("2023-01-31", 0.2),
                self.get_audited_line_to_assert("2023-02-28", 0.2),
            ],
        )

        audit_lines = self.audit_cell(options, lines[0], "current")
        self.assertRecordValues(
            audit_lines,
            [
                self.get_audited_line_to_assert("2023-03-01", 10000),
                self.get_audited_line_to_assert("2023-03-01", -10000),
                self.get_audited_line_to_assert("2023-03-31", 250),
                self.get_audited_line_to_assert("2023-03-31", 0.2),
                self.get_audited_line_to_assert("2023-03-31", 5000),
            ],
        )

        audit_lines = self.audit_cell(options, lines[0], "later")
        self.assertRecordValues(
            audit_lines,
            [
                self.get_audited_line_to_assert("2023-04-30", 250),
                self.get_audited_line_to_assert("2023-04-30", 50),
                self.get_audited_line_to_assert("2023-04-30", 0.2),
                self.get_audited_line_to_assert("2023-04-30", 5000),
                self.get_audited_line_to_assert("2023-05-31", 50),
                self.get_audited_line_to_assert("2023-05-31", 0.2),
            ],
        )

    def test_deferred_expense_report_audit_cell_grouped_mode(self):

        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )

        inv1 = self.create_invoice(
            [[self.expense_accounts[0], 1000, "2023-01-01", "2023-04-30"]]
        )
        inv2 = self.create_invoice(
            [[self.expense_accounts[0], 100, "2023-04-01", "2023-05-31"]]
        )
        inv3 = self.create_invoice(
            [
                [
                    self.expense_accounts[0],
                    10,
                    "2023-01-01",
                    "2023-02-28",
                ],
                [
                    self.expense_accounts[0],
                    1,
                    "2023-01-01",
                    "2023-05-31",
                ],
            ]
        )
        inv4 = self.create_invoice(
            [
                [
                    self.expense_accounts[0],
                    10000,
                    "2023-03-01",
                    "2023-04-30",
                ],
                [
                    self.expense_accounts[0],
                    1998,
                    "2023-03-01",
                    "2023-03-31",
                ],
            ],
            invoice_date="2023-03-01",
        )
        options = self.get_options("2023-03-01", "2023-03-31")
        lines = self.get_lines(options)

        audit_lines = self.audit_cell(options, lines[0], "total")
        self.assertEqual(
            audit_lines,
            inv1.invoice_line_ids
            + inv2.invoice_line_ids
            + inv3.invoice_line_ids.sorted("id")[1]
            + inv4.invoice_line_ids.sorted("id")[0],
        )

        audit_lines = self.audit_cell(options, lines[0], "not_started")
        self.assertEqual(audit_lines, inv2.invoice_line_ids)

        audit_lines = self.audit_cell(options, lines[0], "before")
        self.assertRecordValues(
            audit_lines,
            [
                {"id": inv1.invoice_line_ids[0].id},
                {"id": inv3.invoice_line_ids[1].id},
            ],
        )

        audit_lines = self.audit_cell(options, lines[0], "current")
        self.assertRecordValues(
            audit_lines,
            [
                {"id": inv1.invoice_line_ids[0].id},
                {"id": inv3.invoice_line_ids[1].id},
                {"id": inv4.invoice_line_ids[0].id},
            ],
        )

        audit_lines = self.audit_cell(options, lines[0], "later")
        self.assertRecordValues(
            audit_lines,
            [
                {"id": inv1.invoice_line_ids.id},
                {"id": inv2.invoice_line_ids.id},
                {"id": inv3.invoice_line_ids.sorted("id")[1].id},
                {"id": inv4.invoice_line_ids.sorted("id")[0].id},
            ],
        )

        for report_date_from, report_date_to in (
            ("2023-01-01", "2023-01-31"),
            ("2023-02-01", "2023-02-28"),
            ("2023-03-01", "2023-03-31"),
        ):
            self.generate_deferral_entries(
                self.get_options(report_date_from, report_date_to)
            )
        lines = self.get_lines(options)

        audit_lines = self.audit_cell(options, lines[0], "total")
        self.assertEqual(
            audit_lines,
            inv1.invoice_line_ids
            + inv2.invoice_line_ids
            + inv3.invoice_line_ids.sorted("id")[1]
            + inv4.invoice_line_ids.sorted("id")[0],
        )

        audit_lines = self.audit_cell(options, lines[0], "not_started")
        self.assertEqual(audit_lines, inv2.invoice_line_ids)

        audit_lines = self.audit_cell(options, lines[0], "before")
        self.assertRecordValues(
            audit_lines[:3],
            [
                {"id": inv1.invoice_line_ids.id},
                {"id": inv2.invoice_line_ids.id},
                {"id": inv3.invoice_line_ids[1].id},
            ],
        )
        self.assertRecordValues(
            audit_lines[3:],
            [
                self.get_audited_line_to_assert("2023-01-31", -1111),
                self.get_audited_line_to_assert("2023-01-31", 255.2),
                self.get_audited_line_to_assert("2023-02-01", 1111),
                self.get_audited_line_to_assert("2023-02-01", -255.2),
                self.get_audited_line_to_assert("2023-02-28", -1111),
                self.get_audited_line_to_assert("2023-02-28", 510.4),
            ],
        )

        audit_lines = self.audit_cell(options, lines[0], "current")
        self.assertRecordValues(
            audit_lines,
            [
                self.get_audited_line_to_assert("2023-03-01", 10000),
                self.get_audited_line_to_assert("2023-03-01", 1111),
                self.get_audited_line_to_assert("2023-03-01", -510.4),
                self.get_audited_line_to_assert("2023-03-31", -11101),
                self.get_audited_line_to_assert("2023-03-31", 5750.6),
            ],
        )

        audit_lines = self.audit_cell(options, lines[0], "later")
        self.assertRecordValues(
            audit_lines,
            [
                self.get_audited_line_to_assert("2023-04-01", 11101),
                self.get_audited_line_to_assert("2023-04-01", -5750.6),
            ],
        )

        self.generate_deferral_entries(self.get_options("2023-04-01", "2023-04-30"))
        audit_lines = self.audit_cell(options, lines[0], "later")
        self.assertRecordValues(
            audit_lines,
            [
                self.get_audited_line_to_assert("2023-04-01", 11101),
                self.get_audited_line_to_assert("2023-04-01", -5750.6),
                self.get_audited_line_to_assert("2023-04-30", -11101),
                self.get_audited_line_to_assert("2023-04-30", 11050.8),
                self.get_audited_line_to_assert("2023-05-01", 11101),
                self.get_audited_line_to_assert("2023-05-01", -11050.8),
            ],
        )

        inv5 = self.create_invoice(
            [[self.expense_accounts[0], 100000, "2023-01-01", "2023-05-31"]]
        )

        for report_date_from, report_date_to in (
            ("2023-01-01", "2023-01-31"),
            ("2023-02-01", "2023-02-28"),
        ):
            self.generate_deferral_entries(
                self.get_options(report_date_from, report_date_to)
            )

        options = self.get_options("2023-03-01", "2023-03-31")
        lines = self.get_lines(options)

        audit_lines = self.audit_cell(options, lines[0], "total")
        self.assertEqual(
            audit_lines,
            inv1.invoice_line_ids
            + inv2.invoice_line_ids
            + inv3.invoice_line_ids.sorted("id")[1]
            + inv4.invoice_line_ids.sorted("id")[0]
            + inv5.invoice_line_ids,
        )

        audit_lines = self.audit_cell(options, lines[0], "not_started")
        self.assertEqual(audit_lines, inv2.invoice_line_ids)

        audit_lines = self.audit_cell(options, lines[0], "before")
        self.assertRecordValues(
            audit_lines[:4],
            [
                {"id": inv1.invoice_line_ids.id},
                {"id": inv2.invoice_line_ids.id},
                {"id": inv3.invoice_line_ids[1].id},
                {"id": inv5.invoice_line_ids.id},
            ],
        )
        self.assertRecordValues(
            audit_lines[4:],
            [
                self.get_audited_line_to_assert("2023-01-31", -1111),
                self.get_audited_line_to_assert("2023-01-31", 255.2),
                self.get_audited_line_to_assert("2023-01-31", -100000),
                self.get_audited_line_to_assert("2023-01-31", 20000),
                self.get_audited_line_to_assert("2023-02-01", 1111),
                self.get_audited_line_to_assert("2023-02-01", -255.2),
                self.get_audited_line_to_assert("2023-02-01", 100000),
                self.get_audited_line_to_assert("2023-02-01", -20000),
                self.get_audited_line_to_assert("2023-02-28", -1111),
                self.get_audited_line_to_assert("2023-02-28", 510.4),
                self.get_audited_line_to_assert("2023-02-28", -100000),
                self.get_audited_line_to_assert("2023-02-28", 40000),
            ],
        )

        audit_lines = self.audit_cell(options, lines[0], "current")
        self.assertRecordValues(
            audit_lines,
            [
                self.get_audited_line_to_assert("2023-03-01", 10000),
                self.get_audited_line_to_assert("2023-03-01", 1111),
                self.get_audited_line_to_assert("2023-03-01", -510.4),
                self.get_audited_line_to_assert("2023-03-01", 100000),
                self.get_audited_line_to_assert("2023-03-01", -40000),
                self.get_audited_line_to_assert("2023-03-31", -11101),
                self.get_audited_line_to_assert("2023-03-31", 5750.6),
            ],
        )

        self.generate_deferral_entries(self.get_options("2023-03-01", "2023-03-31"))

        audit_lines = self.audit_cell(options, lines[0], "current")
        self.assertRecordValues(
            audit_lines,
            [
                self.get_audited_line_to_assert("2023-03-01", 10000),
                self.get_audited_line_to_assert("2023-03-01", 1111),
                self.get_audited_line_to_assert("2023-03-01", -510.4),
                self.get_audited_line_to_assert("2023-03-01", 100000),
                self.get_audited_line_to_assert("2023-03-01", -40000),
                self.get_audited_line_to_assert("2023-03-31", -11101),
                self.get_audited_line_to_assert("2023-03-31", 5750.6),
                self.get_audited_line_to_assert("2023-03-31", -100000),
                self.get_audited_line_to_assert("2023-03-31", 60000),
            ],
        )
