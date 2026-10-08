import logging
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TestPoSCommon

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

                # The fixture's rate is 0.5: 20 session units are 40 company units.
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
