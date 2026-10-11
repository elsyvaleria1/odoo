from __future__ import annotations

import os
import statistics
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from odoo.db.cursor import Cursor


class StatementCounter:

    def __init__(self) -> None:
        self.count = 0
        self.chars = 0
        self.sql_wait = 0.0
        self._time_start = getattr(threading.current_thread(), "query_time", 0.0)
        self._schedstat: int | None = None
        self._wait_mark: float | None = None
        self._probe_seconds = 0.0

    def _thread_wait(self) -> float:
        start = time.perf_counter()
        wait = int(os.pread(self._schedstat, 64, 0).split()[1]) / 1e9
        self._probe_seconds += time.perf_counter() - start
        return wait

    def _mark_statement(self) -> None:
        self._wait_mark = self._thread_wait()

    def _record(self, cursor, query, params, start, delay):
        self.count += 1
        self.chars += len(query) if isinstance(query, (str, bytes)) else len(str(query))
        if self._wait_mark is not None:
            self.sql_wait += self._thread_wait() - self._wait_mark
            self._wait_mark = None

    @property
    def seconds(self):
        return (
            threading.current_thread().query_time
            - self._time_start
            + self._probe_seconds
        )

    @contextmanager
    def on(self):
        thread = threading.current_thread()
        owns_time = not hasattr(thread, "query_count")
        if owns_time:
            thread.query_count = 0
            thread.query_time = 0.0
        existing = getattr(thread, "query_hooks", None)
        hooks = existing if existing is not None else []
        thread.query_hooks = hooks
        hooks.append(self._record)
        before_statement = Cursor.__dict__.get("_before_statement", _MISSING)
        try:
            self._schedstat = os.open(_SCHEDSTAT, os.O_RDONLY)
        except OSError:
            self._schedstat = None
        else:
            inherited = Cursor._before_statement

            def marked(cursor):
                self._mark_statement()
                inherited(cursor)

            Cursor._before_statement = marked
        try:
            yield self
        finally:
            if self._schedstat is not None:
                if before_statement is _MISSING:
                    del Cursor._before_statement
                else:
                    Cursor._before_statement = before_statement
                os.close(self._schedstat)
                self._schedstat = None
            hooks.remove(self._record)
            if existing is None and not hooks:
                del thread.query_hooks
            if owns_time:
                del thread.query_count
                del thread.query_time

    def reset(self) -> None:
        self.count = 0
        self.chars = 0
        self.sql_wait = 0.0
        self._probe_seconds = 0.0
        self._wait_mark = None
        self._time_start = threading.current_thread().query_time


class ServerClock:
    def __init__(self) -> None:
        self.seconds = 0.0
        self._depth = 0
        self._restore: list[tuple[type, str, object]] = []

    def __call__(self) -> float:
        return self.seconds

    def wrap(self, cls: type, *names: str) -> None:
        for name in names:
            original = getattr(cls, name)
            self._restore.append((cls, name, cls.__dict__.get(name, _MISSING)))
            setattr(cls, name, self._get_timed(original))

    def _get_timed(self, original):
        def timed(record, *args, **kwargs):
            if self._depth:
                return original(record, *args, **kwargs)
            self._depth += 1
            start = time.perf_counter()
            try:
                return original(record, *args, **kwargs)
            finally:
                self.seconds += time.perf_counter() - start
                self._depth -= 1

        return timed

    def unwrap(self) -> None:
        for cls, name, previous in reversed(self._restore):
            if previous is _MISSING:
                delattr(cls, name)
            else:
                setattr(cls, name, previous)
        self._restore.clear()


_MISSING = object()


_SCHEDSTAT = Path("/proc/thread-self/schedstat")
CLEAN_WAIT_SHARE = 0.05


def run_delay() -> float:
    try:
        return int(_SCHEDSTAT.read_text(encoding="ascii").split()[1]) / 1e9
    except OSError:
        return 0.0


def measure(
    fn: Callable[[], object],
    counter: StatementCounter,
    *,
    repeat: int,
    rounds: int = 5,
    clock: Callable[[], float] | None = None,
    waited: Callable[[], float] = run_delay,
) -> dict[str, float]:
    if repeat < 1 or rounds < 1:
        raise ValueError("repeat and rounds must be positive")
    clock = clock or time.perf_counter
    fn()
    fn()
    samples = []
    clean = []
    statements = []
    chars = []
    for _ in range(rounds):
        counter.reset()
        wait_start = waited()
        start = clock()
        cpu_start = time.thread_time()
        for _ in range(repeat):
            before, chars_before = counter.count, counter.chars
            fn()
            statements.append(counter.count - before)
            chars.append(counter.chars - chars_before)
        wall = clock() - start
        cpu = time.thread_time() - cpu_start
        samples.append(
            {
                "wall_ms": wall / repeat * 1000,
                "cpu_ms": cpu / repeat * 1000,
                "sql_ms": counter.seconds / repeat * 1000,
                "non_sql_ms": (wall - counter.seconds) / repeat * 1000,
            }
        )
        outside_sql = waited() - wait_start - getattr(counter, "sql_wait", 0.0)
        if outside_sql <= CLEAN_WAIT_SHARE * (wall - counter.seconds):
            clean.append(samples[-1])
    read = clean or samples
    return {
        **{key: round(min(row[key] for row in read), 3) for key in samples[0]},
        "rounds": rounds,
        "rounds_contended": rounds - len(clean),
        "non_sql_ms_median": round(
            statistics.median(row["non_sql_ms"] for row in samples), 3
        ),
        "statements": statistics.median(statements),
        "statements_min": min(statements),
        "statements_max": max(statements),
        "sql_chars": statistics.median(chars),
    }


class _Rec:
    __slots__ = ("key", "parent", "value")

    def __init__(self, key: str, value: int, parent: _Rec | None) -> None:
        self.key = key
        self.value = value
        self.parent = parent


def _calibration_workload() -> int:
    index: dict[str, list[_Rec]] = {}
    parent = None
    for i in range(60000):
        rec = _Rec(f"k{i % 997}", i, parent)
        index.setdefault(rec.key, []).append(rec)
        parent = rec if i % 7 else None
    total = 0
    for recs in index.values():
        for rec in recs:
            total += rec.value + (rec.parent.value if rec.parent else 0)
    return total + len(sorted(index, key=lambda key: (len(index[key]), key)))


def calibration_ms(runs: int = 15) -> float:
    best = float("inf")
    for _ in range(runs):
        start = time.perf_counter()
        _calibration_workload()
        best = min(best, time.perf_counter() - start)
    return round(best * 1000, 3)
