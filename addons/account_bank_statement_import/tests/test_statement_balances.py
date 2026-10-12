from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestStatementBalances(TransactionCase):
    def _statement(self, transactions, **values):
        return {
            "name": "STMT/2026/001",
            "transactions": [{"amount": amount} for amount in transactions],
            **values,
        }

    def _check(self, *statements):
        self.env["account.journal"]._check_parsed_balances(list(statements), "BE001")

    def test_a_statement_that_adds_up_passes(self):
        self._check(
            self._statement(
                [100.0, -30.0],
                balance_start=1000.0,
                balance_end_real=1070.0,
                balances_are_booked=True,
            ),
        )

    def test_a_statement_that_does_not_add_up_is_refused(self):
        with self.assertRaises(UserError) as caught:
            self._check(
                self._statement(
                    [100.0, -30.0],
                    balance_start=1000.0,
                    balance_end_real=1100.0,
                    balances_are_booked=True,
                ),
            )
        message = str(caught.exception)
        self.assertIn("STMT/2026/001", message)
        self.assertIn("30.0", message, "the message names the difference")

    def test_an_available_balance_is_not_reconciled(self):
        self._check(
            self._statement(
                [-6306.71],
                balance_start=8998.20,
                balance_end_real=2661.49,
                balances_are_booked=False,
            ),
        )

    def test_a_parser_that_says_nothing_is_not_reconciled(self):
        self._check(
            self._statement([100.0], balance_start=1000.0, balance_end_real=9999.0),
        )

    def test_a_missing_balance_is_not_reconciled(self):
        self._check(
            self._statement([100.0], balance_end_real=9999.0, balances_are_booked=True),
        )
        self._check(
            self._statement([100.0], balance_start=1000.0, balances_are_booked=True),
        )

    def test_rounding_does_not_make_a_statement_fail(self):
        self._check(
            self._statement(
                [0.1, 0.1, 0.1],
                balance_start=0.0,
                balance_end_real=0.3,
                balances_are_booked=True,
            ),
        )

    def test_a_statement_with_no_transactions_still_has_to_add_up(self):
        with self.assertRaises(UserError):
            self._check(
                self._statement(
                    [],
                    balance_start=1000.0,
                    balance_end_real=1200.0,
                    balances_are_booked=True,
                ),
            )

    def test_the_first_unbalanced_statement_in_a_file_is_named(self):
        good = self._statement(
            [50.0], balance_start=0.0, balance_end_real=50.0, balances_are_booked=True
        )
        bad = self._statement(
            [50.0],
            balance_start=0.0,
            balance_end_real=500.0,
            balances_are_booked=True,
            name="STMT/2026/002",
        )
        with self.assertRaises(UserError) as caught:
            self._check(good, bad)
        self.assertIn("STMT/2026/002", str(caught.exception))
