import logging

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import CommonPosTest, TestPoSCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosOrderSettlement(CommonPosTest):
    def _open_session(self, rounding_method="HALF-UP"):
        self.rounding = self.env["account.cash.rounding"].create(
            {
                "name": "Settlement cash rounding",
                "rounding": 0.05,
                "rounding_method": rounding_method,
                "profit_account_id": self.company_data["default_account_revenue"].id,
                "loss_account_id": self.company_data["default_account_expense"].id,
            }
        )
        self.pos_config_usd.write(
            {
                "cash_rounding": True,
                "only_round_cash_method": True,
                "rounding_method": self.rounding.id,
            }
        )
        self.pos_config_usd.open_ui()
        self.session = self.pos_config_usd.current_session_id

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
class TestPosRefundQuantities(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.product = self.create_product("Refundable", self.categ_basic, 10)
        self.session = self._start_pos_session(self.cash_pm1, 0)
        self.original = self._sync([(self.product, 2)])

    def _sync(self, lines, refunded_line=None):
        args = [
            {
                "product": product,
                "quantity": qty,
                **(
                    {"refunded_orderline_id": refunded_line.id} if refunded_line else {}
                ),
            }
            for product, qty in lines
        ]
        data = self.create_ui_order_data(args)
        if refunded_line:
            data["is_refund"] = True
        result = self.env["pos.order"].sync_from_ui([data])
        return self.env["pos.order"].browse(
            row["id"] for row in result["pos.order"] if row["uuid"] == data["uuid"]
        )

    def test_an_over_refund_from_the_till_is_recorded_and_flagged(self):
        line = self.original.lines
        self._sync([(self.product, -1)], line)
        self._sync([(self.product, -1)], line)
        self.assertEqual(line.refunded_qty, 2)

        over = self._sync([(self.product, -1)], line)

        _logger.debug("Refunded %s of %s", line.refunded_qty, line.qty)
        self.assertEqual(over.state, "paid")
        self.assertEqual(line.refunded_qty, 3)
        self.assertIn("returns more than was sold", over.message_ids[0].body)

    def test_a_draft_refund_does_not_block_a_paid_one(self):
        line = self.original.lines
        draft = self.create_ui_order_data(
            [
                {
                    "product": self.product,
                    "quantity": -2,
                    "refunded_orderline_id": line.id,
                }
            ],
            pos_order_ui_args={"state": "draft", "is_refund": True},
            payments=[],
        )
        self.env["pos.order"].sync_from_ui([draft])
        _logger.debug("Draft refund pending: refunded_qty=%s", line.refunded_qty)

        self._sync([(self.product, -2)], line)

        self.assertEqual(
            self.env["pos.order"].search([("uuid", "=", draft["uuid"])]).state, "draft"
        )

    def test_a_draft_refund_settled_by_the_wizard_cannot_over_refund(self):
        line = self.original.lines
        draft = self.create_ui_order_data(
            [
                {
                    "product": self.product,
                    "quantity": -2,
                    "refunded_orderline_id": line.id,
                }
            ],
            pos_order_ui_args={"state": "draft", "is_refund": True},
            payments=[],
        )
        self.env["pos.order"].sync_from_ui([draft])
        draft_refund = self.env["pos.order"].search([("uuid", "=", draft["uuid"])])
        self._sync([(self.product, -2)], line)

        with self.assertRaises(ValidationError):
            self.make_payment(draft_refund, self.cash_pm1, draft_refund.amount_total)

        self.assertEqual(draft_refund.state, "draft")
