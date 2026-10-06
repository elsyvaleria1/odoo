from typing import Protocol

from . import nplusone, orm_profiler
from .nplusone import NplusOneTracker
from .orm_profiler import OrmProfiler, _OrmProfile

__all__ = [
    "NplusOneTracker",
    "OrmObserver",
    "OrmProfiler",
    "_OrmProfile",
    "enabled_observers",
]


class OrmObserver(Protocol):
    def on_operation(
        self,
        operation: str,
        model_name: str,
        record_count: int,
        fields: frozenset[str],
    ) -> None: ...

    def on_operation_done(
        self,
        operation: str,
        model_name: str,
        record_count: int,
        elapsed: float,
    ) -> None: ...

    def report(self) -> None: ...

    def clear(self) -> None: ...


def enabled_observers() -> tuple[OrmObserver, ...]:
    observers: list[OrmObserver] = []
    if nplusone._n1_enabled:
        observers.append(NplusOneTracker())
    if orm_profiler._orm_profiling_enabled:
        observers.append(OrmProfiler())
    return tuple(observers)
