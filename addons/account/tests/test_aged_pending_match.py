from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon


@tagged("post_install", "-at_install")
class TestAgedPendingMatch(TestAccountReportsCommon):
    def test_aged_payable_equals_the_ledger_and_explains_the_advance(self):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-01-05",
                "invoice_line_ids": [
                    Command.create(
                        {"name": "pending", "price_unit": 1000.0, "tax_ids": []}
                    )
                ],
            }
        )
        st_line = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.company_data["default_journal_bank"].id,
                "date": "2019-01-03",
                "payment_ref": "advance",
                "partner_id": self.partner_a.id,
                "amount": -1000.0,
            }
        )
        st_line.set_line_bank_statement_line(
            bill.line_ids.filtered(lambda line: line.display_type == "payment_term").ids
        )
        report = self.env.ref("account.aged_payable_report")
        options = self._generate_options(
            report,
            fields.Date.from_string("2019-01-31"),
            fields.Date.from_string("2019-01-31"),
        )
        columns = [column["expression_label"] for column in options["columns"]]
        partner_line = next(
            (
                line
                for line in report._get_lines(options)
                if line["name"] == self.partner_a.display_name
            ),
            {"columns": [{"no_format": 0.0} for _label in columns]},
        )
        values = {
            label: column["no_format"]
            for label, column in zip(columns, partner_line["columns"], strict=True)
        }

        ledger = -sum(
            self.env["account.move.line"]
            .search(
                [
                    ("partner_id", "=", self.partner_a.id),
                    ("account_id.account_type", "=", "liability_payable"),
                    ("parent_state", "=", "posted"),
                ]
            )
            .mapped("balance")
        )
        self.assertEqual(values["total"], ledger)
        self.assertEqual(values["total"], -1000.0)
        self.assertEqual(values["pending_match"], -1000.0)

    def test_aged_payable_is_the_trade_payable_ledger(self):
        payable = self.company_data["default_account_payable"]
        non_trade = payable.copy({"code": "211NT", "non_trade": True})
        expense = self.company_data["default_account_expense"]

        def entry(account, amount, partner=None):
            move = self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "date": "2019-01-10",
                    "line_ids": [
                        Command.create(
                            {
                                "account_id": account.id,
                                "partner_id": partner and partner.id,
                                "balance": -amount,
                            }
                        ),
                        Command.create({"account_id": expense.id, "balance": amount}),
                    ],
                }
            )
            move.action_post()
            return move

        entry(payable, 1000.0, self.partner_a)
        entry(payable, 300.0)
        entry(non_trade, 500.0, self.partner_a)
        report = self.env.ref("account.aged_payable_report")
        options = self._generate_options(
            report,
            fields.Date.from_string("2019-01-31"),
            fields.Date.from_string("2019-01-31"),
        )
        options["unfold_all"] = True
        columns = [column["expression_label"] for column in options["columns"]]
        totals = {
            line["name"]: dict(
                zip(
                    columns,
                    [column["no_format"] for column in line["columns"]],
                    strict=True,
                )
            )["total"]
            for line in report._get_lines(options)
        }

        trade_ledger = -sum(
            self.env["account.move.line"]
            .search(
                [
                    ("company_id", "=", self.env.company.id),
                    ("parent_state", "=", "posted"),
                    ("account_id.account_type", "=", "liability_payable"),
                    ("account_id.non_trade", "=", False),
                ]
            )
            .mapped("amount_residual")
        )
        self.assertEqual(totals["Total Aged Payable"], trade_ledger)
        self.assertEqual(totals["Total Aged Payable"], 1300.0)
        self.assertEqual(totals[self.partner_a.display_name], 1000.0)
        self.assertEqual(totals["Unknown"], 300.0, "a partner-less line counts")
