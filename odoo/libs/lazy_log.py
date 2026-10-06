from collections.abc import Callable, Iterable, Mapping, Sequence, Sized
from typing import Protocol

__all__ = [
    "LazyLogValue",
    "format_record_label",
    "get_lazy_count",
    "get_lazy_keys",
    "get_lazy_record_label",
    "get_lazy_record_names",
    "get_lazy_values_keys",
]

_MAX_IDS = 8


class RecordLabelSource(Protocol):
    @property
    def _name(self) -> str: ...

    @property
    def _ids(self) -> Sequence[object]: ...


class RecordNamesSource(Protocol):
    def mapped(self, field: str) -> Sequence[object]: ...


class LazyLogValue:
    __slots__ = ("fn",)

    def __init__(self, fn: Callable[[], object]) -> None:
        self.fn = fn

    def __str__(self) -> str:
        try:
            return str(self.fn())
        except Exception as exc:  # a label must never break the caller
            return f"<unprintable: {exc!r}>"

    __repr__ = __str__


def format_record_label(records: RecordLabelSource) -> str:
    name = records._name
    ids = records._ids
    if not ids:
        return f"{name}[]"
    shown = ",".join(str(i) for i in ids[:_MAX_IDS])
    if len(ids) > _MAX_IDS:
        return f"{name}[{len(ids)}: {shown},...]"
    return f"{name}({shown})"


def get_lazy_record_label(records: RecordLabelSource) -> LazyLogValue:
    return LazyLogValue(lambda: format_record_label(records))


def get_lazy_keys(vals: Mapping[str, object]) -> LazyLogValue:
    return LazyLogValue(lambda: sorted(vals))


def get_lazy_values_keys(vals_list: Iterable[Mapping[str, object]]) -> LazyLogValue:
    return LazyLogValue(lambda: sorted({k for vals in vals_list for k in vals}))


def get_lazy_record_names(
    records: RecordNamesSource, field: str = "display_name"
) -> LazyLogValue:
    return LazyLogValue(lambda: records.mapped(field)[:_MAX_IDS])


def get_lazy_count(iterable: Sized) -> LazyLogValue:
    return LazyLogValue(lambda: len(iterable))
