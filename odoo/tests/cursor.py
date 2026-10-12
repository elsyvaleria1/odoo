import contextlib
import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import psycopg

import odoo
from odoo.db import BaseCursor, Cursor, Savepoint
from odoo.libs.debug_log import DebugLog

if TYPE_CHECKING:
    from .common import BaseCase

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


def cannot_release(thread: threading.Thread | None) -> bool:
    return (
        thread is None
        or not thread.is_alive()
        or getattr(thread, "type", None) == "http_idle"
    )


def thread_by_ident(ident: int | None) -> threading.Thread | None:
    if ident is None:
        return None
    return next((t for t in threading.enumerate() if t.ident == ident), None)


def _release_foreign_acquisition(lock: Any) -> None:
    if hasattr(lock, "_owner"):
        me = threading.get_ident()
        owner = lock._owner
        if owner is None:
            _debug.logic("test.lock.stranded_release_skipped", reason="free")
            _logger.warning(
                "The lock of a stranded test cursor was already free; releasing nothing"
            )
            return
        foreign = owner != me
        if foreign:
            holder = thread_by_ident(owner)
            if holder is not None and not cannot_release(holder):
                _debug.logic("test.lock.adoption_refused", holder=holder.name)
                _logger.error(
                    "Refusing to take the registry test lock from %s, which is "
                    "still running and will release it itself",
                    holder.name,
                )
                return
            lock._owner = me
        lock.release()
        _debug.logic("test.lock.stranded_released", adopted=foreign)
        return
    try:
        lock.release()
    except RuntimeError:
        _debug.logic("test.lock.stranded_release_failed")
        _logger.warning(
            "Could not release the lock of a stranded test cursor: another "
            "thread holds it and this lock exposes no owner to adopt, so every "
            "later test cursor will stall for test_cursor_lock_timeout",
        )


def _held_here(lock: Any) -> bool:
    return bool(lock._is_owned())


