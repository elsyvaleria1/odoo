from datetime import datetime, time

from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.digest.tests.common import TestDigestCommon


@tagged("post_install", "-at_install")
class TestAccountDigest(TestDigestCommon):
    @classmethod
    @mute_logger("odoo.models.unlink")
    def setUpClass(cls):
        super().setUpClass()
        account1 = cls.env["account.account"].search(
            [("internal_group", "=", "income"), ("company_ids", "=", cls.company_1.id)],
            limit=1,
        )
        account2 = cls.env["account.account"].search(
            [
                ("internal_group", "=", "expense"),
                ("company_ids", "=", cls.company_1.id),
            ],
            limit=1,
        )
        cls.env["account.journal"].with_company(cls.company_2).create(
            {
                "name": "Test Journal",
                "code": "code",
                "type": "general",
            }
        )

        comp2_account, comp2_account2 = cls.env["account.account"].create(
            [
                {
                    "name": "Account 1 Company 2",
                    "account_type": "expense_depreciation",
                    "code": "aaaaaa",
                    "company_ids": [Command.link(cls.company_2.id)],
                },
                {
                    "name": "Account 2 Company 2",
                    "account_type": "income_other",
                    "code": "bbbbbb",
                    "company_ids": [Command.link(cls.company_2.id)],
                },
            ]
        )

        cls.env["account.move"].search([]).state = "draft"

        moves = cls.env["account.move"].create(
            {
                "line_ids": [
                    (0, 0, {"debit": 5, "credit": 0, "account_id": account1.id}),
                    (0, 0, {"debit": 0, "credit": 5, "account_id": account2.id}),
                    (0, 0, {"debit": 8, "credit": 0, "account_id": account1.id}),
                    (0, 0, {"debit": 0, "credit": 8, "account_id": account2.id}),
                ],
            }
        )

        moves |= (
            cls.env["account.move"]
            .with_company(cls.company_2)
            .create(
                {
                    "line_ids": [
                        (
                            0,
                            0,
                            {"debit": 0, "credit": 2, "account_id": comp2_account.id},
                        ),
                        (
                            0,
                            0,
                            {"debit": 2, "credit": 0, "account_id": comp2_account2.id},
                        ),
                    ],
                }
            )
        )

        moves.state = "posted"

    def test_kpi_account_total_revenue_value(self):
        self.assertEqual(int(self.digest_1.kpi_account_total_revenue_value), -13)
        self.assertEqual(int(self.digest_2.kpi_account_total_revenue_value), -2)
        self.assertEqual(int(self.digest_3.kpi_account_total_revenue_value), -13)

        self.digest_3.invalidate_recordset()
        self.assertEqual(
            int(
                self.digest_3.with_company(
                    self.company_2
                ).kpi_account_total_revenue_value
            ),
            -2,
            msg="When no company is set, the KPI must be computed based on the current company",
        )

    def test_account_kpis_read_the_same_days(self):
        self.env.user.group_ids = [
            Command.link(self.env.ref("account.group_account_user").id)
        ]
        today = fields.Date.today()
        yesterday = today - relativedelta(days=1)
        income = self.env["account.account"].search(
            [
                ("internal_group", "=", "income"),
                ("company_ids", "=", self.company_1.id),
            ],
            limit=1,
        )
        receivable = self.env["account.account"].search(
            [
                ("account_type", "=", "asset_receivable"),
                ("company_ids", "=", self.company_1.id),
            ],
            limit=1,
        )
        for date, amount in ((yesterday, 40.0), (today, 7.0)):
            self.env["account.move"].create(
                {
                    "date": date,
                    "line_ids": [
                        Command.create({"account_id": income.id, "balance": -amount}),
                        Command.create(
                            {"account_id": receivable.id, "balance": amount}
                        ),
                    ],
                }
            ).action_post()

        bank = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.company_1.id)], limit=1
        )
        credit = self.env["account.journal"].create(
            {"name": "Digest card", "type": "credit", "company_id": self.company_1.id}
        )
        Line = self.env["account.bank.statement.line"]
        for journal, date, amount in (
            (bank, yesterday, 100.0),
            (credit, yesterday, 30.0),
            (bank, today, 7.0),
        ):
            Line.create(
                {
                    "journal_id": journal.id,
                    "date": date,
                    "payment_ref": "digest",
                    "amount": amount,
                }
            )
        cancelled = Line.create(
            {
                "journal_id": bank.id,
                "date": yesterday,
                "payment_ref": "cancelled",
                "amount": 1000.0,
            }
        )
        cancelled.move_id.action_draft()
        cancelled.move_id.action_cancel()

        digest = self.digest_1.with_context(
            start_datetime=datetime.combine(yesterday, time(10)),
            end_datetime=datetime.combine(today, time(10)),
        )
        digest.invalidate_recordset()
        self.assertEqual(digest.kpi_account_total_revenue_value, 40.0)
        self.assertEqual(digest.kpi_account_bank_cash_value, 130.0)
