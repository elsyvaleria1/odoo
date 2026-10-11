import threading
from collections.abc import ItemsView
from dataclasses import dataclass
from typing import ClassVar, assert_type

from odoo.libs.callbacks import UndoLog
from odoo.libs.collections import (
    Collector,
    FrozenOrderedSet,
    OrderedSet,
    frozendict,
    submap,
)
from odoo.libs.debug_log import DebugLog
from odoo.libs.documents.document import Document
from odoo.libs.documents.readers import _prepare_reader
from odoo.libs.documents.writers import _prepare_writer
from odoo.libs.func import locked
from odoo.libs.iteration import groupby
from odoo.libs.lru import LRU
from odoo.libs.settings import SettingsSlot
from odoo.libs.utils import is_list_of

from .test_collector import KeysOnlyMapping


class LockedOwner:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    @locked
    def describe(self, value: int, /, *, label: str = "") -> str:
        return f"{label}{value}"


class ClassLockedOwner:
    _lock: ClassVar[threading.RLock] = threading.RLock()

    @classmethod
    @locked
    def describe(cls, value: int, /, *, label: str = "") -> str:
        return f"{label}{value}"


def decorator_contracts(owner: LockedOwner) -> None:
    assert_type(owner.describe(3), str)
    assert_type(owner.describe(3, label="value="), str)
    assert_type(LockedOwner.describe(owner, 3), str)
    owner.describe("3")  # type: ignore[arg-type]  # Preserve the argument type.
    owner.describe(3, "label")  # type: ignore[call-arg]  # Preserve keyword-only binding.
    owner.describe(3, label=4)  # type: ignore[arg-type]  # Preserve keyword types.
    LockedOwner.describe(object(), 3)  # type: ignore[arg-type]  # Preserve the receiver.
    assert_type(ClassLockedOwner.describe(3, label="value="), str)
    ClassLockedOwner.describe("3")  # type: ignore[arg-type]  # Check classmethod binding too.

    @locked  # type: ignore[type-var]  # A receiver must supply a context-manager lock.
    def missing_lock(owner: object) -> int:
        return 1


def sequence_contracts(
    value: object, values: list[object], members: tuple[object, ...]
) -> None:
    if is_list_of(value, int):
        assert_type(value, list[int] | tuple[int, ...])
        assert_type(value[0], int)
    element_types: tuple[type[int | str], ...] = (int, str)
    if is_list_of(value, element_types):
        assert_type(value, list[int | str] | tuple[int | str, ...])
    if is_list_of(values, int):
        assert_type(values, list[int])
    if is_list_of(members, int):
        assert_type(members, tuple[int, ...])
    is_list_of(value, 3)  # type: ignore[call-overload]  # The validator takes types.


def logging_contracts(debug: DebugLog) -> None:
    assert_type(debug.logic("event"), None)
    assert_type(debug.perf.count("event"), None)
    with debug.perf("event") as span:
        assert_type(span.set(count=3), None)

    @debug.perf.timed
    def describe(value: int, /, *, label: str = "") -> str:
        return f"{label}{value}"

    assert_type(describe(3, label="value="), str)
    describe("3")  # type: ignore[arg-type]  # Timing preserves positional types.
    describe(3, "label")  # type: ignore[call-arg]  # Timing preserves keyword-only binding.
    describe(3, label=4)  # type: ignore[arg-type]  # Timing preserves keyword types.


def document_callback_contracts() -> None:
    def read(document: Document) -> str:
        return document.decoded

    def write(value: object, **options: object) -> bytes:
        return str(value).encode()

    _prepare_reader("text", frozenset({"text/plain"}), ("text",), read)
    _prepare_writer("text", "text/plain", "text", write)

    def invalid_reader() -> str:
        return ""

    def invalid_writer(value: object) -> bytes:
        return b""

    _prepare_reader("text", frozenset({"text/plain"}), ("text",), invalid_reader)  # type: ignore[arg-type]  # A reader must accept a document.
    _prepare_writer("text", "text/plain", "text", invalid_writer)  # type: ignore[arg-type]  # A writer must accept options.


