from __future__ import annotations

import typing
from collections import defaultdict

from odoo.libs.debug_log import DebugLog

if typing.TYPE_CHECKING:
    from collections.abc import (
        Callable,
        Collection,
        Iterable,
        Iterator,
        MutableMapping,
    )

    from ..components.core import OrmCore
    from ..fields import Field
    from ..primitives import NewId

_debug = DebugLog(__name__)

_MISSING = object()


class _OriginRead(typing.NamedTuple):
    field: Field[typing.Any]
    new_id: NewId
    value: object
    key: object


def _slots(
    core: OrmCore[Field[typing.Any]], field: Field[typing.Any]
) -> Iterator[MutableMapping[typing.Any, typing.Any]]:
    if (slot := core.get_field_data_or_none(field)) is not None:
        yield slot
    for _key, context_slot in core.iter_context_caches(field):
        yield context_slot


class OriginReads:
    __slots__ = ("_by_model", "_deferred", "telling")

    def __init__(self) -> None:
        self._by_model: dict[str, dict[int, list[_OriginRead]]] = {}
        self._deferred: list[tuple[str, list[int], Collection[str]]] = []
        self.telling = 0

    def __bool__(self) -> bool:
        return bool(self._by_model)

    def note(
        self,
        field: Field[typing.Any],
        slot: MutableMapping[typing.Any, typing.Any],
        new_id: NewId,
        key: object,
    ) -> None:
        origin = new_id.origin
        value = slot.get(new_id, _MISSING)
        if origin is None or value is _MISSING:
            return
        by_origin = self._by_model.setdefault(field.model_name, {})
        by_origin.setdefault(origin, []).append(_OriginRead(field, new_id, value, key))

    def forget_assigned(
        self,
        model_name: str,
        new_ids: Iterable[NewId],
        fnames: Collection[str],
        key_of: Callable[[Field[typing.Any]], object],
    ) -> None:
        by_origin = self._by_model.get(model_name)
        if not by_origin or self.telling:
            return
        for new_id in new_ids:
            reads = by_origin.get(new_id.origin) if new_id.origin else None
            if not reads:
                continue
            kept = [
                read
                for read in reads
                if read.new_id != new_id
                or read.field.name not in fnames
                or read.key != key_of(read.field)
            ]
            self._store(model_name, new_id.origin, kept)

    def evict(
        self,
        core: OrmCore[Field[typing.Any]],
        model_name: str,
        ids: Iterable[int] | None,
        fnames: Collection[str],
    ) -> dict[Field[typing.Any], list[NewId]]:
        by_origin = self._by_model.get(model_name)
        if not by_origin:
            return {}
        evicted: dict[Field[typing.Any], list[NewId]] = defaultdict(list)
        for origin in list(by_origin) if ids is None else ids:
            reads = by_origin.get(origin)
            if not reads:
                continue
            kept = []
            for read in reads:
                if read.field.name not in fnames:
                    kept.append(read)
                    continue
                for slot in _slots(core, read.field):
                    if slot.get(read.new_id, _MISSING) is read.value:
                        del slot[read.new_id]
                        evicted[read.field].append(read.new_id)
            self._store(model_name, origin, kept)
        if evicted:
            _debug.logic(
                "origin_reads.evicted",
                model=model_name,
                fields=len(evicted),
                drafts=sum(len(new_ids) for new_ids in evicted.values()),
            )
        return evicted

    def _store(
        self, model_name: str, origin: int | None, reads: list[_OriginRead]
    ) -> None:
        by_origin = self._by_model[model_name]
        if reads:
            by_origin[typing.cast("int", origin)] = reads
            return
        by_origin.pop(typing.cast("int", origin), None)
        if not by_origin:
            del self._by_model[model_name]

    def defer(self, changes: Iterable[tuple[str, list[int], Collection[str]]]) -> None:
        self._deferred.extend(changes)

    def take_deferred(self) -> list[tuple[str, list[int], Collection[str]]]:
        deferred, self._deferred = self._deferred, []
        return deferred

    def clear(self) -> None:
        self._by_model.clear()
        self._deferred.clear()
