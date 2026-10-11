import logging

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import (
    PosCashRoundingCommon,
    PosCashRoundingSessionCommon,
    PosOpenSessionCommon,
)

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosOrderSettlement(PosCashRoundingCommon):
    def _create_order(self, price_unit, **values):
        order = self.env["pos.order"].create(
            {
                "session_id": self.session.id,
                "amount_tax": 0,
                "amount_total": 0,
                "amount_paid": 0,
                "amount_return": 0,
                "lines": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "qty": 1,
                            "price_unit": price_unit,
                            "price_subtotal": price_unit,
                            "price_subtotal_incl": price_unit,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
                **values,
            }
        )
        order._recompute_amounts()
        return order

    def _pay(self, order, method, amount):
        return (
            self.env["wizard.pos.order.pay"]
            .with_context(active_model="pos.order", active_id=order.id)
            .create({"amount": amount, "payment_method_id": method.id})
            .action_make_payment()
        )

    def _wizard_default_amount(self, order):
        return (
            self.env["wizard.pos.order.pay"]
            .with_context(active_model="pos.order", active_id=order.id)
            .new({})
            .amount
        )

    def test_full_refund_of_rounded_cash_sale_settles_by_bank(self):
        self._open_session()
        order = self._create_order(10.02)
        self._pay(order, self.cash_payment_method, 10.02)
        self.assertEqual(order.state, "paid")
        self.assertEqual(order.amount_paid, 10.0)

        refund = order._refund()
        default_amount = self._wizard_default_amount(refund)
        _logger.debug(
            "Refund %s total=%s default=%s",
            refund.id,
            refund.amount_total,
            default_amount,
        )
        self.assertEqual(refund.amount_total, -10.02)
        self.assertEqual(default_amount, -10.0)

        self._pay(refund, self.bank_payment_method, default_amount)

        self.assertEqual(refund.state, "paid")
        self.assertEqual(refund.amount_paid, -10.0)

        self.session.action_pos_session_closing_control()
        _logger.debug(
            "Closed %s: state=%s move=%s",
            self.session.id,
            self.session.state,
            self.session.move_id,
        )
        self.assertEqual(self.session.state, "closed")
        self.assertEqual(self.session.move_id.state, "posted")

    def test_frontend_full_refund_paid_at_its_own_total_still_syncs(self):
        self._open_session()
        order = self._create_order(10.02)
        self._pay(order, self.cash_payment_method, 10.02)
        line = order.lines
        refund_values = {
            "uuid": "frontend-full-refund",
            "session_id": self.session.id,
            "state": "paid",
            "is_refund": True,
            "amount_paid": -10.02,
            "amount_total": -10.02,
            "amount_tax": 0,
            "amount_return": 0,
            "lines": [
                Command.create(
                    {
                        "product_id": self.product_a.id,
                        "qty": -1,
                        "price_unit": 10.02,
                        "price_subtotal": -10.02,
                        "price_subtotal_incl": -10.02,
                        "tax_ids": [Command.clear()],
                        "refunded_orderline_id": line.id,
                    }
                )
            ],
            "payment_ids": [
                Command.create(
                    {
                        "amount": -10.02,
                        "payment_method_id": self.bank_payment_method.id,
                    }
                )
            ],
        }

        self.env["pos.order"].sync_from_ui([refund_values])

        refund = self.env["pos.order"].search([("uuid", "=", "frontend-full-refund")])
        _logger.debug(
            "Frontend refund %s state=%s total=%s paid=%s",
            refund.id,
            refund.state,
            refund.amount_total,
            refund.amount_paid,
        )
        self.assertEqual(refund.state, "paid")

    def test_full_refund_also_settles_at_its_own_total(self):
        self._open_session()
        order = self._create_order(10.02)
        self._pay(order, self.cash_payment_method, 10.02)
        refund = order._refund()

        self._pay(refund, self.bank_payment_method, -10.02)

        self.assertEqual(refund.state, "paid")
        self.assertEqual(refund.amount_paid, -10.02)

    def test_short_bank_payment_leaves_the_order_unpaid(self):
        self._open_session()
        order = self._create_order(10.02)

        self._pay(order, self.bank_payment_method, 10.0)

        self.assertEqual(order.state, "draft")
        self.assertFalse(order._is_payment_amount_valid())
        with self.assertRaises(UserError):
            order.action_pos_order_paid()

    def test_payment_refreshes_every_derived_amount(self):
        self._open_session()
        order = self._create_order(10.0)

        self._pay(order, self.bank_payment_method, 4.0)

        _logger.debug(
            "Partially paid %s: paid=%s difference=%s",
            order.id,
            order.amount_paid,
            order.amount_difference,
        )
        self.assertEqual(order.amount_paid, 4.0)
        self.assertEqual(order.amount_difference, -6.0)

    def test_down_rounding_tolerance_excludes_a_whole_rounding_step(self):
        self._open_session("DOWN")
        order = self._create_order(10.10)
        order.add_payment(
            {
                "pos_order_id": order.id,
                "payment_method_id": self.cash_payment_method.id,
                "amount": 10.05,
            }
        )

        self.assertFalse(order._is_payment_amount_valid())

    def test_down_rounding_tolerance_keeps_partial_steps(self):
        self._open_session("DOWN")
        order = self._create_order(10.14)
        order.add_payment(
            {
                "pos_order_id": order.id,
                "payment_method_id": self.cash_payment_method.id,
                "amount": 10.12,
            }
        )

        self.assertTrue(order._is_payment_amount_valid())


