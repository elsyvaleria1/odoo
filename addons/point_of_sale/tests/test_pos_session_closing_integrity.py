import logging
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged

from .common import PosLazySessionCommon, TestPoSCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosSessionClosingIntegrity(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config

    def _assert_bank_difference(self, session, method, amount, company_amount=None):
        moves = self.env["account.move"].search(
            [
                ("pos_diff_session_id", "=", session.id),
                ("pos_diff_payment_method_id", "=", method.id),
            ]
        )
        _logger.debug(
            "Session %s method %s difference %s: moves=%s",
            session.id,
            method.id,
            amount,
            moves,
        )
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves.state, "posted")
        outstanding = moves.line_ids.filtered(
            lambda line: line.account_id == method.outstanding_account_id
        )
        self.assertEqual(
            sum(outstanding.mapped("balance")),
            amount if company_amount is None else company_amount,
        )
        self.assertEqual(sum(moves.line_ids.mapped("balance")), 0)
        report = self.env["report.point_of_sale.report_saledetails"].get_sale_details(
            session_ids=session.ids
        )
        rows = [row for row in report["payments"] if row.get("id") == method.id]
        _logger.debug("Difference report rows for method %s: %s", method.id, rows)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["final_count"], 0)
        self.assertEqual(rows[0]["money_difference"], amount)
        self.assertEqual(rows[0]["money_counted"], amount)

    def test_empty_session_posts_combined_and_split_bank_differences(self):
        session = self._start_pos_session(self.bank_pm1 | self.bank_split_pm1, 0)

        session.action_pos_session_closing_control(
            bank_payment_method_diffs={
                self.bank_pm1.id: 20,
                self.bank_split_pm1.id: -10,
            }
        )

        self.assertEqual(session.state, "closed")
        self._assert_bank_difference(session, self.bank_pm1, 20)
        self._assert_bank_difference(session, self.bank_split_pm1, -10)

    def test_active_session_posts_difference_for_unused_bank_method(self):
        session = self._start_pos_session(self.cash_pm1 | self.bank_pm1, 0)
        product = self.create_product("Cash sale", self.categ_basic, 100, 50)
        self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(product, 1)],
                    "payments": [(self.cash_pm1, 100)],
                    "uuid": "cash-only-bank-difference",
                }
            ]
        )
        session.cash_register_balance_end_real = 100

        session.action_pos_session_closing_control(
            bank_payment_method_diffs={self.bank_pm1.id: 20}
        )

        self._assert_bank_difference(session, self.bank_pm1, 20)

    def test_empty_session_bank_difference_keeps_session_and_company_currencies(self):
        self.config = self.other_currency_config
        for amount in (20, -20):
            with self.subTest(amount=amount):
                session = self._start_pos_session(self.bank_pm2, 0)
                self.assertNotEqual(session.currency_id, session.company_id.currency_id)
                session.action_pos_session_closing_control(
                    bank_payment_method_diffs={self.bank_pm2.id: amount}
                )

                self._assert_bank_difference(
                    session, self.bank_pm2, amount, company_amount=amount * 2
                )

    def test_zero_bank_difference_needs_no_outstanding_account_or_move(self):
        self.bank_pm1.outstanding_account_id = False
        session = self._start_pos_session(self.bank_pm1, 0)

        session.action_pos_session_closing_control(
            bank_payment_method_diffs={self.bank_pm1.id: 0}
        )

        self.assertEqual(session.state, "closed")
        self.assertFalse(session._get_related_account_moves())

    def test_bank_difference_refuses_unconfigured_method(self):
        session = self._start_pos_session(self.bank_pm1, 0)

        with self.assertRaises(UserError):
            session.action_pos_session_closing_control(
                bank_payment_method_diffs={self.bank_split_pm1.id: 20}
            )

        self.assertEqual(session.state, "opened")

    def test_bank_difference_refuses_non_finite_amounts(self):
        session = self._start_pos_session(self.bank_pm1, 0)

        for amount in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(amount=amount), self.assertRaises(UserError):
                session.action_pos_session_closing_control(
                    bank_payment_method_diffs={self.bank_pm1.id: amount}
                )

        self.assertEqual(session.state, "opened")

    def test_bank_difference_without_profit_account_is_not_lost(self):
        self.bank_pm1.journal_id.profit_account_id = False
        session = self._start_pos_session(self.bank_pm1, 0)

        with self.assertRaises(UserError):
            session.action_pos_session_closing_control(
                bank_payment_method_diffs={self.bank_pm1.id: 20}
            )

        self.assertEqual(session.state, "opened")

    def test_closed_session_cash_move_cannot_be_deleted(self):
        session = self._start_pos_session(self.cash_pm1, 0)
        session.try_cash_in_out("in", 10, "Float", self.env.user.partner_id.id, {})
        movement = session.statement_line_ids
        session.cash_register_balance_end_real = 10
        session.action_pos_session_closing_control()

        with self.assertRaises(UserError):
            session.remove_cash_in_out(movement.id, self.env.user.partner_id.id)

        self.assertTrue(movement.exists())

    def test_payment_method_reconfiguration_preserves_closed_cash_journal(self):
        session = self._start_pos_session(self.cash_pm1, 0)
        session.try_cash_in_out("in", 10, "Float", self.env.user.partner_id.id, {})
        session.cash_register_balance_end_real = 10
        session.action_pos_session_closing_control()
        journal = session.cash_journal_id
        report = self.env["report.point_of_sale.report_saledetails"]
        lines = {session.id: session.statement_line_ids}
        before = report._prepare_uncounted_cash_row(session, lines)

        self.config.payment_method_ids = self.cash_split_pm1
        self.env.flush_all()
        session.invalidate_recordset(["cash_journal_id"])

        _logger.debug(
            "Closed journal before=%s after=%s", journal, session.cash_journal_id
        )
        self.assertEqual(session.cash_journal_id, journal)
        self.assertEqual(report._prepare_uncounted_cash_row(session, lines), before)
        self.config.open_ui()
        self.assertEqual(
            self.config.current_session_id.cash_journal_id,
            self.cash_split_pm1.journal_id,
        )

    def test_authorized_open_session_reconfiguration_updates_cash_journal(self):
        session = self._start_pos_session(self.cash_pm1, 0)

        self.config.with_context(
            bypass_payment_method_ids_forbidden_change=True
        ).payment_method_ids = self.cash_split_pm1

        _logger.debug("Reconfigured open session journal=%s", session.cash_journal_id)
        self.assertEqual(session.cash_journal_id, self.cash_split_pm1.journal_id)

    def test_closing_with_draft_orders_leaves_the_session_open_for_payment(self):
        session = self._start_pos_session(self.bank_pm1, 0)
        self.assertFalse(self.config.cash_control)
        product = self.create_product("Draft sale", self.categ_basic, 100, 50)
        draft = self.create_ui_order_data(
            [(product, 1)],
            pos_order_ui_args={"state": "draft"},
            payments=[],
            uuid="draft-before-close",
        )
        self.env["pos.order"].sync_from_ui([draft])

        refusal = session.update_closing_control_state_session("closing notes")

        _logger.debug("Close refusal for %s: %s", session.id, refusal)
        self.assertEqual(refusal["successful"], False)
        self.assertFalse(refusal["redirect"])
        self.assertEqual(session.state, "opened")
        paid = self.create_ui_order_data(
            [],
            payments=[(self.bank_pm1, draft["amount_total"])],
            uuid="draft-before-close",
        )
        self.env["pos.order"].sync_from_ui([paid])
        order = session.order_ids.filtered(lambda o: o.uuid == "draft-before-close")
        self.assertEqual(order.state, "paid")

    def test_closing_an_already_closed_session_reports_without_raising(self):
        session = self._start_pos_session(self.bank_pm1, 0)
        session.action_pos_session_closing_control()
        self.assertEqual(session.state, "closed")

        refusal = session.update_closing_control_state_session("late notes")

        _logger.debug("Already closed refusal for %s: %s", session.id, refusal)
        self.assertEqual(refusal["successful"], False)
        self.assertTrue(refusal["redirect"])
        self.assertNotIn("Rescue", refusal["message"])

    def test_session_of_only_future_paid_orders_posts_its_entry(self):
        session = self._start_pos_session(self.bank_pm1, 0)
        product = self.create_product("Pickup", self.categ_basic, 100, 50)
        self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(product, 1)],
                    "payments": [(self.bank_pm1, 100)],
                    "pos_order_ui_args": {
                        "preset_time": fields.Datetime.to_string(
                            fields.Datetime.now() + timedelta(days=1)
                        )
                    },
                    "uuid": "paid-pickup-tomorrow",
                }
            ]
        )

        session.action_pos_session_closing_control()

        _logger.debug(
            "Closed %s: move=%s orders=%s",
            session.id,
            session.move_id,
            session.order_ids.mapped("state"),
        )
        self.assertEqual(session.state, "closed")
        self.assertEqual(session.move_id.state, "posted")
        self.assertEqual(session.order_ids.mapped("state"), ["done"])

    def test_every_closing_payment_is_marked_as_a_pos_payment(self):
        session = self._start_pos_session(self.bank_pm1 | self.bank_split_pm1, 0)
        product = self.create_product("Split sale", self.categ_basic, 100, 50)
        self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(product, 1)],
                    "payments": [(self.bank_pm1, 100)],
                    "uuid": "combined-bank",
                },
                {
                    "pos_order_lines_ui_args": [(product, 1)],
                    "payments": [(self.bank_split_pm1, 100)],
                    "customer": self.customer,
                    "uuid": "split-bank",
                },
            ]
        )
        Payment = type(self.env["account.payment"])
        original_create = Payment.create
        contexts = []

        def create(records, vals_list):
            contexts.append(records.env.context.get("pos_payment"))
            return original_create(records, vals_list)

        self.patch(Payment, "create", create)

        session.action_pos_session_closing_control()

        _logger.debug("Closing payment contexts: %s", contexts)
        self.assertEqual(session.state, "closed")
        self.assertEqual(contexts, [True, True])

    def test_session_holding_only_a_future_draft_closes_without_entry(self):
        session = self._start_pos_session(self.bank_pm1, 0)
        product = self.create_product("Later", self.categ_basic, 100, 50)
        future = fields.Datetime.to_string(fields.Datetime.now() + timedelta(days=1))
        draft = self.create_ui_order_data(
            [(product, 1)],
            pos_order_ui_args={"state": "draft", "preset_time": future},
            payments=[],
            uuid="draft-pickup-tomorrow",
        )
        self.env["pos.order"].sync_from_ui([draft])

        session.action_pos_session_closing_control()

        _logger.debug("Closed %s: move=%s", session.id, session.move_id)
        self.assertEqual(session.state, "closed")
        self.assertFalse(session.move_id)


