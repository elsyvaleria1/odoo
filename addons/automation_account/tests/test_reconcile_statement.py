from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests.common import tagged

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestReconcileStatement(AutomationAccountCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.move = cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": cls.partner.id,
                "journal_id": cls.journal_sale.id,
                "invoice_date": "2026-08-20",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Reconcile me",
                            "quantity": 1,
                            "price_unit": 100.0,
                            "account_id": cls.account_income.id,
                            "tax_ids": [],
                        },
                    ),
                ],
            },
        )
        cls.move.action_post()

        statement_line = cls.env["account.bank.statement.line"].create(
            {
                "journal_id": cls.journal_bank.id,
                "date": "2026-08-21",
                "payment_ref": "Automation statement line",
                "partner_id": cls.partner.id,
                "amount": 100.0,
            },
        )
        cls.st_line = statement_line

    def setUp(self):
        super().setUp()
        self.step = self._make_step("pass")
        self.runtime = self._make_runtime()
        self.line = self.runtime.line_ids

    def test_a_programming_error_reaches_the_caller_unconverted(self):
        boom = AttributeError(
            "'account.bank.statement.line' object has no attribute "
            "'set_line_bank_statement_line'",
        )

        with patch.object(
            type(self.st_line),
            "set_line_bank_statement_line",
            side_effect=boom,
        ):
            with self.assertRaises(AttributeError):
                self.step.reconcile_statement_with_move(
                    self.line,
                    self.st_line,
                    self.move,
                )

    def test_the_business_guards_still_raise_user_errors(self):
        draft = self.move.copy()

        with self.assertRaises(UserError):
            self.step.reconcile_statement_with_move(self.line, self.st_line, draft)

    def test_a_move_with_no_open_receivable_line_is_refused(self):
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.journal_bank.id,
                "date": "2026-08-21",
                "line_ids": [
                    Command.create(
                        {
                            "name": "debit",
                            "account_id": self.account_income.id,
                            "debit": 50.0,
                        },
                    ),
                    Command.create(
                        {
                            "name": "credit",
                            "account_id": self.account_income.id,
                            "credit": 50.0,
                        },
                    ),
                ],
            },
        )
        entry.action_post()

        with self.assertRaises(UserError):
            self.step.reconcile_statement_with_move(self.line, self.st_line, entry)
