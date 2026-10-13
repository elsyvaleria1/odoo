
from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from functools import wraps
from typing import Any, NamedTuple

from odoo import models

LOG_ROOT = "odoo.approval"
TRACE_ORIGIN = "_approval_trace_origin"

_QUIET_DEFAULT = logging.WARNING
_MAX_IDS = 10
_MAX_ITEMS = 50
_MAX_CHARS = 200

_NPLUSONE_MIN_ROWS = 4
SLOW_MS_VAR = "APPROVAL_TRACE_SLOW_MS"
NPLUSONE_VAR = "APPROVAL_TRACE_NPLUSONE"

_open = threading.local()
_depth = threading.local()

_perf: dict[str, list[float]] = {}


def _env_float(name: str) -> float | None:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        logging.getLogger(f"{LOG_ROOT}.perf").warning(
            "Ignoring %s=%r: not a number of milliseconds.", name, raw
        )
        return None


def _env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
    )


_SLOW_MS = _env_float(SLOW_MS_VAR)
_WATCH_NPLUSONE = _env_flag(NPLUSONE_VAR) or _SLOW_MS is not None


def _render_ids(ids: Iterable[Any]) -> str:
    shown = list(ids)[: _MAX_IDS + 1]
    if len(shown) > _MAX_IDS:
        return f"[{','.join(str(i) for i in shown[:_MAX_IDS])},+]"
    return f"[{','.join(str(i) for i in shown)}]"


def _render_value(value: Any) -> str:
    if isinstance(value, models.BaseModel):
        if len(value) == 1 and value.id:
            return f"{value._name}#{value.id}"
        return f"{value._name}#{_render_ids(value._ids)}"
    if value is None or isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, Mapping):
        inner = ",".join(
            f"{key}:{_render_value(item)}"
            for key, item in list(value.items())[:_MAX_IDS]
        )
        return f"{{{inner}}}"
    if isinstance(value, (set, frozenset)):
        return _render_ids(sorted(value, key=repr))
    if isinstance(value, (list, tuple)):
        return _render_ids(_render_value(item) for item in value)
    text = str(value)
    if len(text) > _MAX_CHARS:
        text = f"{text[:_MAX_CHARS]}..."
    return text if text and not any(char.isspace() for char in text) else repr(text)


def _render(value: Any) -> str:
    try:
        return _render_value(value)
    except Exception:
        return "<unrenderable>"


def _line(event: str, fields: Mapping[str, Any]) -> str:
    if not fields:
        return event
    rendered = " ".join(f"{key}={_render(value)}" for key, value in fields.items())
    return f"{event} {rendered}"


class _OffSpan(dict[str, Any]):
    def __setitem__(self, key: Any, value: Any) -> None:
        pass


_OFF_SPAN = _OffSpan()


class Target:
    __slots__ = ("_items_logger", "_logger", "name")

    def __init__(self, name: str) -> None:
        self.name = name
        self._logger = logging.getLogger(f"{LOG_ROOT}.{name}")
        self._items_logger = logging.getLogger(f"{LOG_ROOT}.{name}.items")

    def on(self) -> bool:
        return self._logger.isEnabledFor(logging.DEBUG)

    def items_on(self) -> bool:
        return self._items_logger.isEnabledFor(logging.DEBUG)

    def note(self, event: str, **fields: Any) -> None:
        if self._logger.isEnabledFor(logging.INFO):
            self._logger.info(_line(event, fields))

    def event(self, event: str, **fields: Any) -> None:
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug(_line(event, fields))

    def items(
        self,
        event: str,
        entries: Iterable[Mapping[str, Any]]
        | Callable[[], Iterable[Mapping[str, Any]]],
    ) -> None:
        if not self._items_logger.isEnabledFor(logging.DEBUG):
            return
        resolved = entries() if callable(entries) else entries
        for index, entry in enumerate(resolved):
            if index >= _MAX_ITEMS:
                self._items_logger.debug(_line(event, {"truncated_after": _MAX_ITEMS}))
                return
            self._items_logger.debug(_line(event, {"i": index, **entry}))

    @contextmanager
    def span(self, event: str, **fields: Any) -> Iterator[dict[str, Any]]:
        printing = self._logger.isEnabledFor(logging.DEBUG)
        if not (printing or accounting()):
            yield _OFF_SPAN
            return
        depth = getattr(_depth, "value", 0)
        _depth.value = depth + 1
        spanned: dict[str, Any] = dict(fields)
        open_spans = getattr(_open, "stack", None)
        if open_spans is None:
            open_spans = _open.stack = []
        open_spans.append(spanned)
        outcome = "ok"
        started = time.perf_counter()
        try:
            yield spanned
        except Exception as error:
            outcome = f"raised:{type(error).__name__}"
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            _depth.value = depth
            open_spans.pop()
            _account(event, elapsed_ms, spanned)
            if printing:
                self._logger.debug(
                    _line(
                        event, {**spanned, "ms": elapsed_ms, "d": depth, "r": outcome}
                    ),
                )
            _report_outliers(event, elapsed_ms, spanned)