class TestCursor(BaseCursor):
    __test__ = False

    _cursors_stack: list[TestCursor] = []
    _revoked_by: str | None = None
    _connection_guard = threading.RLock()

    @classmethod
    def release_stranded(cls, owner: str = "") -> int:
        stranded = cls._cursors_stack
        if stranded:
            _debug.lifecycle(
                "test.cursor.stranded", owner=owner or None, count=len(stranded)
            )
        for cursor in reversed(stranded):
            if cursor.in_use_elsewhere:
                cursor.report_in_use(owner)
                continue
            cursor.abandon(owner)
        cls._cursors_stack = []
        return len(stranded)

    @classmethod
    def release_stranded_by(cls, ident: int, owner: str = "") -> int:
        mine = [
            cursor
            for cursor in cls._cursors_stack
            if cursor._thread.ident == ident and not cursor.in_use_elsewhere
        ]
        for cursor in reversed(mine):
            cursor.abandon(owner)
            cls._cursors_stack.remove(cursor)
        _debug.lifecycle(
            "test.cursor.stranded_by", owner=owner or None, count=len(mine)
        )
        return len(mine)

    @classmethod
    def revoke_held_by(
        cls, ident: int, lock: Any, reason: str, timeout: float
    ) -> int | None:
        if not cls._connection_guard.acquire(timeout=timeout):
            _debug.logic("test.cursor.revoke_refused", reason="statement_in_flight")
            return None
        try:
            held = [
                cursor for cursor in cls._cursors_stack if cursor._thread.ident == ident
            ]
            for cursor in reversed(held):
                cursor._revoke(reason)
                cls._cursors_stack.remove(cursor)
            if lock.owner_ident == ident:
                lock._owner = threading.get_ident()
                while lock.held_by_this_thread:
                    lock.release()
            _debug.lifecycle("test.cursor.revoked", count=len(held))
            return len(held)
        finally:
            cls._connection_guard.release()

    @classmethod
    def holder_of(cls, ident: int | None) -> threading.Thread | None:
        for cursor in cls._cursors_stack:
            if cursor._thread.ident == ident:
                return cursor._thread
        return thread_by_ident(ident)

    @property
    def in_use_elsewhere(self) -> bool:
        return self._thread is not threading.current_thread() and not cannot_release(
            self._thread
        )

    def report_in_use(self, owner: str = "") -> None:
        _debug.logic(
            "test.cursor.stranded_in_use",
            owner=owner or None,
            thread=self._thread.name,
        )
        _logger.error(
            "A cursor remaining in the TestCursor stack at the end of %s is "
            "still in use by %s; it is left to that thread, which releases its "
            "registry lock when it closes the cursor",
            owner or "the test",
            self._thread.name,
        )

    def abandon(self, owner: str = "") -> None:
        _logger.warning(
            "A cursor was remaining in the TestCursor stack at the end of %s; "
            "releasing its registry lock",
            owner or "the test",
        )
        try:
            self._close_savepoint(rollback=True)
        except Exception as exc:
            _debug.logic(
                "test.cursor.stranded_rollback_failed",
                owner=owner or None,
                error=type(exc).__name__,
            )
            _logger.warning(
                "Could not roll back the savepoint of the cursor stranded by %s",
                owner or "the test",
                exc_info=True,
            )
        self._closed = True
        _release_foreign_acquisition(self._lock)

    def __init__(self, cursor: Cursor, lock: threading.RLock, readonly: bool) -> None:
        if not isinstance(cursor, BaseCursor):
            raise TypeError(
                f"TestCursor wraps a BaseCursor, got {type(cursor).__name__}"
            )
        super().__init__()
        self._closed: bool = False
        self._savepoint: Savepoint | None = None
        self._thread = threading.current_thread()
        self._cursor = cursor
        self.readonly: bool = readonly
        self._lock = lock
        running = odoo.modules.module.current_test
        if isinstance(running, bool):
            raise RuntimeError(
                "TestCursor opened with no test running: odoo.modules.module."
                "current_test is not set"
            )
        current_test = cast("BaseCase", running)
        current_test.assertCanOpenTestCursor()
        lock_timeout = current_test.test_cursor_lock_timeout
        with _debug.perf(
            "test.cursor.lock_wait",
            test=current_test.canonical_tag,
            timeout=lock_timeout,
            held=getattr(lock, "count", None),
        ) as span:
            acquired = self._acquire_lock(lock_timeout)
            span.set(acquired=acquired)
        if not acquired:
            _debug.logic(
                "test.cursor.lock_timeout",
                test=current_test.canonical_tag,
                timeout=lock_timeout,
                depth=len(self._cursors_stack),
            )
            raise TimeoutError(
                f"Unable to acquire lock for test cursor after {lock_timeout}s"
            )
        with self._connection_guard:
            if not _held_here(self._lock):
                self._closed = True
                raise psycopg.InterfaceError(
                    "Test cursor revoked while it opened: its test took the "
                    "connection back"
                )
            try:
                current_test.assertCanOpenTestCursor()
                self._check_cursor_readonly()
                self._check_outer_savepoints()
            except Exception as exc:
                _debug.lifecycle(
                    "test.cursor.open_refused",
                    test=current_test.canonical_tag,
                    error=type(exc).__name__,
                )
                self._lock.release()
                raise
            self._cursors_stack.append(self)
        _debug.lifecycle(
            "test.cursor.open",
            test=current_test.canonical_tag,
            readonly=readonly,
            depth=len(self._cursors_stack),
            held=getattr(lock, "count", None),
        )

    def _acquire_lock(self, timeout: float) -> bool:
        with self._connection_guard:
            if _held_here(self._lock):
                return self._lock.acquire()
        return self._lock.acquire(timeout=timeout)

    def _revoke(self, reason: str) -> None:
        self._revoked_by = reason
        try:
            self._close_savepoint(rollback=True)
        except Exception:
            _logger.warning(
                "Could not roll back the savepoint of a revoked test cursor",
                exc_info=True,
            )
        self._release_wrapped_cursor()
        self._closed = True

    def _refuse_if_revoked(self) -> None:
        if self._revoked_by is not None:
            raise psycopg.InterfaceError(f"Test cursor revoked: {self._revoked_by}")

    def _check_cursor_readonly(self) -> None:
        if self.readonly:
            return
        if any(cursor.readonly and cursor._savepoint for cursor in self._cursors_stack):
            _debug.logic(
                "test.cursor.readonly_violation", depth=len(self._cursors_stack)
            )
            raise RuntimeError("Opening a read/write test cursor from a readonly one")

    def _check_outer_savepoints(self) -> None:
        forced = 0
        for cursor in self._cursors_stack:
            if not cursor.readonly:
                if not cursor._savepoint:
                    forced += 1
                cursor._check_savepoint()
        if _debug.logic.enabled and forced:
            _debug.logic(
                "test.cursor.outer_savepoints_forced",
                forced=forced,
                depth=len(self._cursors_stack),
            )

    def _check_savepoint(self) -> None:
        if not self._savepoint:
            self._savepoint = Savepoint(self._cursor._obj)
            if self.readonly:
                self._cursor._obj.execute("SET TRANSACTION READ ONLY")
            _debug.lifecycle("test.cursor.savepoint_opened", readonly=self.readonly)

    def _close_savepoint(self, *, rollback: bool) -> None:
        if not self._savepoint:
            return
        self._savepoint.close(rollback=rollback)
        self._savepoint = None
        _debug.lifecycle("test.cursor.savepoint_closed", rollback=rollback)
        if rollback:
            self._cursor._on_rollback_to_savepoint()

    def _savepoint_opened(self) -> None:
        self._cursor._savepoint_opened()
        super()._savepoint_opened()

    def _savepoint_closed(self) -> None:
        super()._savepoint_closed()
        self._cursor._savepoint_closed()

    def _statement(
        self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        with self._connection_guard:
            self._refuse_if_revoked()
            if self._closed:
                raise psycopg.InterfaceError("Cursor already closed")
            self._check_savepoint()
            _debug.perf.count(
                "test.cursor.statement", kind=name, readonly=self.readonly
            )
            return getattr(self._cursor, name)(*args, **kwargs)

    def execute(self, *args: Any, **kwargs: Any) -> None:
        self._statement("execute", args, kwargs)

    def executemany(self, *args: Any, **kwargs: Any) -> None:
        self._statement("executemany", args, kwargs)

    def execute_values(self, *args: Any, **kwargs: Any) -> Any:
        return self._statement("execute_values", args, kwargs)

    def copy_from(self, *args: Any, **kwargs: Any) -> Any:
        return self._statement("copy_from", args, kwargs)

    def copy(self, *args: Any, **kwargs: Any) -> Any:
        return self._statement("copy", args, kwargs)

    def close(self) -> None:
        with self._connection_guard:
            if self._closed:
                _debug.logic("test.cursor.close_again")
                return
            try:
                self.rollback()
                self._release_wrapped_cursor()
            finally:
                self._closed = True

                in_order = bool(self._cursors_stack and self._cursors_stack[-1] is self)
                if in_order:
                    self._cursors_stack.pop()
                else:
                    _debug.logic(
                        "test.cursor.close_out_of_order",
                        depth=len(self._cursors_stack),
                        on_stack=self in self._cursors_stack,
                    )
                    _logger.warning(
                        "Out-of-order close: %s is not the top of the cursor stack",
                        self,
                    )
                    with contextlib.suppress(ValueError):
                        self._cursors_stack.remove(self)
                self._lock.release()
                _debug.lifecycle(
                    "test.cursor.close",
                    readonly=self.readonly,
                    in_order=in_order,
                    depth=len(self._cursors_stack),
                    commits=self.commit_count,
                    held=getattr(self._lock, "count", None),
                )

    def _release_wrapped_cursor(self) -> None:
        if leaked := self._savepoint_depth:
            _logger.warning("%d savepoint(s) left open on a closed test cursor", leaked)
            self._cursor._savepoint_depth -= leaked
            self._savepoint_depth = 0
        if getattr(self._cursor, "_statement_timeout", None) is not None:
            self._cursor.set_statement_timeout(None)

    def commit(self) -> None:
        with self._connection_guard:
            self._refuse_if_revoked()
            self.flush()
            self._close_savepoint(rollback=self.readonly)
            self.commit_count += 1
            self.clear()
            self._now = None
            self.prerollback.clear()
            self.postrollback.clear()
            self.postcommit.clear()
        _debug.lifecycle(
            "test.cursor.commit", readonly=self.readonly, commits=self.commit_count
        )

    def rollback(self) -> None:
        with self._connection_guard:
            if self._revoked_by is not None:
                return
            had_savepoint = self._savepoint is not None
            self.clear()
            self._now = None
            self.postcommit.clear()
            self.prerollback.run()
            self._close_savepoint(rollback=True)
            self.postrollback.drain()
        _debug.lifecycle(
            "test.cursor.rollback", readonly=self.readonly, had_savepoint=had_savepoint
        )

    @property
    def closed(self) -> bool:
        return self._closed or self._cursor.closed

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    def _results(self) -> Cursor:
        self._refuse_if_revoked()
        return self._cursor

    def fetchone(self) -> tuple[Any, ...] | None:
        with self._connection_guard:
            return self._results().fetchone()

    def fetchmany(self, size: int = 0) -> list[tuple[Any, ...]]:
        with self._connection_guard:
            return self._results().fetchmany(size)

    def fetchall(self) -> list[tuple[Any, ...]]:
        with self._connection_guard:
            return self._results().fetchall()

    def dictfetchone(self) -> dict[str, Any] | None:
        with self._connection_guard:
            return self._results().dictfetchone()

    def dictfetchmany(self, size: int) -> list[dict[str, Any]]:
        with self._connection_guard:
            return self._results().dictfetchmany(size)

    def dictfetchall(self) -> list[dict[str, Any]]:
        with self._connection_guard:
            return self._results().dictfetchall()

    def now(self) -> datetime:
        if self._now is None:
            self._now = datetime.now(UTC).replace(tzinfo=None)
        return self._now
