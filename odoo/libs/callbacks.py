from __future__ import annotations

import copy
import logging
import operator
from collections import deque
from collections.abc import (
    Callable,
    Iterable,
    Iterator,
    MutableMapping,
    MutableSequence,
    MutableSet,
)
from typing import Any, Self, SupportsIndex

from odoo.libs.debug_log import DebugLog

__all__ = [
    "CallbackData",
    "Callbacks",
    "HookMark",
    "JournaledDict",
    "JournaledList",
    "JournaledSet",
    "UndoLog",
]

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

_MISSING: Any = object()

_IMMUTABLE_TYPES = frozenset(
    {bool, int, float, complex, str, bytes, tuple, frozenset, type(None)}
)
_PLAIN_MUTABLE_TYPES = (list, dict, set, bytearray, deque)


_TRANSACTIONAL = 0
_DURABLE = 1
_STRICT = 2

type _Entry = tuple[Callable[..., object], tuple[Any, ...], int]


class HookMark:
    __slots__ = ("durable_snapshot", "full", "position", "strict")

    def __init__(self, position: int, full: bool, strict: bool) -> None:
        self.position = position
        self.full = full
        self.strict = strict
        self.durable_snapshot: dict[Any, tuple[Any, Any]] | None = None


class UndoLog:
    __slots__ = (
        "_entries",
        "_full",
        "_marks",
        "_rewinds",
        "_strict",
        "recording",
        "strict",
    )

    def __init__(self) -> None:
        self._entries: list[_Entry] = []
        self._marks: list[HookMark] = []
        self._full = 0
        self._strict = 0
        self._rewinds = 0
        self.recording = False
        self.strict = False

    @property
    def marked(self) -> bool:
        return bool(self._marks)

    @property
    def span(self) -> tuple[HookMark | None, int]:
        return (self._marks[-1] if self._marks else None, self._rewinds)

    def record(self, undo: Callable[..., object], *args: Any) -> None:
        self._entries.append((undo, args, _TRANSACTIONAL))

    def record_durable(self, undo: Callable[..., object], *args: Any) -> None:
        self._entries.append((undo, args, _DURABLE))

    def record_strict(self, undo: Callable[..., object], *args: Any) -> None:
        self._entries.append((undo, args, _STRICT))

    def mark(self, full: bool, strict: bool = False) -> HookMark:
        mark = HookMark(len(self._entries), full or strict, strict)
        self._marks.append(mark)
        if mark.full:
            self._full += 1
            self.recording = True
        if strict:
            self._strict += 1
            self.strict = True
        return mark

    def rewind(self, mark: HookMark) -> int | None:
        index = self._index(mark)
        if index is None:
            return None
        self._rewinds += 1
        self._drop_marks(index + 1)
        entries = self._entries
        undone = len(entries) - mark.position
        kept: list[_Entry] = []
        while len(entries) > mark.position:
            entry = entries.pop()
            if entry[2] == _STRICT and not mark.strict:
                kept.append(entry)
            else:
                entry[0](*entry[1])
        entries.extend(reversed(kept))
        return undone - len(kept)

    def release(self, mark: HookMark) -> bool:
        index = self._index(mark)
        if index is None:
            return False
        self._drop_marks(index)
        return True

    def _index(self, mark: HookMark) -> int | None:
        marks = self._marks
        for index in range(len(marks) - 1, -1, -1):
            if marks[index] is mark:
                return index
        return None

    def _drop_marks(self, index: int) -> None:
        marks = self._marks
        while len(marks) > index:
            dropped = marks.pop()
            self._full -= dropped.full
            self._strict -= dropped.strict
        self.strict = self._strict > 0
        if not marks:
            self._entries.clear()
            self.recording = False
        elif self.recording and not self._full:
            self.recording = False
            self._keep_durable_entries()

    def _keep_durable_entries(self) -> None:
        kept: list[_Entry] = []
        marks = self._marks
        pending = 0
        for position, entry in enumerate(self._entries):
            while pending < len(marks) and marks[pending].position <= position:
                marks[pending].position = len(kept)
                pending += 1
            if entry[2] == _DURABLE:
                kept.append(entry)
        for mark in marks[pending:]:
            mark.position = len(kept)
        self._entries = kept