ACCESS = Target("access")
ACTIVITY = Target("activity")
ATTACHMENT = Target("attachment")
BINDING = Target("binding")
BUTTON = Target("button")
COMPUTE = Target("compute")
CRON = Target("cron")
CRUD = Target("crud")
DECISION = Target("decision")
DEGRADED = Target("degraded")
DELEGATION = Target("delegation")
DOCUMENT = Target("document")
EDITOR = Target("editor")
ESCALATION = Target("escalation")
LIFECYCLE = Target("lifecycle")
MIXIN = Target("mixin")
PERF = Target("perf")
PREDICTION = Target("prediction")
REFUSAL = Target("refusal")
REGISTRY = Target("registry")
REPORT = Target("report")
ROUTING = Target("routing")
RULES = Target("rules")
SEARCH = Target("search")
SNAPSHOT = Target("snapshot")
STEPS = Target("steps")
SUBJECTS = Target("subjects")
SYNC = Target("sync")
TEMPLATE = Target("template")
WIZARD = Target("wizard")

_BY_NAME: dict[str, Target] = {
    target.name: target
    for target in (
        ACCESS,
        ACTIVITY,
        ATTACHMENT,
        BINDING,
        BUTTON,
        COMPUTE,
        CRON,
        CRUD,
        DECISION,
        DEGRADED,
        DELEGATION,
        DOCUMENT,
        EDITOR,
        ESCALATION,
        LIFECYCLE,
        MIXIN,
        PERF,
        PREDICTION,
        REFUSAL,
        REGISTRY,
        REPORT,
        ROUTING,
        RULES,
        SEARCH,
        SNAPSHOT,
        STEPS,
        SUBJECTS,
        SYNC,
        TEMPLATE,
        WIZARD,
    )
}


def _quiet_by_default() -> None:
    root = logging.getLogger(LOG_ROOT)
    if root.level == logging.NOTSET:
        root.setLevel(_QUIET_DEFAULT)


_quiet_by_default()


def accounting() -> bool:
    return _SLOW_MS is not None or _WATCH_NPLUSONE or PERF.on()


def annotate(**fields: Any) -> None:
    open_spans = getattr(_open, "stack", None)
    if open_spans:
        open_spans[-1].update(fields)


def _account(event: str, elapsed_ms: float, measured: Mapping[str, Any]) -> None:
    rows = measured.get("work") or measured.get("n") or 0
    sql = measured.get("sql") or 0
    entry = _perf.get(event)
    if entry is None:
        _perf[event] = [1, elapsed_ms, elapsed_ms, rows, sql]
        return
    entry[0] += 1
    entry[1] += elapsed_ms
    entry[2] = max(entry[2], elapsed_ms)
    entry[3] += rows
    entry[4] += sql


def _report_outliers(
    event: str, elapsed_ms: float, measured: Mapping[str, Any]
) -> None:
    rows = measured.get("work") or measured.get("n") or 0
    sql = measured.get("sql") or 0
    if _SLOW_MS is not None and elapsed_ms >= _SLOW_MS:
        PERF.note("slow", call=event, ms=elapsed_ms, n=rows, sql=sql)
    if _WATCH_NPLUSONE and rows >= _NPLUSONE_MIN_ROWS and sql >= rows:
        PERF.note(
            "n_plus_one",
            call=event,
            n=rows,
            sql=sql,
            per_row=sql / rows,
            ms=elapsed_ms,
        )


class LedgerRow(NamedTuple):
    call: str
    calls: int
    total_ms: float
    worst_ms: float
    rows: int
    sql: int

    @property
    def ms_per_call(self) -> float:
        return self.total_ms / self.calls

    @property
    def sql_per_call(self) -> float:
        return self.sql / self.calls

    @property
    def sql_per_row(self) -> float | None:
        return self.sql / self.rows if self.rows else None


def perf_ledger() -> list[LedgerRow]:
    return sorted(
        (
            LedgerRow(event, int(calls), total, worst, int(rows), int(sql))
            for event, (calls, total, worst, rows, sql) in _perf.items()
        ),
        key=lambda row: row.total_ms,
        reverse=True,
    )