@tagged("post_install", "-at_install")
class TestPosOrderPaidPaymentEdits(PosCashRoundingSessionCommon):
    def _create_rounded_paid_order(self, sign=1):
        order = self._create_bare_order(is_refund=sign < 0)
        line = self._create_line(order)
        line.write({"qty": sign, "price_unit": 10.02})
        order._recompute_amounts()
        order.add_payment(
            {
                "pos_order_id": order.id,
                "payment_method_id": self.cash_payment_method.id,
                "amount": sign * 10,
            }
        )
        order.action_pos_order_paid()
        return order

    def test_paid_cash_payment_can_switch_to_exact_bank_settlement(self):
        for sign in (1, -1):
            with self.subTest(sign=sign):
                order = self._create_rounded_paid_order(sign)
                order.write(
                    {
                        "payment_ids": [
                            Command.update(
                                order.payment_ids.id,
                                {
                                    "payment_method_id": self.bank_payment_method.id,
                                    "amount": sign * 10.02,
                                },
                            )
                        ]
                    }
                )
                self.assertEqual(
                    order.payment_ids.payment_method_id, self.bank_payment_method
                )
                self.assertEqual(order.amount_paid, sign * 10.02)
                self.assertTrue(order._is_payment_amount_valid())

    def test_rounded_paid_payment_updates_preserve_valid_settlement(self):
        for sign in (1, -1):
            for state in ("paid", "done"):
                with self.subTest(sign=sign, state=state):
                    order = self._create_rounded_paid_order(sign)
                    order.state = state
                    before = order.message_ids
                    order.write(
                        {
                            "payment_ids": [
                                Command.update(
                                    order.payment_ids.id, {"name": "terminal reference"}
                                )
                            ]
                        }
                    )
                    self.assertEqual(order.amount_paid, sign * 10)
                    self.assertEqual(order.state, state)
                    self.assertFalse(order.message_ids - before)

    def test_paid_refund_cannot_be_edited_to_underpay_customer(self):
        for state in ("paid", "done"):
            with self.subTest(state=state):
                order = self._create_rounded_paid_order(-1)
                order.state = state
                with self.assertRaises(UserError):
                    order.write(
                        {
                            "payment_ids": [
                                Command.update(order.payment_ids.id, {"amount": -9})
                            ]
                        }
                    )
                self.assertEqual(order.amount_paid, -10)

    def test_paid_payment_edits_still_reject_underpayment_and_warn_overpayment(self):
        for sign in (1, -1):
            with self.subTest(sign=sign):
                order = self._create_rounded_paid_order(sign)
                with self.assertRaises(UserError):
                    order.write(
                        {
                            "payment_ids": [
                                Command.update(
                                    order.payment_ids.id, {"amount": sign * 9}
                                )
                            ]
                        }
                    )
                previous = order.message_ids
                values = {
                    "payment_ids": [
                        Command.update(order.payment_ids.id, {"amount": sign * 11})
                    ]
                }
                if sign < 0:
                    with self.assertRaises(UserError):
                        order.write(values)
                else:
                    order.write(values)
                    self.assertIn(
                        "higher than the total", (order.message_ids - previous).body
                    )

    def test_paid_cash_rounding_cannot_be_kept_after_switching_to_bank(self):
        for sign in (1, -1):
            with self.subTest(sign=sign):
                order = self._create_rounded_paid_order(sign)
                with self.assertRaises(UserError):
                    order.write(
                        {
                            "payment_ids": [
                                Command.update(
                                    order.payment_ids.id,
                                    {
                                        "payment_method_id": self.bank_payment_method.id,
                                    },
                                )
                            ]
                        }
                    )
                self.assertEqual(
                    order.payment_ids.payment_method_id, self.cash_payment_method
                )

    def test_zero_payment_edit_is_in_chatter(self):
        order = self._create_bare_order()
        order.add_payment(
            {
                "pos_order_id": order.id,
                "payment_method_id": self.cash_payment_method.id,
                "amount": 5,
            }
        )
        previous_messages = order.message_ids

        order.write(
            {"payment_ids": [Command.update(order.payment_ids.id, {"amount": 0})]}
        )

        messages = order.message_ids - previous_messages
        self.assertEqual(len(messages), 1)
        self.assertIn("changed from", messages.body)
        self.assertEqual(order.amount_paid, 0)

    def test_zero_edit_with_method_change_preserves_both_history_values(self):
        order = self._create_bare_order()
        order.add_payment(
            {
                "pos_order_id": order.id,
                "payment_method_id": self.cash_payment_method.id,
                "amount": 5,
            }
        )
        before = order.message_ids

        order.write(
            {
                "payment_ids": [
                    Command.update(
                        order.payment_ids.id,
                        {
                            "amount": 0,
                            "payment_method_id": self.bank_payment_method.id,
                        },
                    )
                ]
            }
        )

        messages = order.message_ids - before
        self.assertEqual(len(messages), 1)
        self.assertIn(self.cash_payment_method.name, messages.body)
        self.assertIn(self.bank_payment_method.name, messages.body)
        self.assertIn("and from", messages.body)
        self.assertIn("0.00", messages.body)


