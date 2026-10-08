import logging
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import TestPoSCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosSessionChallenge(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config

    def _close_bank_sales(self, sale_amounts, difference, method=None):
        method = method or self.bank_pm1
        session = self._start_pos_session(method, 0)
        product = self.create_product("Bank challenge", self.categ_basic, 100, 50)
        self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(product, amount / 100)],
                    "payments": [(method, amount)],
                    "customer": self.customer,
                    "uuid": f"bank-challenge-{session.id}-{index}",
                }
                for index, amount in enumerate(sale_amounts)
            ]
        )
        session.action_pos_session_closing_control(
            bank_payment_method_diffs={method.id: difference}
        )
        return session

    def _assert_counted_bank(self, session, expected, difference, method=None):
        method = method or self.bank_pm1
        payments = session.bank_payment_ids
        bank_lines = session._get_related_account_moves().line_ids.filtered(
            lambda line: line.account_id == method.outstanding_account_id
        )
        _logger.debug(
            "Bank posting payments=%s directions=%s balances=%s",
            payments.ids,
            payments.mapped("payment_type"),
            bank_lines.mapped("balance"),
        )
        self.assertEqual(sum(bank_lines.mapped("balance")), expected + difference)
        if payments:
            receivable_account = (
                self.customer.property_account_receivable_id
                if method.split_transactions
                else self.pos_receivable_bank
            )
            receivable_lines = (session.move_id | payments.move_id).line_ids.filtered(
                lambda line: line.account_id == receivable_account
            )
            self.assertEqual(sum(receivable_lines.mapped("balance")), 0)
            self.assertTrue(all(receivable_lines.mapped("reconciled")))
        report = self.env["report.point_of_sale.report_saledetails"].get_sale_details(
            session_ids=session.ids
        )
        rows = [row for row in report["payments"] if row.get("id") == method.id]
        _logger.debug(
            "Bank challenge expected=%s difference=%s rows=%s",
            expected,
            difference,
            rows,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["final_count"], expected)
        self.assertEqual(rows[0]["money_counted"], expected + difference)
        self.assertEqual(rows[0]["money_difference"], difference)
        return rows[0]

    def test_zero_net_captured_bank_payments_keep_difference(self):
        session = self._close_bank_sales([100, -100], 20)
        self.assertEqual(session.state, "closed")
        self._assert_counted_bank(session, 0, 20)
        self.assertFalse(
            self.env["account.move"].search(
                [
                    ("pos_diff_session_id", "=", session.id),
                ]
            ),
            "A combined adjustment must not also create a standalone difference",
        )

    def test_combined_bank_difference_crossing_zero_keeps_signed_count(self):
        for expected, difference in (
            (10, -20),
            (-10, 20),
            (-10, -5),
            (10, 5),
            (-10, 0),
            (10, -10),
            (-10, 10),
        ):
            with (
                self.subTest(expected=expected, difference=difference),
                self.env.cr.savepoint(),
            ):
                session = self._close_bank_sales([expected], difference)
                self.assertEqual(session.state, "closed")
                self._assert_counted_bank(session, expected, difference)

    def test_shared_profit_and_loss_account_keeps_gain_sign(self):
        self.bank_pm1.journal_id.loss_account_id = (
            self.bank_pm1.journal_id.profit_account_id
        )
        session = self._close_bank_sales([], 20)
        self._assert_counted_bank(session, 0, 20)

    def test_split_bank_refund_keeps_bank_and_receivable_roles(self):
        session = self._close_bank_sales([-10], 20, self.bank_split_pm1)
        self._assert_counted_bank(session, -10, 20, self.bank_split_pm1)

    def test_unused_bank_method_uses_same_default_account_as_captured_payments(self):
        self.bank_pm1.outstanding_account_id = False
        for sign in (1, -1):
            with self.subTest(sign=sign), self.env.cr.savepoint():
                captured = self._close_bank_sales([100 * sign], 20 * sign)
                expected_account = captured.bank_payment_ids.outstanding_account_id
                self.assertTrue(expected_account)
                _logger.debug(
                    "Captured bank payment sign=%s resolved default account=%s",
                    sign,
                    expected_account,
                )

                empty = self._close_bank_sales([], 20 * sign)

                moves = self.env["account.move"].search(
                    [("pos_diff_session_id", "=", empty.id)]
                )
                lines = moves.line_ids.filtered_domain(
                    [("account_id", "=", expected_account.id)]
                )
                self.assertEqual(sum(lines.mapped("balance")), 20 * sign)
                self.assertEqual(moves.state, "posted")
                self.assertFalse(empty.bank_payment_ids)