def dump_perf_ledger(reset: bool = True, top: int | None = None) -> None:
    rows = perf_ledger()
    PERF.note(
        "ledger_begin",
        calls=sum(row.calls for row in rows),
        events=len(rows),
        total_ms=sum(row.total_ms for row in rows),
        slow_ms=_SLOW_MS,
        nplusone=_WATCH_NPLUSONE,
    )
    for row in rows[:top] if top else rows:
        PERF.note(
            "ledger",
            call=row.call,
            calls=row.calls,
            total_ms=row.total_ms,
            worst_ms=row.worst_ms,
            avg_ms=row.ms_per_call,
            rows=row.rows,
            sql=row.sql,
            sql_per_call=row.sql_per_call,
            sql_per_row=row.sql_per_row,
        )
    if reset:
        _perf.clear()


def forget_perf_ledger() -> None:
    _perf.clear()


CALL_TRACES: dict[str, dict[str, str]] = {
    "approval.request": {
        "create": "crud",
        "write": "crud",
        "unlink": "crud",
        "copy": "crud",
        "copy_data": "crud",
        "action_confirm": "lifecycle",
        "action_approve": "lifecycle",
        "action_refuse": "lifecycle",
        "action_cancel": "lifecycle",
        "action_reset_to_draft": "lifecycle",
        "action_resubmit": "lifecycle",
        "action_request_change": "lifecycle",
        "action_withdraw": "lifecycle",
        "action_withdraw_approver": "lifecycle",
        "action_approve_bulk": "lifecycle",
        "action_refuse_bulk": "lifecycle",
        "_action_bulk_decision": "lifecycle",
        "_apply_decision": "decision",
        "_force_terminal": "lifecycle",
        "_force_draft": "lifecycle",
        "_revoke": "lifecycle",
        "_approve_without_decision": "lifecycle",
        "_open_approval_round": "lifecycle",
        "_refuse_cascade": "lifecycle",
        "_withdraw_decided_steps": "decision",
        "_sync_approvers": "routing",
        "_extend_approvers_live": "routing",
        "_get_managed_approver_user_ids": "routing",
        "_get_rows_decidable_by": "access",
        "_get_default_escalation_manager": "escalation",
        "_get_desired_approvers": "routing",
        "_prepare_category_snapshot": "snapshot",
        "_check_auto_action_rules": "rules",
        "_get_applicable_steps": "steps",
        "_get_step_assignment": "steps",
        "_get_unmet_steps": "steps",
        "cron_smart_escalation": "cron",
        "cron_auto_expire": "cron",
        "cron_consent_approval": "cron",
        "_send_reminder": "escalation",
        "_escalate_to_manager": "escalation",
        "_compute_state": "compute",
        "_compute_sla_status": "compute",
        "_compute_approval_progress": "compute",
        "_compute_pending_approver_ids": "compute",
        "_compute_res_name": "compute",
        "_compute_can_withdraw": "compute",
        "_compute_is_pending_my_review": "compute",
        "_compute_user_ids": "compute",
        "_compute_count_attachment": "compute",
        "_compute_sla_elapsed_hours": "compute",
        "_compute_sla_remaining_hours": "compute",
        "_compute_approval_deadline": "compute",
        "_compute_is_overdue": "compute",
        "_compute_user_approver_state": "compute",
        "_get_step_counts": "steps",
        "_get_blocking_unmet_steps": "steps",
        "_get_open_steps": "steps",
        "_get_domain_pending_review": "search",
        "_search_is_pending_my_review": "search",
        "_search_is_overdue": "search",
        "_search_sla_status": "search",
        "_predict_outcomes": "prediction",
        "_replay_bound_operation": "binding",
        "_check_access_write": "access",
        "_check_access_unlink": "access",
        "_check_locked_fields": "access",
        "_check_business_rules_unlink": "access",
        "_check_confirm": "lifecycle",
        "_retire_unasked_approval_activities": "activity",
        "_cancel_activities": "activity",
        "_lock_for_approval_action": "lifecycle",
    },
    "approval.approver": {
        "create": "crud",
        "write": "crud",
        "unlink": "crud",
        "action_approve": "decision",
        "action_refuse": "decision",
        "_create_activity": "activity",
        "_approve_for_every_step": "decision",
        "_compute_is_delegated": "delegation",
        "_delegation_date_buckets": "delegation",
        "_search_is_delegated": "search",
        "_is_notifiable": "activity",
        "_prepare_source_activity_vals": "activity",
        "_get_effective_approver": "delegation",
        "_check_access_create": "access",
        "_check_access_write": "access",
        "_check_access_unlink": "access",
    },
    "approval.category": {
        "create": "crud",
        "write": "crud",
        "_compute_rule_count": "compute",
        "create_request": "lifecycle",
        "_compute_kanban_dashboard": "compute",
        "_compute_count_request_to_validate": "compute",
    },
    "approval.category.step": {
        "_get_pool_user_ids": "steps",
        "_get_candidate_user_ids": "steps",
        "_is_applicable_to_request": "steps",
        "_is_applicable_to_document": "steps",
    },
    "approval.rule": {
        "_evaluate": "rules",
    },
    "approval.binding": {
        "_register_hook": "registry",
        "_unregister_hook": "registry",
        "_apply_to_registry": "registry",
        "_gate": "binding",
        "_run_admitted": "binding",
        "_enforce_at_checkpoint": "binding",
        "_raise_requests_for": "binding",
        "_replay": "binding",
        "_reset_coverage": "binding",
        "_approve_on_invoke": "binding",
        "_get_binding_ids": "binding",
        "_mark_invoked_run": "binding",
        "_get_requests_holding_decisions": "binding",
        "_get_covering_requests": "binding",
        "_get_button_steps": "button",
        "_get_action_binding_ids": "binding",
        "_get_names_of_gated_models": "button",
        "_get_covered_ids": "binding",
        "_get_snapshot": "binding",
        "get_button_approvals": "button",
        "check_button_approval": "button",
        "action_decide_approval": "button",
        "action_withdraw_decision": "button",
        "create_step_for_button": "editor",
        "action_open_button_steps": "editor",
    },
    "approval.template": {
        "action_create_request": "template",
        "_compute_usage_count": "compute",
    },
    "approval.refusal.reason": {
        "_compute_usage_count": "compute",
    },
    "approval.observation": {
        "create": "crud",
    },
    "approval.metrics": {
        "_query": "report",
        "_read_group": "report",
        "search_read": "report",
        "search_fetch": "report",
    },
    "approver.performance": {
        "_query": "report",
        "_read_group": "report",
        "search_read": "report",
        "search_fetch": "report",
    },
    "wizard.approval.request.decide": {
        "action_confirm_refuse": "wizard",
        "action_confirm_change": "wizard",
    },
    "wizard.approval.approver.delegate": {
        "action_confirm": "wizard",
        "_compute_preview": "wizard",
    },
    "approval.dashboard": {
        "action_refresh": "report",
        "action_view_slowest_category": "report",
        "action_view_slowest_approver": "report",
        "action_view_overloaded_approver": "report",
        "action_view_to_review": "report",
        "_compute_today_stats": "report",
        "_compute_trends": "report",
        "_compute_bottlenecks": "report",
        "_compute_all_time_stats": "report",
        "_compute_user_metrics": "report",
        "_compute_velocity_metrics": "report",
        "_get_avg_response_time_sql": "report",
        "_get_avg_response_time_today_sql": "report",
    },
    "ir.attachment": {
        "_approval_terminal_parent_ids": "attachment",
        "_unlink_approved_approval_request": "attachment",
    },
    "mail.activity": {
        "_get_answering_approvers": "activity",
        "_compute_approval_request_id": "compute",
    },
    "res.users": {
        "_is_approval_manager": "access",
        "_approval_handover_on_archive": "crud",
    },
}