@tagged("post_install", "-at_install")
class TestPosOrderCashOnlyRounding(PosCashRoundingSessionCommon):
    def test_card_underpayment_cannot_use_cash_only_tolerance(self):
        order = self._create_bare_order(amount_total=10.02)
        order.add_payment(
            {
                "pos_order_id": order.id,
                "payment_method_id": self.bank_payment_method.id,
                "amount": 10,
            }
        )
        _logger.debug(
            "Card-only payment: total=%s paid=%s", order.amount_total, order.amount_paid
        )

        with self.assertRaises(UserError):
            order.action_pos_order_paid()

        self.assertEqual(order.state, "draft")

    def test_cash_payment_can_use_cash_rounding(self):
        order = self._create_bare_order(amount_total=10.02)
        order.add_payment(
            {
                "pos_order_id": order.id,
                "payment_method_id": self.cash_payment_method.id,
                "amount": 10,
            }
        )

        order.action_pos_order_paid()

        self.assertEqual(order.state, "paid")

    def test_cash_only_rounding_through_sync_with_real_totals(self):
        self.product_a.type = "service"
        for sign in (1, -1):
            for method in (self.cash_payment_method, self.bank_payment_method):
                with self.subTest(sign=sign, method=method.name):
                    order = self._create_bare_order(is_refund=sign < 0)
                    line = self._create_line(order)
                    line.write({"qty": sign, "price_unit": 10.02})
                    order._recompute_amounts()
                    self.assertEqual(order.amount_total, sign * 10.02)
                    values = self._sync_values(order, [])
                    values.update(
                        {
                            "state": "paid",
                            "payment_ids": [
                                Command.create(
                                    {
                                        "payment_method_id": method.id,
                                        "amount": sign * 10,
                                    }
                                )
                            ],
                        }
                    )

                    if method == self.bank_payment_method:
                        with self.assertRaises(UserError), self.env.cr.savepoint():
                            self.env["pos.order"].sync_from_ui([values])
                        self.assertEqual(order.state, "draft")
                        self.assertFalse(order.payment_ids)
                    else:
                        self.env["pos.order"].sync_from_ui([values])
                        self.assertEqual(order.state, "paid")

    def test_zero_cash_line_preserves_explicit_rounding_intent(self):
        order = self._create_bare_order(amount_total=10.02)
        for method, amount in (
            (self.bank_payment_method, 10),
            (self.cash_payment_method, 0),
        ):
            order.add_payment(
                {
                    "pos_order_id": order.id,
                    "payment_method_id": method.id,
                    "amount": amount,
                }
            )

        order.action_pos_order_paid()

        self.assertEqual(order.state, "paid")

    def test_cash_payment_can_round_the_entire_order_to_zero(self):
        self.session.set_opening_control(0, None)
        order = self._create_bare_order()
        self.product_a.type = "service"
        line = self._create_line(order)
        line.price_unit = 0.02
        order._recompute_amounts()
        self.assertEqual(order.amount_total, 0.02)
        values = self._sync_values(order, [])
        values.update(
            {
                "state": "paid",
                "payment_ids": [
                    Command.create(
                        {
                            "payment_method_id": self.cash_payment_method.id,
                            "amount": 0,
                        }
                    )
                ],
            }
        )

        self.env["pos.order"].sync_from_ui([values])

        self.assertEqual(order.state, "paid")
        self.assertEqual(order.amount_paid, 0)
        self.assertEqual(order.payment_ids.payment_method_id, self.cash_payment_method)

        self.session.action_pos_session_closing_control()

        self.assertEqual(self.session.state, "closed")
        self.assertEqual(self.session.move_id.state, "posted")


@tagged("post_install", "-at_install")
class TestPosOrderPrintedPayments(PosOpenSessionCommon):
    def test_a_printed_paid_order_refuses_a_new_payment(self):
        cash_pm = self.session.payment_method_ids.filtered("is_cash_count")[:1]
        order = self._create_bare_order(state="paid", nb_print=1)
        with self.assertRaises(UserError):
            order.write(
                {
                    "payment_ids": [
                        Command.create(
                            {
                                "payment_method_id": cash_pm.id,
                                "amount": 5,
                                "payment_status": "done",
                            }
                        )
                    ]
                }
            )
        self.assertFalse(order.payment_ids)
