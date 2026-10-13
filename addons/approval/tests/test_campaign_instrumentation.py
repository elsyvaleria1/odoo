import ast
import logging
import re
from pathlib import Path
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import ApprovalCommon
from odoo.addons.approval.models import approval_trace as trace

RAISE = re.compile(r"^\s*raise (UserError|ValidationError|AccessError)\(")
REFUSAL_EVENT = re.compile(r"trace\.REFUSAL\.event\(")

REPORTED_BY_ITS_CALLERS = frozenset({"_raise_not_assigned_approver"})

REFUSAL_WITHOUT_A_RAISE = frozenset()

EMPTY_BY_OMISSION = frozenset(
    {
        "_raise_approval_category_not_configured",
        "_raise_approval_category_not_matched",
    }
)

ADDON = Path(__file__).resolve().parents[1]


def _source_files():
    for folder in ("models", "wizards", "reports"):
        yield from sorted((ADDON / folder).glob("*.py"))


class TestCampaignRefusalCensus(ApprovalCommon):
    def test_a_green_flow_logs_no_refusal(self):
        category = self._make_category(
            name="Census Green",
            approvers=[self.approver_1, self.approver_2],
        )
        with self.assertNoLogs("odoo.approval.refusal", level="DEBUG"):
            request = self._prepare_request(category)
            request.with_user(self.approver_1).action_approve()
            request.with_user(self.approver_2).action_approve()
            self.assertEqual(request.state, "approved")
            request.with_user(self.approver_2).action_withdraw()
            self.assertEqual(request.state, "pending")
            request.with_user(self.approver_2).action_approve()
            self.assertEqual(request.state, "approved")
            request.with_user(self.manager_user).action_reset_to_draft()
            self.assertEqual(request.state, "new")
            request.action_confirm()

    def test_a_refused_call_names_its_own_kind(self):
        category = self._make_category(name="Census Red", approvers=[self.approver_1])
        request = self._prepare_request(category)
        with self.assertLogs("odoo.approval.refusal", level="DEBUG") as captured:
            with self.assertRaises(UserError):
                request.action_confirm()
        self.assertTrue(
            any("confirm_not_draft" in line for line in captured.output),
            captured.output,
        )
        self.assertTrue(
            any(f"request={request.id}" in line for line in captured.output),
            captured.output,
        )

    def test_every_raise_reports_a_refusal(self):
        unreported = []
        for path in _source_files():
            lines = path.read_text().split("\n")
            for index, line in enumerate(lines):
                if not RAISE.match(line):
                    continue
                if REFUSAL_EVENT.search("\n".join(lines[max(0, index - 14) : index])):
                    continue
                owner = next(
                    (
                        match.group(1)
                        for earlier in range(index, -1, -1)
                        if (match := re.match(r"^    def (\w+)", lines[earlier]))
                    ),
                    "?",
                )
                if owner in REPORTED_BY_ITS_CALLERS:
                    continue
                unreported.append(f"{path.name}:{index + 1} {owner}")
        self.assertEqual(unreported, [], "\n".join(unreported))

    def test_no_call_site_reads_the_model_name_attribute(self):
        needle = "self." + "_name"
        reads = {path.name: path.read_text().count(needle) for path in _source_files()}
        total = sum(reads.values())
        self.assertLessEqual(
            total,
            7,
            f"{total - 7} campaign call site(s) reach the model name through self: "
            f"{ {name: n for name, n in reads.items() if n} }. "
            "Pass the record instead: `record=self` renders model#id.",
        )

    def test_the_refusal_target_carries_only_refusals(self):
        misplaced = []
        for path in _source_files():
            tree = ast.parse(path.read_text())
            for holder in ast.walk(tree):
                if not isinstance(holder, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                raises = any(
                    isinstance(node, ast.Raise)
                    or (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr.startswith("_raise")
                    )
                    for node in ast.walk(holder)
                )
                for node in ast.walk(holder):
                    if not isinstance(node, ast.Call):
                        continue
                    target = node.func
                    if not (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Attribute)
                        and target.value.attr == "REFUSAL"
                    ):
                        continue
                    if raises or holder.name in REFUSAL_WITHOUT_A_RAISE:
                        continue
                    misplaced.append(f"{path.name}:{node.lineno} {holder.name}")
        self.assertEqual(
            misplaced,
            [],
            "these lines are on the `refusal` target inside a method that raises "
            f"nothing: {misplaced}. A question that is answered rather than declined "
            "belongs on `access`; anything else belongs on its own concern's target.",
        )

    def test_no_campaign_line_is_the_only_statement_of_a_body(self):
        traps = []
        for path in _source_files():
            tree = ast.parse(path.read_text())
            for holder in ast.walk(tree):
                if not isinstance(holder, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                body = [
                    node
                    for node in holder.body
                    if not (
                        isinstance(node, ast.Expr)
                        and isinstance(node.value, ast.Constant)
                    )
                ]
                if len(body) != 1 or not isinstance(body[0], ast.Expr):
                    continue
                call = body[0].value
                if not (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Attribute)
                    and isinstance(call.func.value.value, ast.Name)
                    and call.func.value.value.id == "trace"
                ):
                    continue
                if holder.name in EMPTY_BY_OMISSION:
                    continue
                traps.append(f"{path.name}:{holder.lineno} {holder.name}")
        self.assertEqual(
            traps,
            [],
            "removing the campaign would leave these bodies empty: "
            f"{traps}. Instrument the call site instead.",
        )

    def test_the_reported_kinds_are_distinct(self):
        kinds = []
        for path in _source_files():
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                target = node.func
                if not (
                    isinstance(target, ast.Attribute)
                    and target.attr == "event"
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr == "REFUSAL"
                ):
                    continue
                first = node.args[0]
                if isinstance(first, ast.Constant):
                    kinds.append(first.value)
        duplicated = sorted({kind for kind in kinds if kinds.count(kind) > 1})
        self.assertEqual(duplicated, [], f"kinds used twice: {duplicated}")


