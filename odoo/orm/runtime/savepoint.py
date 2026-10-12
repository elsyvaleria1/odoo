from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, override

from odoo.db.cursor import BaseCursor
from odoo.db.savepoint import Savepoint, _FlushingSavepoint
from odoo.libs.debug_log import DebugLog
from odoo.libs.func import reset_cached_properties

_debug = DebugLog(__name__)


class CacheInvalidating(Protocol):
    @property
    def cache_invalidation_generation(self) -> dict[str, int]: ...

    def clear_cache(self, *names: str) -> None: ...


def _cache_generation(cr: BaseCursor) -> dict[str, int]:
    txn = cr.transaction
    return {} if txn is None else dict(txn.registry.cache_invalidation_generation)


def _clear_invalidated_caches(
    registry: CacheInvalidating, before: dict[str, int]
) -> None:
    invalidated = tuple(
        name
        for name, generation in registry.cache_invalidation_generation.items()
        if generation != before.get(name, 0)
    )
    if invalidated:
        _debug.logic("savepoint.caches_cleared", groups=invalidated)
        registry.clear_cache(*invalidated)


class _OrmSavepoint(Savepoint):
    __slots__ = ("_generation_before",)

    if TYPE_CHECKING:
        _cr: BaseCursor

    def __init__(self, cr: BaseCursor) -> None:
        self._generation_before = _cache_generation(cr)
        super().__init__(cr)

    @override
    def rollback(self) -> None:
        super().rollback()
        txn = self._cr.transaction
        if txn is not None:
            txn.core.note_rows_vanished()
            _clear_invalidated_caches(txn.registry, self._generation_before)


class _OrmFlushingSavepoint(_FlushingSavepoint):
    __slots__ = ("_generation_before",)

    _restores_orm_state = True

    @override
    def _save_orm_state(self, cr: BaseCursor) -> None:
        self._generation_before = _cache_generation(cr)

    @override
    def _restore_orm_state(self, cr: BaseCursor) -> None:
        txn = cr.transaction
        if txn is None:
            return
        txn.core.note_rows_vanished()
        self._clear_invalidated_caches(txn.registry, self._generation_before)
        current = type(txn.registry).registries.get(txn.registry.db_name)
        _debug.logic(
            "savepoint.restore_orm_state",
            db=txn.registry.db_name,
            registry_replaced=current is not None and current is not txn.registry,
            envs=len(txn.envs),
        )
        if current is not None and current is not txn.registry:
            txn.reset()
        else:
            txn.clear()
            for env in txn.envs:
                reset_cached_properties(env)

    _clear_invalidated_caches = staticmethod(_clear_invalidated_caches)


BaseCursor._savepoint_cls = _OrmSavepoint
BaseCursor._flushing_savepoint_cls = _OrmFlushingSavepoint
