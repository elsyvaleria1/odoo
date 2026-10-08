import logging
import threading
import time
from copy import deepcopy
from uuid import uuid4

import psycopg.errors

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.service.transaction import retrying
from odoo.tests import TransactionCase, tagged
from odoo.tools import SQL, mute_logger

_logger = logging.getLogger(__name__)


def _id_marks(cr):
    cr.execute(
        """
        SELECT t.relname, COALESCE(pg_sequence_last_value(s.oid), 0)
          FROM pg_class s
          JOIN pg_depend d ON d.objid = s.oid
                          AND d.classid = 'pg_class'::regclass
                          AND d.refclassid = 'pg_class'::regclass
                          AND d.deptype IN ('a', 'i')
          JOIN pg_class t ON t.oid = d.refobjid
          JOIN pg_attribute a ON a.attrelid = t.oid
                             AND a.attnum = d.refobjsubid
                             AND a.attname = 'id'
         WHERE s.relkind = 'S'
           AND t.relkind = 'r'
           AND t.relnamespace = 'public'::regnamespace
           AND t.relname NOT LIKE 'orm_signaling%%'
        """
    )
    return dict(cr.fetchall())


@tagged("post_install", "-at_install")
class TestPosOrderConcurrency(TransactionCase):
    @mute_logger("odoo.db.cursor")
    def _drop_rows_committed_since(self, marks):
        with self.leave_registry_test_mode(), self.registry.cursor() as cr:
            pending = {
                table
                for table, last_id in _id_marks(cr).items()
                if last_id > marks.get(table, 0)
            }
            while pending:
                dropped = set()
                for table in sorted(pending):
                    try:
                        with cr.savepoint(flush=False):
                            cr.execute(
                                SQL(
                                    "DELETE FROM %s WHERE id > %s",
                                    SQL.identifier(table),
                                    marks.get(table, 0),
                                )
                            )
                    except (
                        psycopg.errors.ForeignKeyViolation,
                        psycopg.errors.RestrictViolation,
                    ):
                        continue
                    except psycopg.errors.InsufficientPrivilege:
                        # an append-only audit log keeps its rows by design
                        pass
                    dropped.add(table)
                if not dropped:
                    raise AssertionError(
                        f"rows committed by the test are still referenced: {sorted(pending)}"
                    )
                pending -= dropped
            cr.commit()

    def _env(self, cr):
        return self.env(cr=cr, user=self.admin_id)

    def _commit_fixture(self, terminals=1):
        self.admin_id = self.env.ref("base.user_admin").id
        with self.registry.cursor() as cr:
            marks = _id_marks(cr)
        self.addCleanup(self._drop_rows_committed_since, marks)
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

    def _is_waiting_on_a_lock(self, cr, pid):
        cr.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid = %s AND NOT granted)",
            [pid],
        )
        return cr.fetchone()[0]

    def _race(self, first, second):
        # second's snapshot predates first's commit, as when two terminals
        # settle at the same moment; retrying() is what serves their RPCs
        first_worked = threading.Event()
        first_committed = threading.Event()
        attempts = []
        outcome = {}
        with (
            self.registry.cursor() as cr_first,
            self.registry.cursor() as cr_second,
        ):
            env_first, env_second = self._env(cr_first), self._env(cr_second)
            cr_second.execute("SELECT pg_backend_pid()")
            second_pid = cr_second.fetchone()[0]

            def attempt():
                attempts.append(len(attempts) + 1)
                (first_worked if len(attempts) == 1 else first_committed).wait(30)
                return second(env_second)

            def run_second():
                try:
                    outcome["result"] = retrying(attempt, env_second)
                except Exception as error:
                    outcome["error"] = error

            thread = threading.Thread(target=run_second)
            thread.start()
            try:
                first(env_first)
                env_first.flush_all()
            finally:
                first_worked.set()
            waited = False
            deadline = time.monotonic() + 15
            while (
                thread.is_alive() and len(attempts) < 2 and time.monotonic() < deadline
            ):
                if self._is_waiting_on_a_lock(cr_first, second_pid):
                    waited = True
                    break
                time.sleep(0.02)
            cr_first.commit()
            first_committed.set()
            thread.join(60)
        _logger.debug(
            "race: waited=%s attempts=%s outcome=%s", waited, len(attempts), outcome
        )
        return waited, len(attempts), outcome

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