@tagged("post_install", "-at_install")
class TestPosSessionClosingSummary(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config

    def test_closing_summary_keeps_cash_bank_credit_and_unused_methods(self):
        session = self._start_pos_session(
            self.cash_pm1 | self.bank_pm1 | self.pay_later_pm | self.bank_split_pm1, 10
        )
        product = self.create_product("Summary product", self.categ_basic, 100, 50)
        self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(product, 1)],
                    "payments": [
                        (self.cash_pm1, 40),
                        (self.bank_pm1, 30),
                        (self.pay_later_pm, 30),
                    ],
                    "customer": self.customer,
                    "uuid": "session-summary-audit",
                }
            ]
        )
        session.try_cash_in_out("out", 5, "petty cash", self.env.user.partner_id.id, {})

        summary = session.get_closing_control_data()

        _logger.debug("Closing summary: %s", summary)
        self.assertEqual(summary["orders_details"], {"quantity": 1, "amount": 100})
        self.assertEqual(summary["default_cash_details"]["amount"], 45)
        self.assertEqual(summary["default_cash_details"]["payment_amount"], 40)
        methods = {
            method["id"]: method for method in summary["non_cash_payment_methods"]
        }
        for method, amount, count in [
            (self.bank_pm1, 30, 1),
            (self.pay_later_pm, 30, 1),
            (self.bank_split_pm1, 0, 0),
        ]:
            self.assertEqual(methods[method.id]["amount"], amount)
            self.assertEqual(methods[method.id]["number"], count)

    def test_closing_summary_without_cash(self):
        session = self._start_pos_session(self.bank_pm1, 0)

        summary = session.get_closing_control_data()

        self.assertNotIn("id", summary["default_cash_details"])
        self.assertNotIn("amount", summary["default_cash_details"])
        self.assertEqual(len(summary["non_cash_payment_methods"]), 1)
        self.assertEqual(summary["non_cash_payment_methods"][0]["amount"], 0)

    def test_closing_summary_preserves_refunds_and_second_cash_method(self):
        methods = self.cash_pm1 | self.cash_split_pm1 | self.bank_pm1
        session = self._start_pos_session(methods, 10)
        product = self.create_product("Refund summary", self.categ_basic, 100, 50)
        self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(product, sign)],
                    "payments": [
                        (self.cash_pm1, 40 * sign),
                        (self.cash_split_pm1, 20 * sign),
                        (self.bank_pm1, 40 * sign),
                    ],
                    "customer": self.customer,
                    "uuid": f"summary-sign-{sign}",
                }
                for sign in (1, -1)
            ]
        )

        summary = session.get_closing_control_data()

        _logger.debug("Refund and second cash method summary: %s", summary)
        self.assertEqual(summary["orders_details"], {"quantity": 2, "amount": 0})
        self.assertEqual(summary["default_cash_details"]["id"], self.cash_pm1.id)
        self.assertEqual(summary["default_cash_details"]["amount"], 10)
        self.assertEqual(summary["default_cash_details"]["payment_amount"], 0)
        self.assertEqual(
            [
                (row["id"], row["amount"], row["number"])
                for row in summary["non_cash_payment_methods"]
            ],
            [
                (method.id, 0, 2)
                for method in session.payment_method_ids - self.cash_pm1
            ],
        )

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


