from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account_loans import _account_loans_add_date_column


@tagged("post_install", "-at_install")
class TestLoanManagement(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loan_journal = cls.env["account.journal"].search(
            [
                ("company_id", "=", cls.company.id),
                ("type", "=", "general"),
                (
                    "id",
                    "!=",
                    cls.company.account_config_id.currency_exchange_journal_id.id,
                ),
            ],
            limit=1,
        )
        cls.long_term_account = cls.env["account.account"].search(
            [
                ("company_ids", "=", cls.company.id),
                ("account_type", "=", "liability_non_current"),
            ],
            limit=1,
        )
        cls.short_term_account = cls.env["account.account"].search(
            [
                ("company_ids", "=", cls.company.id),
                ("account_type", "=", "liability_current"),
            ],
            limit=1,
        )
        cls.expense_account = cls.env["account.account"].search(
            [
                ("company_ids", "=", cls.company.id),
                ("account_type", "=", "expense"),
                (
                    "id",
                    "!=",
                    cls.company.account_config_id.account_journal_early_pay_discount_loss_account_id.id,
                ),
            ],
            limit=1,
        )

    def create_loan(
        self,
        name,
        date,
        duration,
        amount_borrowed,
        interest,
        validate=False,
        skip_until_date=False,
    ):
        loan = self.env["account.loan"].create(
            {
                "name": name,
                "date": date,
                "duration": duration,
                "amount_borrowed": amount_borrowed,
                "interest": interest,
                "skip_until_date": skip_until_date,
                "journal_id": self.loan_journal.id,
                "long_term_account_id": self.long_term_account.id,
                "short_term_account_id": self.short_term_account.id,
                "expense_account_id": self.expense_account.id,
                "line_ids": [
                    Command.create(
                        {
                            "date": fields.Date.to_date(date)
                            + relativedelta(months=month),
                            "principal": amount_borrowed / duration,
                            "interest": interest / duration,
                        }
                    )
                    for month in range(duration)
                ],
            }
        )
        if validate:
            loan.action_confirm()
        return loan

    @freeze_time("2024-07-31")
    def test_loan_values(self):
        loan = self.create_loan(
            "Odoomobile Loan 🚗", "2024-01-01", 2 * 12, 24_000, 2_400, validate=True
        )

        self.assertEqual(loan.outstanding_balance, 17_000)

        self.assertEqual(len(loan.line_ids), 24)
        self.assertRecordValues(
            loan.line_ids[0] | loan.line_ids[4] | loan.line_ids[-1],
            [
                {
                    "date": fields.Date.to_date("2024-01-01"),
                    "principal": 1_000,
                    "interest": 100,
                    "payment": 1_100,
                    "outstanding_balance": 23_000,
                },
                {
                    "date": fields.Date.to_date("2024-05-01"),
                    "principal": 1_000,
                    "interest": 100,
                    "payment": 1_100,
                    "outstanding_balance": 19_000,
                },
                {
                    "date": fields.Date.to_date("2025-12-01"),
                    "principal": 1_000,
                    "interest": 100,
                    "payment": 1_100,
                    "outstanding_balance": 0,
                },
            ],
        )

        payment_moves = loan.line_ids.generated_move_ids.filtered(
            lambda m: len(m.line_ids) == 3
        )
        self.assertEqual(len(payment_moves), 24)
        reclassification_moves = (
            loan.line_ids.generated_move_ids - payment_moves
        ).filtered(lambda m: not m.reversed_entry_id)
        self.assertEqual(len(reclassification_moves), 23)
        reclassification_reverse_moves = (
            loan.line_ids.generated_move_ids - payment_moves
        ) - reclassification_moves
        self.assertEqual(len(reclassification_reverse_moves), 23)

        self.assertRecordValues(
            payment_moves[0]
            | payment_moves[11]
            | payment_moves[15]
            | payment_moves[-1],
            [
                {
                    "date": fields.Date.to_date("2024-01-31"),
                    "ref": "Odoomobile Loan 🚗 - Principal & Interest 01/2024",
                    "amount_total": 1_100,
                    "generating_loan_line_id": loan.line_ids[0].id,
                },
                {
                    "date": fields.Date.to_date("2024-12-31"),
                    "ref": "Odoomobile Loan 🚗 - Principal & Interest 12/2024",
                    "amount_total": 1_100,
                    "generating_loan_line_id": loan.line_ids[11].id,
                },
                {
                    "date": fields.Date.to_date("2025-04-30"),
                    "ref": "Odoomobile Loan 🚗 - Principal & Interest 04/2025",
                    "amount_total": 1_100,
                    "generating_loan_line_id": loan.line_ids[15].id,
                },
                {
                    "date": fields.Date.to_date("2025-12-31"),
                    "ref": "Odoomobile Loan 🚗 - Principal & Interest 12/2025",
                    "amount_total": 1_100,
                    "generating_loan_line_id": loan.line_ids[-1].id,
                },
            ],
        )

        self.assertRecordValues(
            payment_moves[0].line_ids.sorted(lambda l: -l.debit),
            [
                {
                    "name": "Odoomobile Loan 🚗 - Principal 01/2024",
                    "debit": 1_000,
                    "credit": 0,
                    "account_id": self.long_term_account.id,
                },
                {
                    "name": "Odoomobile Loan 🚗 - Interest 01/2024",
                    "debit": 100,
                    "credit": 0,
                    "account_id": self.expense_account.id,
                },
                {
                    "name": "Odoomobile Loan 🚗 - Due 01/2024 (Principal $ 1,000.00 + Interest $ 100.00)",
                    "debit": 0,
                    "credit": 1_100,
                    "account_id": self.short_term_account.id,
                },
            ],
        )

        self.assertRecordValues(
            reclassification_moves[0]
            | reclassification_moves[11]
            | reclassification_moves[15],
            [
                {
                    "date": fields.Date.to_date("2024-01-31"),
                    "ref": "Odoomobile Loan 🚗 - Reclassification LT - ST 02/2024 to 01/2025",
                    "amount_total": 12_000,
                    "generating_loan_line_id": loan.line_ids[0].id,
                },
                {
                    "date": fields.Date.to_date("2024-12-31"),
                    "ref": "Odoomobile Loan 🚗 - Reclassification LT - ST 01/2025 to 12/2025",
                    "amount_total": 12_000,
                    "generating_loan_line_id": loan.line_ids[11].id,
                },
                {
                    "date": fields.Date.to_date("2025-04-30"),
                    "ref": "Odoomobile Loan 🚗 - Reclassification LT - ST 05/2025 to 12/2025",
                    "amount_total": 8_000,
                    "generating_loan_line_id": loan.line_ids[15].id,
                },
            ],
        )

        self.assertRecordValues(
            reclassification_moves[0].line_ids.sorted(lambda l: l.credit),
            [
                {
                    "name": f"Odoomobile Loan 🚗 - Reclassification LT - ST 02/2024 to 01/2025 (To {self.short_term_account.code})",
                    "debit": 12_000,
                    "credit": 0,
                    "account_id": self.long_term_account.id,
                },
                {
                    "name": f"Odoomobile Loan 🚗 - Reclassification LT - ST 02/2024 to 01/2025 (From {self.long_term_account.code})",
                    "debit": 0,
                    "credit": 12_000,
                    "account_id": self.short_term_account.id,
                },
            ],
        )

        self.assertRecordValues(
            reclassification_reverse_moves[0]
            | reclassification_reverse_moves[11]
            | reclassification_reverse_moves[15],
            [
                {
                    "date": fields.Date.to_date("2024-02-01"),
                    "ref": "Odoomobile Loan 🚗 - Reversal reclassification LT - ST 02/2024 to 01/2025",
                    "amount_total": 12_000,
                    "generating_loan_line_id": loan.line_ids[0].id,
                },
                {
                    "date": fields.Date.to_date("2025-01-01"),
                    "ref": "Odoomobile Loan 🚗 - Reversal reclassification LT - ST 01/2025 to 12/2025",
                    "amount_total": 12_000,
                    "generating_loan_line_id": loan.line_ids[11].id,
                },
                {
                    "date": fields.Date.to_date("2025-05-01"),
                    "ref": "Odoomobile Loan 🚗 - Reversal reclassification LT - ST 05/2025 to 12/2025",
                    "amount_total": 8_000,
                    "generating_loan_line_id": loan.line_ids[15].id,
                },
            ],
        )

        self.assertRecordValues(
            reclassification_reverse_moves[0].line_ids.sorted(lambda l: l.debit),
            [
                {
                    "name": f"Odoomobile Loan 🚗 - Reversal reclassification LT - ST 02/2024 to 01/2025 (To {self.short_term_account.code})",
                    "credit": 12_000,
                    "debit": 0,
                    "account_id": self.long_term_account.id,
                },
                {
                    "name": f"Odoomobile Loan 🚗 - Reversal reclassification LT - ST 02/2024 to 01/2025 (From {self.long_term_account.code})",
                    "credit": 0,
                    "debit": 12_000,
                    "account_id": self.short_term_account.id,
                },
            ],
        )

    @freeze_time("2024-07-31")
    def test_loan_states(self):
        loan = self.create_loan("Odoomobile Loan 🚗", "2024-01-01", 12, 24_000, 2_400)

        self.assertEqual(loan.state, "draft")
        self.assertFalse(loan.line_ids.generated_move_ids)

        loan.action_confirm()
        self.assertEqual(loan.state, "running")
        self.assertTrue(loan.line_ids.generated_move_ids)
        self.assertTrue(
            any(m.state == "posted" for m in loan.line_ids.generated_move_ids)
            and any(m.state == "draft" for m in loan.line_ids.generated_move_ids)
        )

        loan.action_cancel()
        self.assertEqual(loan.state, "cancelled")
        self.assertFalse(loan.line_ids.generated_move_ids)

        loan.action_set_to_draft()
        self.assertEqual(loan.state, "draft")
        self.assertFalse(loan.line_ids.generated_move_ids)

        loan.action_confirm()
        self.assertEqual(loan.state, "running")
        self.assertTrue(loan.line_ids.generated_move_ids)

        action = loan.action_close()
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        wizard.date = fields.Date.to_date("2024-10-31")
        wizard.action_save()
        self.assertEqual(loan.state, "closed")
        self.assertEqual(len(loan.line_ids.generated_move_ids), 30)

        loan.action_set_to_draft()
        self.assertEqual(loan.state, "draft")
        self.assertFalse(loan.line_ids.generated_move_ids)

        loan2 = self.create_loan(
            "Odoomobile Loan 🚗", "2024-01-01", 12, 24_000, 2_400, validate=True
        )
        self.assertEqual(loan2.state, "running")
        with freeze_time("2024-12-31"), self.sync_env_with_side_cursors():
            self.env.ref(
                "account.ir_cron_auto_post_draft_entry"
            ).method_direct_trigger()
            self.assertEqual(loan2.state, "closed")

    @freeze_time("2024-06-23")
    def test_loan_states_with_audit_trail(self):
        self.company.account_config_id.restrictive_audit_trail = True
        loan = self.create_loan("Odoomobile Loan 🚗", "2024-01-01", 12, 24_000, 2_400)

        self.assertEqual(loan.state, "draft")
        self.assertFalse(loan.line_ids.generated_move_ids)

        loan.action_confirm()
        self.assertEqual(loan.state, "running")
        self.assertEqual(
            len(
                loan.line_ids.generated_move_ids.filtered(lambda m: m.state == "posted")
            ),
            15,
        )
        self.assertEqual(len(loan.line_ids.generated_move_ids), 34)

        loan.action_cancel()
        self.assertEqual(loan.state, "cancelled")
        self.assertFalse(
            len(
                loan.line_ids.generated_move_ids.filtered(lambda m: m.state == "posted")
            )
        )
        self.assertEqual(len(loan.line_ids.generated_move_ids), 15)

        loan.action_set_to_draft()
        self.assertEqual(loan.state, "draft")
        self.assertEqual(len(loan.line_ids.generated_move_ids), 15)

        loan.action_confirm()
        self.assertEqual(loan.state, "running")
        self.assertEqual(
            len(
                loan.line_ids.generated_move_ids.filtered(lambda m: m.state == "posted")
            ),
            15,
        )
        self.assertEqual(len(loan.line_ids.generated_move_ids), 49)

        action = loan.action_close()
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        wizard.action_save()
        self.assertEqual(loan.state, "closed")
        self.assertEqual(
            len(
                loan.line_ids.generated_move_ids.filtered(lambda m: m.state == "posted")
            ),
            15,
        )
        self.assertEqual(len(loan.line_ids.generated_move_ids), 33)

        loan.action_set_to_draft()
        self.assertEqual(loan.state, "draft")
        self.assertFalse(
            len(
                loan.line_ids.generated_move_ids.filtered(lambda m: m.state == "posted")
            )
        )
        self.assertEqual(len(loan.line_ids.generated_move_ids), 30)

    @freeze_time("2024-01-01")
    def test_loan_import_amortization_schedule(self):
        with file_open(
            "account_loans/demo/files/loan_amortization_demo.csv", "rb"
        ) as f:
            attachment = self.env["ir.attachment"].create(
                {
                    "name": "loan_amortization_demo.csv",
                    "raw": f.read(),
                }
            )
            attachment = _account_loans_add_date_column(attachment)

        action = self.env["account.loan"].action_upload_amortization_schedule(
            attachment.id
        )
        loan = self.env["account.loan"].browse(
            action.get("params", {}).get("context", {}).get("default_loan_id")
        )
        import_wizard = self.env["base_import.import"].browse(
            action.get("params", {}).get("context", {}).get("wizard_id")
        )
        result = import_wizard.parse_preview(
            {
                "quoting": '"',
                "separator": ",",
                "date_format": "%Y-%m-%d",
                "has_headers": True,
            }
        )
        import_wizard.with_context(default_loan_id=loan.id).execute_import(
            ["date", "principal", "interest"],
            [],
            result["options"],
        )
        loan.action_file_uploaded()
        loan.write(
            {
                "journal_id": self.loan_journal.id,
                "long_term_account_id": self.long_term_account.id,
                "short_term_account_id": self.short_term_account.id,
                "expense_account_id": self.expense_account.id,
            }
        )
        loan.action_confirm()

        self.assertRecordValues(
            loan,
            [
                {
                    "date": fields.Date.from_string("2023-01-01"),
                    "state": "running",
                    "name": attachment.name,
                    "amount_borrowed": 19_900.25,
                    "outstanding_balance": 15_981.65,
                }
            ],
        )

        self.assertEqual(len(loan.line_ids), 48)
        self.assertRecordValues(
            loan.line_ids[0] | loan.line_ids[-1],
            [
                {
                    "date": fields.Date.from_string("2023-01-01"),
                    "principal": 304.60,
                    "interest": 250.00,
                    "payment": 554.6,
                    "outstanding_balance": 19_595.65,
                },
                {
                    "date": fields.Date.from_string("2026-12-01"),
                    "principal": 547.72,
                    "interest": 6.88,
                    "payment": 554.6,
                    "outstanding_balance": 0,
                },
            ],
        )

        loan2 = self.create_loan(
            "Loan 2", "2024-01-01", 2 * 12, 24_000, 2_400, validate=True
        )
        self.assertEqual(len(loan2.line_ids), 24)

        with self.assertRaises(UserError):
            loan2.action_upload_amortization_schedule(attachment.id)
        loan2.action_set_to_draft()

        action = loan2.action_upload_amortization_schedule(attachment.id)
        self.assertEqual(
            action.get("params", {}).get("context", {}).get("default_loan_id"), loan2.id
        )
        import_wizard = self.env["base_import.import"].browse(
            action.get("params", {}).get("context", {}).get("wizard_id")
        )
        result = import_wizard.parse_preview(
            {
                "quoting": '"',
                "separator": ",",
                "date_format": "%Y-%m-%d",
                "has_headers": True,
            }
        )
        import_wizard.with_context(default_loan_id=loan2.id).execute_import(
            ["date", "principal", "interest"],
            [],
            result["options"],
        )
        loan2.action_file_uploaded()
        loan2.action_confirm()

        self.assertRecordValues(
            loan,
            [
                {
                    "date": fields.Date.from_string("2023-01-01"),
                    "state": "running",
                    "name": attachment.name,
                    "amount_borrowed": 19_900.25,
                    "outstanding_balance": 15_981.65,
                }
            ],
        )

        self.assertEqual(len(loan.line_ids), 48)
        self.assertRecordValues(
            loan.line_ids[0] | loan.line_ids[-1],
            [
                {
                    "date": fields.Date.from_string("2023-01-01"),
                    "principal": 304.60,
                    "interest": 250.00,
                    "payment": 554.6,
                    "outstanding_balance": 19_595.65,
                },
                {
                    "date": fields.Date.from_string("2026-12-01"),
                    "principal": 547.72,
                    "interest": 6.88,
                    "payment": 554.6,
                    "outstanding_balance": 0,
                },
            ],
        )

    def test_loan_zero_interest(self):
        loan = self.env["account.loan"].create(
            {"name": "0 interest loan", "date": "2024-01-01", "amount_borrowed": 24_000}
        )
        wizard = self.env["wizard.account.loan.create.schedule"].browse(
            loan.action_view_compute_wizard()["res_id"]
        )
        wizard.interest_rate = 0
        wizard.action_save()
        self.assertEqual(len(loan.line_ids), 12)
        self.assertTrue(
            all(payment == 2000 for payment in loan.line_ids.mapped("payment"))
        )

    @freeze_time("2024-07-31")
    def test_loan_skip_until_date(self):
        loan = self.create_loan(
            "Odoomobile Loan 🚗",
            "2024-01-01",
            12,
            24_000,
            2_400,
            validate=True,
            skip_until_date="2024-05-15",
        )

        self.assertEqual(loan.state, "running")
        self.assertTrue(loan.line_ids.generated_move_ids)
        self.assertEqual(loan.outstanding_balance, 10_000)

    @freeze_time("2025-01-01")
    def test_loan_skip_until_date_2(self):
        loan = self.env["account.loan"].create(
            {
                "name": "Test",
                "date": "2024-01-01",
                "duration": 12,
                "amount_borrowed": 20_000,
                "interest": 107.87,
                "skip_until_date": "2024-10-31",
                "journal_id": self.loan_journal.id,
                "long_term_account_id": self.long_term_account.id,
                "short_term_account_id": self.short_term_account.id,
                "expense_account_id": self.expense_account.id,
            }
        )

        wizard = self.env["wizard.account.loan.create.schedule"].browse(
            loan.action_view_compute_wizard()["res_id"]
        )
        wizard.action_save()
        loan.action_confirm()

        self.assertTrue(loan.line_ids.generated_move_ids)
        self.assertEqual(loan.state, "closed")