class TestCampaignSwallowedFailures(ApprovalCommon):
    ALLOWED_TO_STAY_SILENT = {
        "approval_trace.py": "the renderer degrades to <unrenderable>, which IS the report",
    }

    def test_no_handler_swallows_a_failure_without_a_word(self):
        offenders = []
        for path in _source_files():
            source = path.read_text()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Try):
                    continue
                for handler in node.handlers:
                    segment = ast.get_source_segment(source, handler) or ""
                    speaks = (
                        any(isinstance(n, ast.Raise) for n in ast.walk(handler))
                        or "_logger." in segment
                        or "trace." in segment
                    )
                    if speaks or path.name in self.ALLOWED_TO_STAY_SILENT:
                        continue
                    caught = ast.unparse(handler.type) if handler.type else "everything"
                    offenders.append(f"{path.name}:{handler.lineno} catches {caught}")
        self.assertEqual(offenders, [], "\n".join(offenders))


@tagged("post_install", "-at_install")
class TestCampaignMeasurement(ApprovalCommon):
    def setUp(self):
        super().setUp()
        trace.forget_perf_ledger()
        self.addCleanup(trace.forget_perf_ledger)

    def _shut_printing(self, target):
        logger = logging.getLogger(f"{trace.LOG_ROOT}.{target.name}")
        before = logger.level
        logger.setLevel(logging.WARNING)
        self.addCleanup(logger.setLevel, before)

    def test_a_span_is_timed_while_every_target_is_silent(self):
        self._shut_printing(trace.LIFECYCLE)
        self.assertFalse(trace.LIFECYCLE.on(), "the printing switch starts shut")
        with patch.object(trace, "_WATCH_NPLUSONE", True):
            with trace.LIFECYCLE.span("measured_but_not_printed", n=3) as span:
                span["sql"] = 1
            self.assertFalse(trace.LIFECYCLE.on(), "and stays shut while measuring")
        ledger = {row.call: row for row in trace.perf_ledger()}
        self.assertIn("measured_but_not_printed", ledger)
        self.assertEqual(ledger["measured_but_not_printed"].rows, 3)
        self.assertEqual(ledger["measured_but_not_printed"].sql, 1)

    def test_nothing_is_timed_when_neither_switch_is_open(self):
        self._shut_printing(trace.LIFECYCLE)
        self._shut_printing(trace.PERF)
        with (
            patch.object(trace, "_WATCH_NPLUSONE", False),
            patch.object(trace, "_SLOW_MS", None),
        ):
            with trace.LIFECYCLE.span("not_measured_at_all", n=3):
                pass
        self.assertEqual(trace.perf_ledger(), [])

    def test_a_query_per_record_is_named_on_the_perf_target(self):
        with (
            patch.object(trace, "_WATCH_NPLUSONE", True),
            self.assertLogs("odoo.approval.perf", level="INFO") as captured,
        ):
            with trace.ROUTING.span("one_query_each", n=10) as span:
                span["sql"] = 20
        self.assertTrue(
            any(
                "n_plus_one" in line and "per_row=2" in line for line in captured.output
            ),
            captured.output,
        )

    def test_a_batch_too_small_to_show_growth_is_not_named(self):
        with patch.object(trace, "_WATCH_NPLUSONE", True):
            with self.assertNoLogs("odoo.approval.perf", level="INFO"):
                with trace.ROUTING.span("two_rows", n=2) as span:
                    span["sql"] = 9

    def test_a_slow_call_is_named_and_a_fast_one_is_not(self):
        with patch.object(trace, "_SLOW_MS", 0.0):
            with self.assertLogs("odoo.approval.perf", level="INFO") as captured:
                with trace.LIFECYCLE.span("always_slow", n=1) as span:
                    span["sql"] = 0
        self.assertTrue(
            any("slow" in line for line in captured.output), captured.output
        )
        with patch.object(trace, "_SLOW_MS", 60_000.0):
            with self.assertNoLogs("odoo.approval.perf", level="INFO"):
                with trace.LIFECYCLE.span("never_slow", n=1) as span:
                    span["sql"] = 0

    def test_annotate_reports_the_work_the_batch_size_hides(self):
        with patch.object(trace, "_WATCH_NPLUSONE", True):
            with self.assertLogs("odoo.approval.perf", level="INFO") as captured:
                with trace.ROUTING.span("one_request_many_rows", n=1) as span:
                    trace.annotate(work=40)
                    span["sql"] = 40
        row = {r.call: r for r in trace.perf_ledger()}["one_request_many_rows"]
        self.assertEqual(row.rows, 40)
        self.assertEqual(row.sql_per_row, 1)
        self.assertTrue(any("n_plus_one" in line for line in captured.output))

    def test_annotate_outside_a_span_is_a_no_op(self):
        trace.annotate(work=7)
        self.assertEqual(trace.perf_ledger(), [])

    def test_the_ledger_reports_the_rates_a_reader_needs(self):
        with patch.object(trace, "_WATCH_NPLUSONE", True):
            for sql in (2, 4):
                with trace.STEPS.span("summed", n=5) as span:
                    span["sql"] = sql
        row = {r.call: r for r in trace.perf_ledger()}["summed"]
        self.assertEqual((row.calls, row.rows, row.sql), (2, 10, 6))
        self.assertEqual(row.sql_per_call, 3)
        self.assertEqual(row.sql_per_row, 0.6)
        self.assertGreater(row.total_ms, 0)
        self.assertLessEqual(row.worst_ms, row.total_ms)

    def test_a_wrapped_entry_point_is_timed_with_the_targets_quiet(self):
        category = self._make_category(
            name="Measured Confirm", approvers=[self.approver_1]
        )
        with patch.object(trace, "_WATCH_NPLUSONE", True):
            self._prepare_request(category)
        calls = {row.call for row in trace.perf_ledger()}
        self.assertIn("approval.request.action_confirm", calls)
        self.assertIn("approval.request._sync_approvers", calls)


@tagged("post_install", "-at_install")
class TestCampaignCallTraces(ApprovalCommon):
    def test_every_wrapped_method_exists(self):
        missing = [
            f"{model_name}.{method}"
            for model_name, methods in trace.CALL_TRACES.items()
            for method in methods
            if model_name in self.env.registry
            and not hasattr(self.env.registry[model_name], method)
        ]
        self.assertEqual(missing, [], "\n".join(missing))

    def test_every_wrapped_model_is_concrete(self):
        abstract = [
            model_name
            for model_name in trace.CALL_TRACES
            if model_name in self.env.registry and self.env[model_name]._abstract
        ]
        self.assertEqual(abstract, [], "\n".join(abstract))

    def test_every_target_name_is_declared(self):
        unknown = sorted(
            {
                target
                for methods in trace.CALL_TRACES.values()
                for target in methods.values()
            }
            - set(trace._BY_NAME)
        )
        self.assertEqual(unknown, [], "\n".join(unknown))