@tagged("post_install", "-at_install")
class TestPosSessionCountedBankDifference(TestPoSCommon):
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
                expected_account = captured.bank_payment_ids.liquidity_account_id
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
class TestPosSessionClosingAccounting(PosLazySessionCommon):
    def test_an_unbalanced_close_keeps_the_orders_and_a_retry_closes(self):
        product = self.env["product.product"].create(
            {
                "name": "Challenge unbalanced service",
                "type": "service",
                "available_in_pos": True,
                "taxes_id": [Command.clear()],
            }
        )
        order = self._create_order_from_specs(
            [{"product_id": product.id, "qty": 1, "price_unit": 10}], paid=True
        )
        session = order.session_id
        original = type(session)._create_account_move

        def unbalanced(record, *args, **kwargs):
            result = original(record, *args, **kwargs)
            line = record.move_id.line_ids.filtered(lambda l: l.debit > 0)[:1]
            line.with_context(check_move_validity=False).write(
                {"debit": line.debit + 1}
            )
            _logger.debug(
                "injected imbalance=%s into move=%s",
                sum(record.move_id.line_ids.mapped("balance")),
                record.move_id.id,
            )
            return result

        with patch.object(type(session), "_create_account_move", unbalanced):
            action = session.action_pos_session_closing_control()
        self.assertEqual(action["res_model"], "wizard.pos.session.close.unbalanced")
        self.assertTrue(order.exists())
        self.assertEqual(order.state, "paid")
        self.assertFalse(session.move_id)
        session.action_pos_session_closing_control()
        self.assertEqual(session.state, "closed")
        _logger.debug(
            "unbalanced close preserved order=%s and retry closed session=%s",
            order.id,
            session.id,
        )

    def test_a_split_foreign_bank_payment_keeps_the_session_currency(self):
        self._set_report_rates()
        self.bank_payment_method.split_transactions = True
        product = self.env["product.product"].create(
            {
                "name": "Split foreign service",
                "type": "service",
                "available_in_pos": True,
            }
        )
        order = self._create_order_from_specs(
            [{"product_id": product.id, "qty": 1, "price_unit": 100}],
            self.pos_config_eur,
            paid=True,
        )
        order.session_id.action_pos_session_closing_control()
        payment = self.env["account.payment"].search(
            [("pos_session_id", "=", order.session_id.id)]
        )
        self.assertEqual(payment.currency_id, order.currency_id)
        self.assertEqual(payment.amount, 100)
        self.assertEqual(payment.amount_company_currency_signed, 200)
        _logger.debug(
            "ACCOUNT split foreign payment=%s currency=%s amount=%s company_amount=%s",
            payment.id,
            payment.currency_id.name,
            payment.amount,
            payment.amount_company_currency_signed,
        )