def _restore_key(mapping: dict[Any, Any], key: Any, old: Any) -> None:
    if old is _MISSING:
        dict.pop(mapping, key, None)
    else:
        dict.__setitem__(mapping, key, old)


def _restore_items(mapping: dict[Any, Any], items: list[tuple[Any, Any]]) -> None:
    dict.clear(mapping)
    dict.update(mapping, items)


def _truncate_list(items: list[Any], length: int) -> None:
    list.__delitem__(items, slice(length, None))


def _restore_list(items: list[Any], snapshot: list[Any]) -> None:
    list.__setitem__(items, slice(None), snapshot)


def _delete_at(items: list[Any], index: int) -> None:
    list.__delitem__(items, index)


def _insert_run(items: list[Any], index: int, run: list[Any]) -> None:
    list.__setitem__(items, slice(index, index), run)


def _stamp_of(member: tuple[int, Any]) -> int:
    return member[0]


def _relink_member(journaled: JournaledSet, member: tuple[int, Any]) -> None:
    items = journaled._items
    if items and member[0] < next(reversed(items.values()))[0]:
        journaled._unordered = True
    items[member[1]] = member


def _relink_members(
    journaled: JournaledSet, members: dict[Any, tuple[int, Any]]
) -> None:
    items = journaled._items
    if items:
        journaled._unordered = True
    items.update(members)


def _prepend(funcs: deque[Callable[[], object]], func: Callable[[], object]) -> None:
    funcs.appendleft(func)


def _remove_func(
    funcs: deque[Callable[[], object]], func: Callable[[], object]
) -> None:
    for index in range(len(funcs) - 1, -1, -1):
        if funcs[index] is func:
            del funcs[index]
            return