def _traced(
    target: Target, event: str, origin: Callable[..., Any], on_vals: bool = False
) -> Callable[..., Any]:
    @wraps(origin)
    def traced(self, *args: Any, **kwargs: Any) -> Any:
        if not (target.on() or accounting()):
            return origin(self, *args, **kwargs)
        size = len(args[0]) if on_vals and args else len(self)
        cursor = self.env.cr
        before = getattr(cursor, "sql_log_count", 0)
        with target.span(event, n=size, uid=self.env.uid) as span:
            try:
                return origin(self, *args, **kwargs)
            finally:
                span["sql"] = getattr(cursor, "sql_log_count", 0) - before

    setattr(traced, TRACE_ORIGIN, origin)
    return traced


def instrument(model: models.BaseModel) -> None:
    traced = CALL_TRACES.get(model._name)
    if not traced:
        return
    model_class = type(model)
    wrapped = []
    for method_name, target_name in traced.items():
        origin = getattr(model_class, method_name, None)
        if origin is None or getattr(origin, TRACE_ORIGIN, None) is not None:
            continue
        target = _BY_NAME[target_name]
        event = f"{model._name}.{method_name}"
        setattr(
            model_class,
            method_name,
            _traced(target, event, origin, on_vals=method_name == "create"),
        )
        wrapped.append(method_name)
    if wrapped:
        REGISTRY.event("instrumented", model=model._name, methods=len(wrapped))
    missing = [name for name in traced if not hasattr(model_class, name)]
    if missing:
        REGISTRY.note("stale_call_traces", model=model._name, methods=missing)


def uninstrument(model: models.BaseModel) -> None:
    if model._name not in CALL_TRACES:
        return
    model_class = type(model)
    for method_name in CALL_TRACES[model._name]:
        current = getattr(model_class, method_name, None)
        origin = getattr(current, TRACE_ORIGIN, None)
        if origin is None:
            continue
        if method_name in vars(model_class):
            delattr(model_class, method_name)
        if getattr(model_class, method_name, None) is not origin:
            setattr(model_class, method_name, origin)
