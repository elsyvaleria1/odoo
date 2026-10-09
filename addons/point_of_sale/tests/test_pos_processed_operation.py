import logging
from datetime import timedelta
from uuid import uuid4

import requests

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import JsonRpcException, tagged
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

    def _cash_in(self, operation, amount=10, context=None):
        return self.Operation._call_once(
            operation,
            "pos.session",
            "try_cash_in_out",
            [[self.session.id], "in", amount, "float", False, {}],
            {"context": context or {}},
            lambda: self.session.try_cash_in_out("in", amount, "float", False, {}),
        )

    def test_the_operations_the_pos_client_queues_are_queueable(self):
        queued = {
            "pos.session": [
                "write",
                "try_cash_in_out",
                "remove_cash_in_out",
                "set_opening_control",
                "log_partner_message",
            ],
            "pos.order": ["write"],
            "pos.order.line": ["create"],
            "product.template": ["write"],
            "restaurant.table": ["create", "write"],
            "restaurant.floor": ["write"],
            "pos.prep.display": ["reset"],
        }
        for model, methods in queued.items():
            if model not in self.env:
                continue
            for method in methods:
                with self.subTest(model=model, method=method):
                    self.assertTrue(self.Operation._is_queueable(model, method))

    def test_only_pos_loaded_models_and_declared_methods_are_queueable(self):
        for model, method in (
            ("wizard.res.users.check.identity", "run_check"),
            ("res.users.apikeys", "unlink"),
            ("account.move.line", "write"),
            ("pos.session", "close_session_from_ui"),
            ("pos.session", "read"),
            ("pos.processed.operation", "unlink"),
            ("no.such.model", "create"),
        ):
            with self.subTest(model=model, method=method):
                self.assertFalse(self.Operation._is_queueable(model, method))
        self.assertTrue(self.Operation._is_queueable("res.partner", "unlink"))

    def test_a_replayed_operation_runs_once_and_answers_the_first_result(self):
        operation = str(uuid4())
        calls = []

        def create_partner():
            calls.append(1)
            return self.env["res.partner"].create({"name": "replayed"}).ids

        first = self.Operation._call_once(
            operation, "res.partner", "create", [{}], {}, create_partner
        )
        second = self.Operation._call_once(
            operation, "res.partner", "create", [{}], {}, create_partner
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
                operation,
                "pos.session",
                "remove_cash_in_out",
                [[self.session.id], "in", 10, "float", False, {}],
                {},
                lambda: None,
            )

    def test_a_uuid_replayed_with_other_arguments_is_refused(self):
        operation = str(uuid4())
        lines_before = len(self.session.statement_line_ids)
        self._cash_in(operation, amount=10)

        with self.assertRaises(AccessError):
            self._cash_in(operation, amount=20)

        self.session.invalidate_recordset(["statement_line_ids"])
        self.assertEqual(len(self.session.statement_line_ids), lines_before + 1)

    def test_a_replay_under_another_context_answers_the_first_result(self):
        operation = str(uuid4())
        lines_before = len(self.session.statement_line_ids)

        first = self._cash_in(operation, context={"lang": "en_US", "tz": "UTC"})
        second = self._cash_in(operation, context={"lang": "fr_FR"})

        self.assertEqual(first, second)
        self.session.invalidate_recordset(["statement_line_ids"])
        self.assertEqual(len(self.session.statement_line_ids), lines_before + 1)

    def test_an_operation_recorded_without_a_digest_still_replays(self):
        operation = str(uuid4())
        self._cash_in(operation)
        self.env.cr.execute(
            "UPDATE pos_processed_operation SET arguments_digest = NULL "
            "WHERE operation_uuid = %s",
            [operation],
        )
        lines_before = len(self.session.statement_line_ids)

        self._cash_in(operation, amount=20)

        self.session.invalidate_recordset(["statement_line_ids"])
        self.assertEqual(len(self.session.statement_line_ids), lines_before)

    def test_a_replay_rechecks_the_users_access_to_the_model(self):
        cashier = self.env["res.users"].create(
            {
                "name": "Demoted cashier",
                "login": "demoted_cashier",
                "group_ids": [
                    Command.link(self.env.ref("point_of_sale.group_pos_user").id)
                ],
            }
        )
        Operation = self.Operation.with_user(cashier)
        logged, created = str(uuid4()), str(uuid4())
        Operation._call_once(
            logged, "pos.session", "log_partner_message", [[1]], {}, lambda: None
        )
        Operation._call_once(created, "pos.order", "create", [[{}]], {}, lambda: [1])
        cashier.group_ids -= self.env.ref("point_of_sale.group_pos_user")

        for operation, model, method, args in (
            (logged, "pos.session", "log_partner_message", [[1]]),
            (created, "pos.order", "create", [[{}]]),
        ):
            with self.subTest(method=method), self.assertRaises(AccessError) as refused:
                Operation._call_once(
                    operation, model, method, args, {}, lambda: self.fail("ran")
                )
            self.assertNotIn("already processed", str(refused.exception))

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
                operation,
                "pos.session",
                "try_cash_in_out",
                [[self.session.id], "in", 10, "float", False, {}],
                {},
                lambda: None,
            )

    def test_a_failed_operation_leaves_no_record_of_itself(self):
        operation = str(uuid4())

        def fail():
            raise AccessError("refused")

        with self.assertRaises(AccessError):
            with self.env.cr.savepoint():
                self.Operation._call_once(
                    operation,
                    "pos.session",
                    "try_cash_in_out",
                    [[self.session.id], "in", 10, "float", False, {}],
                    {},
                    fail,
                )

        lines_before = len(self.session.statement_line_ids)
        self._cash_in(operation)
        self.session.invalidate_recordset(["statement_line_ids"])
        self.assertEqual(len(self.session.statement_line_ids), lines_before + 1)

    def test_a_result_is_replayed_exactly_as_first_answered(self):
        operation = str(uuid4())
        answer = {"zone": "a\u0000b", "after": [1.5, None, "\ud800"], "a": True}

        first = self.Operation._call_once(
            operation, "res.partner", "create", [{}], {}, lambda: answer
        )
        second = self.Operation._call_once(
            operation, "res.partner", "create", [{}], {}, lambda: self.fail("replayed")
        )

        self.assertEqual(first, answer)
        self.assertEqual(second, answer)
        self.assertEqual(list(second), ["zone", "after", "a"])

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

    def test_a_read_carrying_an_operation_uuid_is_not_recorded(self):
        Operation = self.env["pos.processed.operation"]
        self.addCleanup(
            self.set_registry_readonly_mode, type(self)._registry_readonly_enabled
        )
        for replica in (True, False):
            # without a read replica a read-only route runs on a read/write cursor
            self.set_registry_readonly_mode(replica)
            with self.subTest(replica=replica):
                operation = str(uuid4())
                read = {
                    "model": "pos.session",
                    "method": "read",
                    "args": [[self.pos_session.id], ["name"]],
                    "kwargs": {"context": {"pos_operation_uuid": operation}},
                }
                self.call_jsonrpc("/web/dataset/call_kw/pos.session/read", read)
                self.pos_session.sudo().name = f"Renamed, replica={replica}"
                self.env.flush_all()

                second = self.call_jsonrpc(
                    "/web/dataset/call_kw/pos.session/read", read
                )

                self.assertEqual(second[0]["name"], f"Renamed, replica={replica}")
                self.assertFalse(Operation.search([("operation_uuid", "=", operation)]))

                written = str(uuid4())
                self._call(
                    "try_cash_in_out",
                    [[self.pos_session.id], "in", 10, "float", False, {}],
                    written,
                )
                self.assertTrue(Operation.search([("operation_uuid", "=", written)]))

    def test_a_call_outside_the_queued_operations_is_a_plain_call(self):
        settings = self.env["res.users.settings"]._get_or_create_for_user(self.pos_user)
        for operation in (str(uuid4()), "not-a-uuid"):
            with self.subTest(operation=operation):
                self.call_jsonrpc(
                    "/web/dataset/call_kw/res.users.settings/set_res_users_settings",
                    {
                        "model": "res.users.settings",
                        "method": "set_res_users_settings",
                        "args": [[settings.id], {"use_push_to_talk": True}],
                        "kwargs": {"context": {"pos_operation_uuid": operation}},
                    },
                )

                self.assertFalse(
                    self.env["pos.processed.operation"].search_count(
                        [("operation_uuid", "=", operation)]
                    )
                )

    @mute_logger("odoo.http")
    def test_a_cash_move_replayed_over_rpc_with_another_amount_is_refused(self):
        operation = str(uuid4())
        lines_before = len(self._cash_lines())
        self._call(
            "try_cash_in_out",
            [[self.pos_session.id], "in", 10, "float", False, {}],
            operation,
        )

        with self.assertRaises(JsonRpcException) as refused:
            self._call(
                "try_cash_in_out",
                [[self.pos_session.id], "in", 1000, "float", False, {}],
                operation,
            )

        self.assertEqual(str(refused.exception), "odoo.exceptions.AccessError")
        self.assertEqual(len(self._cash_lines()), lines_before + 1)

    @mute_logger("odoo.http")
    def test_a_replay_over_rpc_after_losing_pos_access_is_refused(self):
        operation = str(uuid4())
        args = [[self.pos_session.id], "in", 10, "float", False, {}]
        first = self._call("try_cash_in_out", args, operation)
        self.assertEqual(self._call("try_cash_in_out", args, operation), first)
        self.pos_user.group_ids -= self.env.ref("point_of_sale.group_pos_user")
        self.env.flush_all()

        with self.assertRaises(JsonRpcException) as refused:
            self._call("try_cash_in_out", args, operation)

        self.assertEqual(str(refused.exception), "odoo.exceptions.AccessError")

    @mute_logger("odoo.http")
    def test_malformed_kwargs_get_the_plain_call_kw_answer(self):
        for kwargs in ([1, 2], "context"):
            with (
                self.subTest(kwargs=kwargs),
                self.assertRaises(JsonRpcException) as refused,
            ):
                self.call_jsonrpc(
                    "/web/dataset/call_kw/pos.session/read",
                    {
                        "model": "pos.session",
                        "method": "read",
                        "args": [[self.pos_session.id], ["name"]],
                        "kwargs": kwargs,
                    },
                )
            self.assertNotEqual(str(refused.exception), "builtins.AttributeError")

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
            [[session_id], "in", 10, "float", False, {}],
            {},
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

    def test_a_replay_of_an_operation_that_committed_then_failed_is_refused(self):
        with self.leave_registry_test_mode():
            session_id = self._commit_session()
            operation = str(uuid4())
            args = [[session_id], "in", 10, "float", False, {}]

            with self.registry.cursor() as cr:
                session = self._env(cr)["pos.session"].browse(session_id)

                def commit_then_fail():
                    session.try_cash_in_out("in", 10, "float", False, {})
                    cr.commit()
                    raise UserError("failed after its commit")

                with self.assertRaises(UserError):
                    self._env(cr)["pos.processed.operation"]._call_once(
                        operation,
                        "pos.session",
                        "try_cash_in_out",
                        args,
                        {},
                        commit_then_fail,
                    )
                cr.rollback()

            with self.registry.cursor() as cr:
                with self.assertRaisesRegex(UserError, "never recorded"):
                    self._env(cr)["pos.processed.operation"]._call_once(
                        operation,
                        "pos.session",
                        "try_cash_in_out",
                        args,
                        {},
                        lambda: self.fail("ran again"),
                    )
                lines = (
                    self._env(cr)["pos.session"].browse(session_id).statement_line_ids
                )
                self.assertEqual(len(lines), 1)
