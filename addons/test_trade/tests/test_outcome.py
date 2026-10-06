from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TestTradeOrderCase


@tagged("post_install", "-at_install")
class TestOutcome(TestTradeOrderCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reason_price = cls.env.ref("loss_reason.loss_reason_price")

    def _confirmable_order(self):
        order = self._make_order()
        self._make_line(order=order, product_qty=1.0)
        return order

    def test_new_order_is_open(self):
        self.assertEqual(self._make_order().outcome, "open")

    def test_confirmed_order_is_won(self):
        order = self._confirmable_order()

        order.action_confirm()

        self.assertEqual(order.outcome, "won")

    def test_plain_cancel_is_withdrawn(self):
        order = self._make_order()

        order.action_cancel()

        self.assertEqual(order.state, "cancel")
        self.assertEqual(order.outcome, "withdrawn")

    def test_close_as_lost_cancels_and_keeps_the_reason(self):
        order = self._make_order()

        order._close_as("lost", loss_reason=self.reason_price, note="12% cheaper")

        self.assertRecordValues(
            order,
            [
                {
                    "state": "cancel",
                    "outcome": "lost",
                    "loss_reason_id": self.reason_price.id,
                    "loss_note": "12% cheaper",
                }
            ],
        )

    def test_close_as_rejected(self):
        order = self._make_order()

        order._close_as("rejected")

        self.assertEqual(order.outcome, "rejected")

    def test_reset_to_draft_reopens_and_forgets_the_loss(self):
        order = self._make_order()
        order._close_as("lost", loss_reason=self.reason_price, note="gone")

        order.action_draft()

        self.assertRecordValues(
            order,
            [{"outcome": "open", "loss_reason_id": False, "loss_note": False}],
        )

    def test_only_open_orders_can_be_closed_as_lost(self):
        order = self._confirmable_order()
        order.action_confirm()

        with self.assertRaisesRegex(UserError, "Only open quotations"):
            order._close_as("lost")
        self.assertEqual(order.outcome, "won")

    def test_close_as_refuses_an_outcome_that_is_not_a_loss(self):
        order = self._make_order()

        with self.assertRaises(ValueError):
            order._close_as("won")

    def test_copy_starts_open(self):
        order = self._make_order()
        order._close_as("lost", loss_reason=self.reason_price)

        self.assertRecordValues(
            order.copy(), [{"outcome": "open", "loss_reason_id": False}]
        )

    def test_loss_reason_domain_follows_the_direction(self):
        purchase_only = self.env["loss.reason"].create(
            {"name": "Supplier sold elsewhere", "scope": "purchase"}
        )
        sale_only = self.env["loss.reason"].create(
            {"name": "Customer chose a rival", "scope": "sale"}
        )
        order = self._make_order()

        allowed = self.env["loss.reason"].search(order._domain_loss_reason_id())

        self.assertIn(sale_only, allowed)
        self.assertIn(self.reason_price, allowed)
        self.assertNotIn(purchase_only, allowed)
