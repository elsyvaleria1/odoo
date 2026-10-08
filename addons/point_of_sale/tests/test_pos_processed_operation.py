import logging
from datetime import timedelta
from uuid import uuid4

import requests

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.point_of_sale.models.pos_processed_operation import RETENTION_DAYS
from odoo.addons.point_of_sale.tests.common import CommonPosTest
from odoo.addons.point_of_sale.tests.common_race import PosRaceCase
from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosProcessedOperation(CommonPosTest):
    def setUp(self):
        super().setUp()
        self.pos_config_usd.open_ui()
        self.session = self.pos_config_usd.current_session_id
        self.Operation = self.env["pos.processed.operation"]

    def _cash_in(self, operation, amount=10):
        return self.Operation._call_once(
            operation,
            "pos.session",
            "try_cash_in_out",
            lambda: self.session.try_cash_in_out("in", amount, "float", False, {}),
        )

    def test_a_replayed_operation_runs_once_and_answers_the_first_result(self):
        operation = str(uuid4())
        calls = []

        def create_partner():
            calls.append(1)
            return self.env["res.partner"].create({"name": "replayed"}).ids

        first = self.Operation._call_once(
            operation, "res.partner", "create", create_partner
        )
        second = self.Operation._call_once(
            operation, "res.partner", "create", create_partner
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(first, second)

    def test_a_replayed_cash_move_is_booked_once(self):
        operation = str(uuid4())
        lines_before = len(self.session.statement_line_ids)

        self._cash_in(operation)
        self._cash_in(operation)

        self.session.invalidate_recordset(["statement_line_ids"])
        self.assertEqual(len(self.session.statement_line_ids), lines_before + 1)

    def test_distinct_operations_both_run(self):
        lines_before = len(self.session.statement_line_ids)

        self._cash_in(str(uuid4()))
        self._cash_in(str(uuid4()))

        self.session.invalidate_recordset(["statement_line_ids"])
        self.assertEqual(len(self.session.statement_line_ids), lines_before + 2)

    def test_a_uuid_reused_for_another_operation_is_refused(self):
        operation = str(uuid4())
        self._cash_in(operation)

        with self.assertRaises(AccessError):
            self.Operation._call_once(
                operation, "pos.session", "remove_cash_in_out", lambda: None
            )

    def test_another_user_cannot_read_an_operation_result(self):
        operation = str(uuid4())
        self._cash_in(operation)
        cashier = self.env["res.users"].create(
            {
                "name": "Other cashier",
                "login": "other_cashier",
                "group_ids": [
                    Command.link(self.env.ref("point_of_sale.group_pos_user").id)
                ],
            }
        )

        with self.assertRaises(AccessError):
            self.Operation.with_user(cashier)._call_once(
                operation, "pos.session", "try_cash_in_out", lambda: None
            )

    def test_a_failed_operation_leaves_no_record_of_itself(self):
        operation = str(uuid4())

        def fail():
            raise AccessError("refused")

        with self.assertRaises(AccessError):
            with self.env.cr.savepoint():
                self.Operation._call_once(
                    operation, "pos.session", "try_cash_in_out", fail
                )

        lines_before = len(self.session.statement_line_ids)
        self._cash_in(operation)
        self.session.invalidate_recordset(["statement_line_ids"])
        self.assertEqual(len(self.session.statement_line_ids), lines_before + 1)

    def test_processed_operations_are_forgotten_after_the_retention(self):
        old, recent = str(uuid4()), str(uuid4())
        self._cash_in(old)
        self._cash_in(recent)
        self.env.cr.execute(
            "UPDATE pos_processed_operation SET processed_at = %s WHERE operation_uuid = %s",
            [
                fields.Datetime.now() - timedelta(days=RETENTION_DAYS + 1),
                old,
            ],
        )

        self.Operation._gc_processed_operations()

        self.assertEqual(
            self.Operation.search([("operation_uuid", "in", [old, recent])]).mapped(
                "operation_uuid"
            ),
            [recent],
        )


@tagged("post_install", "-at_install")
class TestPosProcessedOperationRpc(TestPointOfSaleHttpCommon):
    def setUp(self):
        super().setUp()
        self.pos_user.group_ids += self.env.ref("account.group_account_basic")
        self.main_pos_config.with_user(self.pos_user).open_ui()
        self.pos_session = self.main_pos_config.current_session_id
        self.authenticate("pos_user", "pos_user")

    def _call(self, method, args, operation):
        return self.call_jsonrpc(
            f"/web/dataset/call_kw/pos.session/{method}",
            {
                "model": "pos.session",
                "method": method,
                "args": args,
                "kwargs": {"context": {"pos_operation_uuid": operation}},
            },
        )

    def _cash_lines(self):
        self.env.invalidate_all()
        return self.pos_session.statement_line_ids

    def test_a_cash_move_replayed_over_rpc_is_booked_once(self):
        operation = str(uuid4())
        args = [[self.pos_session.id], "in", 10, "float", False, {}]
        lines_before = len(self._cash_lines())

        first = self._call("try_cash_in_out", args, operation)
        second = self._call("try_cash_in_out", args, operation)

        self.assertEqual(len(self._cash_lines()), lines_before + 1)
        self.assertEqual(first, second)

    def test_a_cash_move_removal_replayed_over_rpc_succeeds(self):
        self._call(
            "try_cash_in_out",
            [[self.pos_session.id], "in", 10, "float", False, {}],
            str(uuid4()),
        )
        line = self._cash_lines()[-1:]
        operation = str(uuid4())
        args = [[self.pos_session.id], line.id, False]

        self._call("remove_cash_in_out", args, operation)
        self._call("remove_cash_in_out", args, operation)

        self.assertFalse(line.exists())

    @mute_logger("odoo.http")
    def test_a_malformed_operation_uuid_is_refused(self):
        lines_before = len(self._cash_lines())

        with self.assertRaises(requests.HTTPError) as refused:
            self._call(
                "try_cash_in_out",
                [[self.pos_session.id], "in", 10, "float", False, {}],
                "not-a-uuid",
            )

        self.assertEqual(refused.exception.response.status_code, 400)
        self.assertEqual(len(self._cash_lines()), lines_before)


@tagged("post_install", "-at_install")
class TestPosProcessedOperationConcurrency(PosRaceCase):
    def _commit_session(self):
        self.admin_id = self.env.ref("base.user_admin").id
        self._drop_rows_committed_from_now()
        with self.registry.cursor() as cr:
            env = self._env(cr)
            PosConfig = env["pos.config"]
            config = PosConfig.create(
                {
                    "name": f"replay {uuid4().hex[:8]}",
                    "payment_method_ids": [
                        Command.set(PosConfig._create_cash_payment_method().ids)
                    ],
                }
            )
            config.open_ui()
            session_id = config.current_session_id.id
            cr.commit()
        return session_id

    def _cash_in(self, env, session_id, operation):
        session = env["pos.session"].browse(session_id)
        return env["pos.processed.operation"]._call_once(
            operation,
            "pos.session",
            "try_cash_in_out",
            lambda: (
                session.try_cash_in_out("in", 10, "float", False, {})
                or session.statement_line_ids.ids
            ),
        )

    @mute_logger("odoo.service.model", "odoo.service.transaction")
    def test_a_replay_racing_its_first_attempt_books_the_move_once(self):
        with self.leave_registry_test_mode():
            session_id = self._commit_session()
            operation = str(uuid4())
            first_result = []

            waited, attempts, outcome = self._race(
                lambda env: first_result.append(
                    self._cash_in(env, session_id, operation)
                ),
                lambda env: self._cash_in(env, session_id, operation),
            )

            with self.registry.cursor() as cr:
                lines = (
                    self._env(cr)["pos.session"].browse(session_id).statement_line_ids
                )
                line_ids = lines.ids
        _logger.debug(
            "replay race: waited=%s attempts=%s outcome=%s lines=%s",
            waited,
            attempts,
            outcome,
            line_ids,
        )
        self.assertNotIn("error", outcome, "the replay must not fail")
        self.assertTrue(waited, "the replay must wait for the first attempt")
        self.assertEqual(attempts, 2, "and then be retried with a fresh snapshot")
        self.assertEqual(len(line_ids), 1, "the cash move must be booked once")
        self.assertEqual(outcome["result"], first_result[0])
        self.assertEqual(outcome["result"], line_ids)
