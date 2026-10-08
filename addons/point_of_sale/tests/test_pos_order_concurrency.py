from copy import deepcopy
from uuid import uuid4

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common_race import PosRaceCase


@tagged("post_install", "-at_install")
class TestPosOrderConcurrency(PosRaceCase):
    def _commit_fixture(self, terminals=1):
        self.admin_id = self.env.ref("base.user_admin").id
        self._drop_rows_committed_from_now()
        with self.registry.cursor() as cr:
            env = self._env(cr)
            PosConfig = env["pos.config"]
            configs = PosConfig.create(
                [
                    {
                        "name": f"race {uuid4().hex[:8]}",
                        "payment_method_ids": [
                            Command.set(PosConfig._create_cash_payment_method().ids)
                        ],
                    }
                    for _ in range(terminals)
                ]
            )
            for config in configs:
                config.open_ui()
                config.current_session_id.set_opening_control(0, None)
            self.terminals = [
                {
                    "session_id": config.current_session_id.id,
                    "pricelist_id": config.pricelist_id.id,
                    "cash_method_id": config.payment_method_ids.id,
                }
                for config in configs
            ]
            self.product_id = (
                env["product.product"]
                .create(
                    {
                        "name": "Race product",
                        "type": "service",
                        "list_price": 10,
                        "available_in_pos": True,
                        "taxes_id": False,
                    }
                )
                .id
            )
            original = self._sync(env, self._order_vals(1, paid=True))
            self.original_line_id = original.lines.id
            cr.commit()

    def _order_vals(self, qty, paid, refunded_line_id=False, terminal=0):
        terminal = self.terminals[terminal]
        line = {
            "product_id": self.product_id,
            "qty": qty,
            "price_unit": 10,
            "price_subtotal": 10 * qty,
            "price_subtotal_incl": 10 * qty,
            "tax_ids": [],
        }
        if refunded_line_id:
            line["refunded_orderline_id"] = refunded_line_id
        uuid = str(uuid4())
        return {
            "uuid": uuid,
            "pos_reference": f"race-{uuid}",
            "sequence_number": 0,
            "session_id": terminal["session_id"],
            "pricelist_id": terminal["pricelist_id"],
            "user_id": self.admin_id,
            "date_order": fields.Datetime.to_string(fields.Datetime.now()),
            "last_order_preparation_change": "{}",
            "lines": [(0, 0, line)],
            "state": "paid" if paid else "draft",
            "amount_total": 10 * qty,
            "amount_tax": 0,
            "amount_paid": 10 * qty if paid else 0,
            "amount_return": 0,
            "payment_ids": [
                (
                    0,
                    0,
                    {
                        "amount": 10 * qty,
                        "payment_method_id": terminal["cash_method_id"],
                        "name": fields.Datetime.now(),
                    },
                )
            ]
            if paid
            else [],
        }

    def _sync(self, env, vals):
        env["pos.order"].sync_from_ui([deepcopy(vals)])
        return env["pos.order"].search([("uuid", "=", vals["uuid"])])

    def _pay_from_backend(self, env, order_id):
        order = env["pos.order"].browse(order_id)
        env["wizard.pos.order.pay"].with_context(
            active_model="pos.order", active_id=order.id
        ).create(
            {
                "amount": order.amount_total,
                "payment_method_id": self.terminals[0]["cash_method_id"],
                "config_id": order.config_id.id,
            }
        ).action_make_payment()
        return order.state

    @mute_logger("odoo.service.model", "odoo.service.transaction")
    def test_concurrent_backend_refund_payments_are_serialized(self):
        with self.leave_registry_test_mode():
            self._commit_fixture()
            with self.registry.cursor() as cr:
                env = self._env(cr)
                refund_ids = [
                    self._sync(
                        env, self._order_vals(-1, False, self.original_line_id)
                    ).id
                    for _ in range(2)
                ]
                cr.commit()

            waited, attempts, outcome = self._race(
                lambda env: self._pay_from_backend(env, refund_ids[0]),
                lambda env: self._pay_from_backend(env, refund_ids[1]),
            )

            with self.registry.cursor() as cr:
                states = self._env(cr)["pos.order"].browse(refund_ids).mapped("state")
        self.assertTrue(
            waited, "the second payment must wait for the first one's refund"
        )
        self.assertEqual(attempts, 2, "and then be retried with a fresh snapshot")
        self.assertIsInstance(
            outcome.get("error"),
            ValidationError,
            "the retry must count the first refund and refuse the over-refund",
        )
        self.assertEqual(states, ["paid", "draft"])

    @mute_logger(
        "odoo.service.model",
        "odoo.service.transaction",
        "odoo.addons.point_of_sale.models.pos_order",
    )
    def test_refunds_synced_from_two_tills_at_once_flag_the_over_refund(self):
        with self.leave_registry_test_mode():
            self._commit_fixture(terminals=2)
            first_vals = self._order_vals(-1, True, self.original_line_id, 0)
            second_vals = self._order_vals(-1, True, self.original_line_id, 1)

            waited, attempts, outcome = self._race(
                lambda env: self._sync(env, first_vals),
                lambda env: self._sync(env, second_vals).id,
            )

            with self.registry.cursor() as cr:
                second = self._env(cr)["pos.order"].browse(outcome.get("result"))
                flagged = bool(second.exists()) and any(
                    "returns more than was sold" in body
                    for body in second.message_ids.mapped("body")
                )
        self.assertNotIn("error", outcome, "a till's refund is recorded, never refused")
        self.assertTrue(waited, "the second sync must wait for the first refund")
        self.assertEqual(attempts, 2, "and then be retried with a fresh snapshot")
        self.assertTrue(flagged, "the retried refund must be flagged as an over-refund")

    @mute_logger("odoo.service.model", "odoo.service.transaction")
    def test_a_sync_retried_while_the_first_still_runs_returns_the_saved_order(self):
        with self.leave_registry_test_mode():
            self._commit_fixture()
            vals = self._order_vals(1, True)

            _waited, attempts, outcome = self._race(
                lambda env: self._sync(env, vals),
                lambda env: env["pos.order"].sync_from_ui([deepcopy(vals)])[
                    "pos.order"
                ],
            )

            with self.registry.cursor() as cr:
                saved = self._env(cr)["pos.order"].search([("uuid", "=", vals["uuid"])])
        self.assertNotIn("error", outcome, "the client must not get an error")
        self.assertEqual(attempts, 2, "the retry is what finds the saved order")
        self.assertEqual(len(saved), 1)
        self.assertEqual(
            [row["id"] for row in outcome["result"] if row["uuid"] == vals["uuid"]],
            saved.ids,
        )