@tagged("post_install", "-at_install")
class TestPosSessionClosingPaths(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config

    def _cash_sales(self, session, amounts, method=None, customer=False):
        method = method or self.cash_pm1
        product = self.create_product("Closing path", self.categ_basic, 1, 0)
        return self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(product, amount)],
                    "payments": [(method, amount)],
                    "customer": customer,
                    "uuid": f"closing-path-{session.id}-{method.id}-{index}-{amount}",
                }
                for index, amount in enumerate(amounts)
            ]
        )

    def test_cash_messages_are_authored_by_the_cashier(self):
        self.env["res.partner"].create(
            {"name": "Email namesake", "email": "till@example.com"}
        )
        self.config.payment_method_ids = self.cash_pm1
        for login, email in (
            ("till_without_email", False),
            ("till_sharing_an_email", "till@example.com"),
        ):
            with self.subTest(email=email):
                cashier = new_test_user(
                    self.env,
                    login=login,
                    email=email,
                    groups="base.group_user,point_of_sale.group_pos_user",
                    company_id=self.company.id,
                )
                self.config.open_ui()
                session = self.config.current_session_id.with_user(cashier)
                session.set_opening_control(5, "")
                session.update_closing_control_state_session("Counted")
                self.assertEqual(session.close_session_from_ui(), {"successful": True})

                messages = session.sudo().message_ids
                authors = {
                    label: messages.filtered(
                        lambda message, label=label: label in (message.body or "")
                    ).author_id
                    for label in (
                        "Opening cash difference",
                        "Closing difference",
                        "Closed Register",
                    )
                }
                _logger.debug("Cashier %s message authors: %s", login, authors)
                for label, author in authors.items():
                    self.assertEqual(author, cashier.partner_id, label)

    def test_closing_cash_summary_is_the_theoretical_balance(self):
        rounding = self.env["account.cash.rounding"].create(
            {
                "name": "Closing summary rounding",
                "rounding": 0.05,
                "strategy": "add_invoice_line",
                "profit_account_id": self.company.account_config_id[
                    "default_cash_difference_income_account_id"
                ].id,
                "loss_account_id": self.company.account_config_id[
                    "default_cash_difference_expense_account_id"
                ].id,
                "rounding_method": "HALF-UP",
            }
        )
        self.config.write({"cash_rounding": True, "rounding_method": rounding.id})
        session = self._start_pos_session(self.cash_pm1 | self.bank_pm1, 7.5)
        product = self.create_product("Rounded sale", self.categ_basic, 10.03, 5)
        self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(product, 1)],
                    "payments": [(self.cash_pm1, 10.05)],
                    "uuid": "summary-rounded-cash",
                },
                {
                    "pos_order_lines_ui_args": [(product, 1)],
                    "payments": [(self.bank_pm1, 10.05)],
                    "uuid": "summary-rounded-bank",
                },
            ]
        )
        session.try_cash_in_out("in", 20, "Float", False, {})
        session.try_cash_in_out("out", 4.25, "Petty cash", False, {})

        for state in ("opened", "closing_control"):
            with self.subTest(state=state):
                if state == "closing_control":
                    session.update_closing_control_state_session("")
                summary = session.get_closing_control_data()["default_cash_details"]
                _logger.debug("Closing cash summary in %s: %s", state, summary)
                self.assertEqual(session.state, state)
                self.assertAlmostEqual(summary["amount"], 7.5 + 10.05 + 20 - 4.25)
                self.assertEqual(summary["amount"], session.cash_register_balance_end)
                self.assertAlmostEqual(summary["payment_amount"], 10.05)

    def test_a_ui_close_reads_the_session_orders_once_per_guard(self):
        self.config.order_edit_tracking = True
        session = self._start_pos_session(self.cash_pm1, 0)
        self._cash_sales(session, [3, 4])
        session.update_closing_cash_details(7)
        calls = []
        get_session_orders = type(session).get_session_orders

        def counted_get_session_orders(records):
            calls.append(records.ids)
            return get_session_orders(records)

        with patch.object(
            type(session), "get_session_orders", counted_get_session_orders
        ):
            self.assertEqual(session.close_session_from_ui(), {"successful": True})

        _logger.debug("get_session_orders calls during a UI close: %s", calls)
        self.assertEqual(session.state, "closed")
        self.assertEqual(len(calls), 2)

    def test_closing_a_closed_session_leaves_it_closed(self):
        session = self._start_pos_session(self.cash_pm1, 0)
        self._cash_sales(session, [5])
        session.action_pos_session_closing_control()
        stop_at = session.stop_at

        with self.assertRaises(UserError):
            session.action_pos_session_closing_control()

        self.assertEqual(session.state, "closed")
        self.assertEqual(session.stop_at, stop_at)

    def test_journal_items_action_selects_lines_by_entry(self):
        session = self._start_pos_session(self.cash_pm1 | self.bank_pm1, 0)
        self._cash_sales(session, [5, 6])
        self._cash_sales(session, [7], method=self.bank_pm1)
        session.action_pos_session_closing_control()
        moves = session._get_related_account_moves()

        action = session.action_view_journal_items()

        self.assertEqual(action["domain"], [("move_id", "in", moves.ids)])
        self.assertEqual(
            self.env["account.move.line"].search(action["domain"]), moves.line_ids
        )

    def test_split_bank_payments_are_created_and_reconciled_in_one_batch(self):
        session = self._start_pos_session(self.cash_pm1 | self.bank_split_pm1, 0)
        customers = self.env["res.partner"].create(
            [{"name": f"Split customer {index}"} for index in range(20)]
        )
        for index, customer in enumerate(customers):
            self._cash_sales(
                session, [index + 1], method=self.bank_split_pm1, customer=customer
            )
        AccountPayment = type(self.env["account.payment"])
        MoveLine = type(self.env["account.move.line"])
        payment_create = AccountPayment.create
        reconcile_plan = MoveLine._reconcile_plan
        payment_batches = []
        reconcile_plans = []

        def counted_payment_create(records, vals_list):
            payment_batches.append(len(vals_list) if isinstance(vals_list, list) else 1)
            return payment_create(records, vals_list)

        def counted_reconcile_plan(records, plan):
            reconcile_plans.append(len(plan))
            return reconcile_plan(records, plan)

        self.env.flush_all()
        statements = self.env.cr.sql_statement_count
        with (
            patch.object(AccountPayment, "create", counted_payment_create),
            patch.object(MoveLine, "_reconcile_plan", counted_reconcile_plan),
        ):
            session.action_pos_session_closing_control()
            self.env.flush_all()
        statements = self.env.cr.sql_statement_count - statements
        _logger.debug(
            "Closing 20 split bank payments: %s statements, payment batches %s,"
            " reconcile plans %s",
            statements,
            payment_batches,
            reconcile_plans,
        )

        self.assertEqual(session.state, "closed")
        payments = session.bank_payment_ids
        self.assertEqual(len(payments), 20)
        self.assertEqual(payments.partner_id, customers)
        receivable_account = customers.property_account_receivable_id
        self.assertEqual(len(receivable_account), 1)
        receivable_lines = (session.move_id | payments.move_id).line_ids.filtered(
            lambda line: line.account_id == receivable_account
        )
        self.assertEqual(len(receivable_lines), 40)
        self.assertTrue(all(receivable_lines.mapped("reconciled")))
        for customer, lines in receivable_lines.grouped("partner_id").items():
            self.assertEqual(sum(lines.mapped("balance")), 0, customer.name)
        self.assertEqual(payment_batches, [20])
        self.assertEqual(len(reconcile_plans), 1)
