from __future__ import annotations

import contextlib
import copy
import enum
import logging
import math
import threading
from time import monotonic
from typing import TYPE_CHECKING, Any

import psycopg

if TYPE_CHECKING:
    from collections.abc import Collection

    from .stats import PoolStats

from odoo.libs.debug_log import DebugLog

from .dsn import (
    _NON_RETRYABLE_CONNECT_ERRORS,
    DsnKey,
    _expand_conninfo,
    _get_key_dbname,
    _resolve_connect_error,
)

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

PROBE_CONNECT_TIMEOUT = 5


class ConnectionProbeOutcome(enum.Enum):
    CONNECTED = "connected"
    TRANSIENT_FAILURE = "transient_failure"
    UNKNOWN = "unknown"


class DatabaseProbeOutcome(enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    AUTH_FAILED = "auth_failed"
    UNKNOWN = "unknown"


def get_libpq_connect_timeout(deadline: float | None, cap: int) -> int:
    if deadline is None:
        return cap
    remaining = deadline - monotonic()
    if remaining <= 0:
        return 0
    return min(cap, math.ceil(remaining))


class _InFlightProbe:
    __slots__ = ("done", "exc", "outcome")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.exc: BaseException | None = None
        self.outcome = ConnectionProbeOutcome.UNKNOWN


class ReachabilityProbe:
    def __init__(self, stats: PoolStats) -> None:
        self._lock = threading.Lock()
        self._proven: set[DsnKey] = set()
        self._inflight: dict[DsnKey, _InFlightProbe] = {}
        self._stats = stats

    def is_proven(self, key: DsnKey) -> bool:
        with self._lock:
            return key in self._proven

    def mark_proven(self, key: DsnKey) -> None:
        if key in self._proven:
            return
        with self._lock:
            if _debug.lifecycle.enabled and key not in self._proven:
                _debug.lifecycle(
                    "pool.reachability_proven",
                    db=_get_key_dbname(key),
                    proven=len(self._proven) + 1,
                )
            self._proven.add(key)

    def clear_key(self, key: DsnKey) -> None:
        with self._lock:
            if _debug.lifecycle.enabled and key in self._proven:
                _debug.lifecycle("pool.reachability_revoked", db=_get_key_dbname(key))
            self._proven.discard(key)

    def clear_keys(self, keys: Collection[DsnKey]) -> None:
        with self._lock:
            _debug.lifecycle("pool.reachability_revoked", count=len(keys))
            self._proven.difference_update(keys)

    def clear(self) -> None:
        with self._lock:
            _debug.lifecycle("pool.reachability_revoked", count=len(self._proven))
            self._proven.clear()

    def clear_database(self, db_name: str) -> None:
        with self._lock:
            revoked = [key for key in self._proven if _get_key_dbname(key) == db_name]
            _debug.lifecycle(
                "pool.reachability_revoked", db=db_name, count=len(revoked)
            )
            self._proven.difference_update(revoked)

    def probe_connection_if_unproven(
        self,
        key: DsnKey,
        conninfo: str,
        kwargs: dict[str, Any],
        deadline: float | None = None,
    ) -> ConnectionProbeOutcome:
        with self._lock:
            if key in self._proven:
                proven = True
                probe = None
                leader = False
            else:
                proven = False
                probe = self._inflight.get(key)
                leader = probe is None
                if leader:
                    probe = self._inflight[key] = _InFlightProbe()
        if proven:
            self._stats.record_probe_outcome("skipped_proven")
            _debug.logic("pool.probe.skipped_proven", db=_get_key_dbname(key))
            return ConnectionProbeOutcome.CONNECTED
        assert probe is not None
        _debug.logic(
            "pool.probe",
            db=_get_key_dbname(key),
            leader=leader,
            deadline_s=None if deadline is None else max(0.0, deadline - monotonic()),
        )
        return self._probe_or_await_leader(
            key, probe, leader, conninfo, kwargs, deadline
        )

    def _probe_or_await_leader(
        self,
        key: DsnKey,
        probe: _InFlightProbe,
        leader: bool,
        conninfo: str,
        kwargs: dict[str, Any],
        deadline: float | None = None,
    ) -> ConnectionProbeOutcome:
        if leader:
            try:
                probe.outcome = self.probe_connection(conninfo, kwargs, deadline)
            except BaseException as e:
                probe.exc = e
                raise
            finally:
                with self._lock:
                    del self._inflight[key]
                    probe.done.set()
                _debug.pipeline(
                    "pool.probe.leader_done",
                    db=_get_key_dbname(key),
                    failed=probe.exc is not None,
                    connected=probe.outcome is ConnectionProbeOutcome.CONNECTED,
                    outcome=probe.outcome.value,
                )
            return probe.outcome
        else:
            wait_timeout = (
                None if deadline is None else max(0.0, deadline - monotonic())
            )
            done = probe.done.wait(wait_timeout)
            _debug.logic(
                "pool.probe.awaited",
                db=_get_key_dbname(key),
                done=done,
                failed=probe.exc is not None,
            )
            if done and probe.exc is not None:
                raise copy.copy(probe.exc) from probe.exc
            return probe.outcome if done else ConnectionProbeOutcome.UNKNOWN

    def probe_connection(
        self, conninfo: str, kwargs: dict[str, Any], deadline: float | None = None
    ) -> ConnectionProbeOutcome:
        probe_timeout = get_libpq_connect_timeout(deadline, PROBE_CONNECT_TIMEOUT)
        if not probe_timeout:
            _debug.logic("pool.probe.skipped_deadline", db=kwargs.get("dbname"))
            return ConnectionProbeOutcome.UNKNOWN
        self._stats.record_probe_started()
        probe_kwargs = {**kwargs, "autocommit": True}
        probe_kwargs["connect_timeout"] = probe_timeout
        try:
            with _debug.perf("pool.probe.connect", timeout=probe_timeout):
                conn = psycopg.connect(conninfo, **probe_kwargs)
        except _NON_RETRYABLE_CONNECT_ERRORS as e:
            self._stats.record_probe_outcome("permanent")
            _debug.logic(
                "pool.probe.permanent", reason="sqlstate", error=type(e).__name__
            )
            raise
        except psycopg.OperationalError as e:
            self._check_for_permanent_connect_error(e, conninfo, kwargs, deadline)
            self._record_transient_connect_error(e)
            return ConnectionProbeOutcome.TRANSIENT_FAILURE
        _debug.lifecycle(
            "pool.probe.ok",
            db=kwargs.get("dbname"),
            backend_pid=getattr(getattr(conn, "info", None), "backend_pid", None),
        )
        with contextlib.suppress(Exception):
            conn.close()
        return ConnectionProbeOutcome.CONNECTED

    def _check_for_permanent_connect_error(
        self,
        error: psycopg.OperationalError,
        conninfo: str,
        kwargs: dict[str, Any],
        deadline: float | None,
    ) -> None:
        translated = _resolve_connect_error(error)
        if translated is not None:
            self._stats.record_probe_outcome("permanent")
            _debug.logic(
                "pool.probe.permanent",
                reason="message",
                error=type(translated).__name__,
            )
            raise translated from error
        maintenance = self.probe_database_presence(conninfo, kwargs, deadline)
        if maintenance is DatabaseProbeOutcome.ABSENT:
            self._stats.record_probe_outcome("permanent")
            _debug.logic("pool.probe.permanent", reason="database_absent")
            raise psycopg.errors.InvalidCatalogName(str(error)) from error
        if _is_authentication_failure(error, maintenance):
            self._stats.record_probe_outcome("permanent")
            _debug.logic("pool.probe.permanent", reason="auth_phase")
            raise psycopg.errors.InvalidAuthorizationSpecification(
                str(error)
            ) from error

    def _record_transient_connect_error(self, error: Exception) -> None:
        self._stats.record_probe_outcome("transient")
        _debug.logic("pool.probe.transient", error=type(error).__name__)
        _logger.debug(
            "Pool pre-flight probe failed (treating as transient)",
            exc_info=error,
        )

    def probe_database_presence(
        self, conninfo: str, kwargs: dict[str, Any], deadline: float | None = None
    ) -> DatabaseProbeOutcome:
        maint = _expand_conninfo({"dsn": conninfo, **kwargs})
        db_name = maint.get("dbname")
        if not db_name or db_name == "postgres":
            _debug.logic(
                "pool.probe.absence_check_skipped",
                db=db_name,
                reason="maintenance_db" if db_name else "no_db_name",
            )
            return DatabaseProbeOutcome.UNKNOWN
        maint.pop("options", None)
        maint["dbname"] = "postgres"
        maint["autocommit"] = True
        probe_timeout = get_libpq_connect_timeout(deadline, PROBE_CONNECT_TIMEOUT)
        if not probe_timeout:
            _debug.logic(
                "pool.probe.absence_check_skipped", db=db_name, reason="deadline"
            )
            return DatabaseProbeOutcome.UNKNOWN
        maint["connect_timeout"] = probe_timeout
        try:
            with psycopg.connect("", **maint) as mc:
                row = mc.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
                ).fetchone()
            _debug.logic("pool.probe.database_absent", db=db_name, absent=row is None)
            return (
                DatabaseProbeOutcome.ABSENT
                if row is None
                else DatabaseProbeOutcome.PRESENT
            )
        except psycopg.OperationalError as e:
            at_auth = _is_password_stage_failure(e)
            _debug.logic(
                "pool.probe.absence_check_unavailable",
                db=db_name,
                error=type(e).__name__,
                auth_failed=at_auth,
            )
            _logger.debug(
                "pg_database existence check unavailable for %r",
                db_name,
                exc_info=True,
            )
            return (
                DatabaseProbeOutcome.AUTH_FAILED
                if at_auth
                else DatabaseProbeOutcome.UNKNOWN
            )
        except psycopg.Error as e:
            _debug.logic(
                "pool.probe.absence_check_unavailable",
                db=db_name,
                error=type(e).__name__,
            )
            _logger.debug(
                "pg_database existence check unavailable for %r",
                db_name,
                exc_info=True,
            )
            return DatabaseProbeOutcome.UNKNOWN


def _is_password_stage_failure(exc: psycopg.OperationalError) -> bool:
    pgconn = getattr(exc, "pgconn", None)
    if pgconn is None:
        return False
    try:
        return bool(pgconn.needs_password or pgconn.used_password)
    except Exception:
        return False


def _is_authentication_failure(
    exc: psycopg.OperationalError, maintenance: DatabaseProbeOutcome
) -> bool:
    pgconn = getattr(exc, "pgconn", None)
    if pgconn is None:
        return False
    try:
        if pgconn.needs_password:
            return True
        return (
            bool(pgconn.used_password)
            and maintenance is DatabaseProbeOutcome.AUTH_FAILED
        )
    except Exception:
        return False