class JournaledList(list[Any]):
    __slots__ = ("_log",)

    def __init__(self, log: UndoLog, items: Iterable[Any] = ()) -> None:
        super().__init__(items)
        self._log = log

    def _snapshot(self) -> None:
        if self._log.recording:
            self._log.record(_restore_list, self, list(self))

    def append(self, value: Any, /) -> None:
        if self._log.recording:
            self._log.record(_truncate_list, self, len(self))
        list.append(self, value)

    def extend(self, values: Iterable[Any], /) -> None:
        if self._log.recording:
            self._log.record(_truncate_list, self, len(self))
        list.extend(self, values)

    def __iadd__(self, values: Iterable[Any], /) -> Self:
        self.extend(values)
        return self

    def _position(self, index: SupportsIndex) -> int:
        position = operator.index(index)
        return position + len(self) if position < 0 else position

    def pop(self, index: SupportsIndex = -1, /) -> Any:
        if not self._log.recording:
            return list.pop(self, index)
        position = self._position(index)
        value = list.pop(self, index)
        self._log.record(list.insert, self, position, value)
        return value

    def __setitem__(self, index: Any, value: Any, /) -> None:
        if self._log.recording:
            if isinstance(index, slice):
                self._snapshot()
            else:
                position = operator.index(index)
                self._log.record(
                    list.__setitem__, self, position, list.__getitem__(self, position)
                )
        list.__setitem__(self, index, value)

    def __delitem__(self, index: Any, /) -> None:
        if not self._log.recording:
            list.__delitem__(self, index)
            return
        if not isinstance(index, slice):
            self.pop(index)
            return
        start, _stop, step = index.indices(len(self))
        if step != 1:
            self._snapshot()
            list.__delitem__(self, index)
            return
        run = list.__getitem__(self, index)
        list.__delitem__(self, index)
        if run:
            self._log.record(_insert_run, self, start, run)

    def __imul__(self, count: SupportsIndex, /) -> Self:
        self._snapshot()
        list.__imul__(self, count)
        return self

    def insert(self, index: SupportsIndex, value: Any, /) -> None:
        if self._log.recording:
            size = len(self)
            position = operator.index(index)
            position = max(position + size, 0) if position < 0 else min(position, size)
            self._log.record(_delete_at, self, position)
        list.insert(self, index, value)

    def remove(self, value: Any, /) -> None:
        if not self._log.recording:
            list.remove(self, value)
            return
        position = list.index(self, value)
        self._log.record(list.insert, self, position, list.__getitem__(self, position))
        list.__delitem__(self, position)

    def clear(self) -> None:
        self._snapshot()
        list.clear(self)

    def sort(self, *, key: Any = None, reverse: bool = False) -> None:
        self._snapshot()
        list.sort(self, key=key, reverse=reverse)

    def reverse(self) -> None:
        self._snapshot()
        list.reverse(self)

    def __copy__(self) -> list[Any]:
        return list(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> list[Any]:
        return [copy.deepcopy(value, memo) for value in self]


class JournaledSet(MutableSet[Any]):
    __slots__ = ("_items", "_log", "_stamp", "_unordered")

    def __init__(self, log: UndoLog, items: Iterable[Any] = ()) -> None:
        self._log = log
        self._items: dict[Any, tuple[int, Any]] = {}
        self._stamp = 0
        self._unordered = False
        for value in items:
            if value not in self._items:
                self._link(value)

    @classmethod
    def _from_iterable(cls, it: Iterable[Any]) -> set[Any]:
        return set(it)

    def _link(self, value: Any) -> None:
        self._items[value] = (self._stamp, value)
        self._stamp += 1

    def _ordered(self) -> dict[Any, tuple[int, Any]]:
        items = self._items
        if self._unordered:
            members = sorted(items.values(), key=_stamp_of)
            items.clear()
            items.update((member[1], member) for member in members)
            self._unordered = False
        return items

    def __contains__(self, value: object) -> bool:
        return value in self._items

    def __iter__(self) -> Iterator[Any]:
        return iter(self._ordered())

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self._ordered())!r})"

    def add(self, value: Any) -> None:
        if value in self._items:
            return
        if self._log.recording:
            self._log.record(dict.pop, self._items, value, None)
        self._link(value)

    def update(self, *iterables: Iterable[Any]) -> None:
        for iterable in iterables:
            for value in iterable:
                self.add(value)

    def discard(self, value: Any) -> None:
        member = self._items.pop(value, None)
        if member is not None and self._log.recording:
            self._log.record(_relink_member, self, member)

    def difference_update(self, *iterables: Iterable[Any]) -> None:
        for iterable in iterables:
            for value in iterable:
                self.discard(value)

    def pop(self) -> Any:
        items = self._ordered()
        if not items:
            raise KeyError("pop from an empty set")
        member = items.pop(next(iter(items)))
        if self._log.recording:
            self._log.record(_relink_member, self, member)
        return member[1]

    def clear(self) -> None:
        if self._items:
            if self._log.recording:
                self._log.record(_relink_members, self, dict(self._ordered()))
            self._items.clear()

    def __copy__(self) -> set[Any]:
        return set(self._items)

    def __deepcopy__(self, memo: dict[int, Any]) -> set[Any]:
        return {copy.deepcopy(value, memo) for value in self._ordered()}