def collection_contracts() -> None:
    collected = Collector({"a": [1, 2]})
    assert_type(collected, Collector[str, int])
    assert_type(collected["a"], tuple[int, ...])
    assert_type(collected.get("missing"), tuple[int, ...])
    assert_type(collected.get("missing", ()), tuple[int, ...])
    assert_type(collected.get("missing", None), tuple[int, ...] | None)
    assert_type(collected.get("missing", default="absent"), tuple[int, ...] | str)
    assert_type(collected.pop("missing"), tuple[int, ...])
    assert_type(collected.pop("missing", ()), tuple[int, ...])
    assert_type(collected.pop("missing", default=None), tuple[int, ...] | None)
    collected.update({"a": (3,)})
    collected.update([("b", [4])])
    collected.update(c=[5])
    collected.update(KeysOnlyMapping())
    collected.update({"a": 3})  # type: ignore[arg-type]  # Values must be iterable.
    collected.update({"a": ["3"]})  # type: ignore[arg-type]  # Preserve value types.
    collected["a"] = ["3"]  # type: ignore[list-item]  # Validate direct writes too.
    collected[3] = [3]  # type: ignore[index]  # Preserve key types.
    assert_type(Collector(a=[1]), Collector[str, int])

    cache = LRU[str, int](2)
    assert_type(cache.get("a"), int | None)
    assert_type(cache.get("a", "absent"), int | str)
    assert_type(cache.pop("a"), int)
    assert_type(cache.pop("a", default=None), int | None)
    assert_type(cache.pop("a", default="absent"), int | str)
    cache["a"] = "3"  # type: ignore[assignment]  # Preserve cached value types.

    assert_type(frozendict.fromkeys(["a", "b"]), frozendict[str, None])
    assert_type(frozendict.fromkeys(["a"], 3), frozendict[str, int])
    assert_type(frozendict.fromkeys([3], "a"), frozendict[int, str])
    assert_type(submap({"a": 3}, ["a"]), dict[str, int])


def set_contracts() -> None:
    integers = OrderedSet([1, 2])
    assert_type(integers & {"a"}, OrderedSet[int])
    assert_type(integers - {"a"}, OrderedSet[int])
    assert_type(integers | {"a"}, OrderedSet[int | str])
    assert_type(integers ^ {"a"}, OrderedSet[int | str])
    integers.add("a")  # type: ignore[arg-type]  # Mutation cannot widen the element type.

    frozen = FrozenOrderedSet([1, 2])
    assert_type(frozen & {"a"}, FrozenOrderedSet[int])
    assert_type(frozen - {"a"}, FrozenOrderedSet[int])
    assert_type(frozen | {"a"}, FrozenOrderedSet[int | str])
    assert_type(frozen ^ {"a"}, FrozenOrderedSet[int | str])

    assert_type(groupby([1, 2]), ItemsView[int, list[int]])
    assert_type(groupby([1, 2], str), ItemsView[str, list[int]])


def callback_contracts(log: UndoLog) -> None:
    def undo(key: str, value: int, /) -> None:
        pass

    log.record(undo, "a", 3)
    log.record_durable(undo, "a", 3)
    log.record_strict(undo, "a", 3)
    log.record(undo, "a", "3")  # type: ignore[arg-type]  # Callback arguments must match.
    log.record_durable(undo, 3, 3)  # type: ignore[arg-type]  # Check durable callbacks too.
    log.record_strict(undo, "a")  # type: ignore[arg-type]  # Check arity as well as types.


@dataclass(frozen=True)
class Settings:
    count: int = 1


def settings_contracts() -> None:
    slot = SettingsSlot("settings", Settings)
    assert_type(slot.current(), Settings)
    with slot.installed(Settings(3)) as installed:
        assert_type(installed, Settings)
    with slot.override(count=3) as overridden:
        assert_type(overridden, Settings)

    SettingsSlot("scalar", lambda: 3)  # type: ignore[type-var]  # Settings must be dataclasses.
