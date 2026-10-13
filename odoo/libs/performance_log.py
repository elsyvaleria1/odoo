
import functools
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Concatenate, Protocol, cast, overload

from odoo.libs.lazy_log import RecordLabelSource, get_lazy_record_label

__all__ = ["PerformanceLog"]


class StatementCounter(Protocol):
    @property
    def sql_statement_count(self) -> int: ...


class PerformanceEnvironment(Protocol):
    @property
    def cr(self) -> StatementCounter: ...


class PerformanceRecord(RecordLabelSource, Protocol):
    @property
    def env(self) -> PerformanceEnvironment: ...


type RecordMethod[Record: PerformanceRecord, **P, R] = Callable[
    Concatenate[Record, P], R
]


class PerformanceLog:
    def __init__(self, logger: logging.Logger, *, unit: str = "queries") -> None:
        self.logger = logger
        self._method_format = f"%s on %s: %.1f ms, %d {unit}"
        self._block_format = f"%s: %.1f ms, %d {unit}"

    @overload
    def log_method[Record: PerformanceRecord, **P, R](
        self, func: RecordMethod[Record, P, R], *, label: str | None = None
    ) -> RecordMethod[Record, P, R]: ...

    @overload
    def log_method[Record: PerformanceRecord, **P, R](
        self, func: None = None, *, label: str | None = None
    ) -> Callable[[RecordMethod[Record, P, R]], RecordMethod[Record, P, R]]: ...

    def log_method(
        self, func: Callable[..., Any] | None = None, *, label: str | None = None
    ) -> Callable[..., Any]:
        def decorate[F: Callable[..., Any]](fn: F) -> F:
            name = label or fn.__qualname__

            @functools.wraps(fn)
            def wrapper(records: PerformanceRecord, *args: Any, **kwargs: Any) -> Any:
                if not self.logger.isEnabledFor(logging.DEBUG):
                    return fn(records, *args, **kwargs)
                cr = records.env.cr
                queries = cr.sql_statement_count
                start = time.perf_counter()
                try:
                    return fn(records, *args, **kwargs)
                finally:
                    elapsed = (time.perf_counter() - start) * 1000
                    queries = cr.sql_statement_count - queries
                    if queries or elapsed >= 0.05 or records:
                        self.logger.debug(
                            self._method_format,
                            name,
                            get_lazy_record_label(records),
                            elapsed,
                            queries,
                        )

            return cast("F", wrapper)

        return decorate(func) if func is not None else decorate

    @contextmanager
    def log_duration(
        self, env: PerformanceEnvironment, label: str, *args: object
    ) -> Iterator[None]:
        if not self.logger.isEnabledFor(logging.DEBUG):
            yield
            return
        cr = env.cr
        queries = cr.sql_statement_count
        start = time.perf_counter()
        try:
            yield
        finally:
            self.logger.debug(
                self._block_format,
                label % args if args else label,
                (time.perf_counter() - start) * 1000,
                cr.sql_statement_count - queries,
            )