class JournaledDict(dict[Any, Any]):
    __slots__ = ("_log", "_snapshot_span")

    def __init__(self, log: UndoLog) -> None:
        super().__init__()
        self._log = log
        self._snapshot_span: tuple[HookMark | None, int] | None = None

    def _store(self, key: Any, value: Any) -> None:
        if self._log.recording:
            self._log.record(_restore_key, self, key, dict.get(self, key, _MISSING))
        dict.__setitem__(self, key, value)

    def __setitem__(self, key: Any, value: Any, /) -> None:
        self._store(key, value)

    def __delitem__(self, key: Any, /) -> None:
        dict.__getitem__(self, key)
        self._remove(key)

    def pop(self, key: Any, default: Any = _MISSING, /) -> Any:
        value = dict.get(self, key, _MISSING)
        if value is _MISSING:
            if default is _MISSING:
                raise KeyError(key)
            return default
        self._remove(key)
        return value

    def _remove(self, key: Any) -> None:
        if self._log.recording and self._snapshot_span != (span := self._log.span):
            self._snapshot_span = span
            self._log.record(_restore_items, self, list(dict.items(self)))
        dict.__delitem__(self, key)

    def popitem(self) -> tuple[Any, Any]:
        key, value = dict.popitem(self)
        if self._log.recording:
            self._log.record(_restore_key, self, key, value)
        return key, value

    def setdefault(self, key: Any, default: Any = None, /) -> Any:
        value = dict.get(self, key, _MISSING)
        if value is _MISSING:
            self[key] = value = default
        return value

    def update(self, other: Any = (), /, **kwargs: Any) -> None:
        items = other.items() if hasattr(other, "items") else other
        for key, value in items:
            self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    def __ior__(self, other: Any, /) -> Self:
        self.update(other)
        return self

    def clear(self) -> None:
        if self._log.recording and self:
            self._log.record(dict.update, self, dict(self))
        dict.clear(self)

    def setdefault_list(self, key: Any) -> JournaledList:
        return self._setdefault_journaled(key, JournaledList)

    def setdefault_set(self, key: Any) -> JournaledSet:
        return self._setdefault_journaled(key, JournaledSet)

    def setdefault_dict(self, key: Any) -> JournaledDict:
        return self._setdefault_journaled(key, JournaledDict)

    def _setdefault_journaled[T: (JournaledList, JournaledSet, JournaledDict)](
        self, key: Any, kind: type[T]
    ) -> T:
        value = dict.get(self, key, _MISSING)
        if value is _MISSING:
            value = kind(self._log)
            self._store(key, value)
            return value
        if type(value) is not kind:
            raise TypeError(
                f"{key!r} holds a {type(value).__name__}, not a {kind.__name__}"
            )
        return value

    def __copy__(self) -> dict[Any, Any]:
        return dict(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[Any, Any]:
        return {
            copy.deepcopy(key, memo): copy.deepcopy(value, memo)
            for key, value in self.items()
        }


_JOURNALED_TYPES = (JournaledList, JournaledSet, JournaledDict)


class CallbackData(JournaledDict):
    __slots__ = ()

    def __setitem__(self, key: Any, value: Any, /) -> None:
        if type(value) not in _IMMUTABLE_TYPES:
            self._check_value(key, value)
        self._store(key, value)

    def _check_value(self, key: Any, value: Any) -> None:
        if isinstance(value, _JOURNALED_TYPES):
            if value._log is not self._log:
                raise TypeError(
                    f"hook data {key!r}: the container belongs to other hooks"
                )
            return
        if isinstance(value, _PLAIN_MUTABLE_TYPES) or _is_mutable_collection(value):
            _debug.logic(
                "callbacks.plain_container_refused",
                key=key,
                type=type(value).__name__,
            )
            raise TypeError(
                f"hook data {key!r} would hold a plain {type(value).__name__}, "
                "which a savepoint rollback cannot restore: build it with "
                "data.setdefault_list/setdefault_set/setdefault_dict, or keep it "
                "in durable_data when it must survive the rollback"
            )


def _is_mutable_collection(value: Any) -> bool:
    return isinstance(value, MutableMapping | MutableSequence | MutableSet)


def _snapshot_durable(data: dict[Any, Any]) -> dict[Any, tuple[Any, Any]]:
    copies = copy.deepcopy(data)
    return {key: (value, copies[key]) for key, value in data.items()}


def _restore_durable(
    data: dict[Any, Any], snapshot: dict[Any, tuple[Any, Any]]
) -> None:
    saved = copy.deepcopy({key: entry[1] for key, entry in snapshot.items()})
    data.clear()
    for key, (original, _copy) in snapshot.items():
        value = saved[key]
        if isinstance(original, dict):
            original.clear()
            original.update(value)
        elif isinstance(original, list | bytearray):
            original[:] = value
        elif isinstance(original, set):
            original.clear()
            original.update(value)
        elif isinstance(original, deque):
            original.clear()
            original.extend(value)
        else:
            original = value
        data[key] = original


class _Durable:
    __slots__ = ("func",)

    def __init__(self, func: Callable[[], object]) -> None:
        self.func = func

    def __call__(self) -> object:
        return self.func()

    def __repr__(self) -> str:
        return f"durable({self.func!r})"


class Callbacks:
    __slots__ = ("_funcs", "_log", "data", "durable_data")

    def __init__(self) -> None:
        self._log = UndoLog()
        self._funcs: deque[Callable[[], object]] = deque()
        self.data: CallbackData = CallbackData(self._log)
        self.durable_data: dict[Any, Any] = {}

    def add[F: Callable[[], object]](self, func: F) -> F:
        if self._log.recording:
            self._log.record(_remove_func, self._funcs, func)
        self._funcs.append(func)
        return func

    def add_durable[F: Callable[[], object]](self, func: F) -> F:
        durable = _Durable(func)
        if self._log.strict:
            self._log.record_strict(_remove_func, self._funcs, durable)
        self._funcs.append(durable)
        return func

    def _popleft(self) -> Callable[[], object]:
        func = self._funcs.popleft()
        log = self._log
        if log.recording:
            if type(func) is _Durable:
                log.record_durable(_prepend, self._funcs, func)
            else:
                log.record(_prepend, self._funcs, func)
        elif type(func) is _Durable and log.marked:
            log.record_durable(_prepend, self._funcs, func)
        return func

    def run(self) -> None:
        while self._funcs:
            self._popleft()()
        self.clear()

    def drain(self) -> None:
        first: Exception | None = None
        while self._funcs:
            func = self._popleft()
            try:
                func()
            except Exception as exc:
                if first is None:
                    first = exc
                else:
                    _logger.exception(
                        "hook %r failed after an earlier hook had failed", func
                    )
            except BaseException:
                if first is not None:
                    _logger.error("a hook failed before an interrupt", exc_info=first)
                raise
        self.clear()
        if first is not None:
            raise first

    def clear(self) -> None:
        log = self._log
        if log.marked:
            while self._funcs:
                self._popleft()
            if self.durable_data:
                log.record_durable(
                    dict.update, self.durable_data, dict(self.durable_data)
                )
        else:
            self._funcs.clear()
        self.data.clear()
        self.durable_data.clear()

    def __len__(self) -> int:
        return len(self._funcs)

    def checkpoint(self, *, strict: bool = False) -> HookMark:
        mark = self._log.mark(bool(self._funcs or self.data), strict)
        if strict:
            mark.durable_snapshot = _snapshot_durable(self.durable_data)
        return mark

    def rollback_to(self, mark: HookMark) -> None:
        undone = self._log.rewind(mark)
        if undone is None:
            _debug.logic("callbacks.rollback_to_unknown_mark")
            return
        dropped = 0
        if not mark.full and (self._funcs or self.data):
            durable = [func for func in self._funcs if type(func) is _Durable]
            dropped = len(self._funcs) - len(durable)
            self._funcs.clear()
            self._funcs.extend(durable)
            dict.clear(self.data)
        if mark.durable_snapshot is not None:
            _restore_durable(self.durable_data, mark.durable_snapshot)
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "callbacks.rolled_back",
                undone=undone,
                full=mark.full,
                dropped=dropped,
                pending=len(self._funcs),
            )

    def release(self, mark: HookMark) -> None:
        self._log.release(mark)
