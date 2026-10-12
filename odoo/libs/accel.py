from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from typing import Any, cast

from . import _trigger_trees
from ._field_access import _fallback as _field_access
from .debug_log import DebugLog

try:
    import odoo_rust as _native
except ImportError:
    _native = None

NATIVE = _native is not None
_debug = DebugLog(__name__)

__all__ = [
    "NATIVE",
    "batch_cache_fill",
    "batch_cache_filter",
    "batch_cache_get",
    "batch_group_ids",
    "csv_export",
    "fast_clone",
    "get_trigger_trees",
    "origin_ids",
    "rows_to_dicts",
    "sort_ids_by_cache",
    "to_prefetch_ids",
]

_FORMULA_PREFIXES = ("=", "-", "+", "@", "\t", "\r")


_require = _field_access.require_type


def csv_export_python(headers: list[Any], rows: list[Any]) -> bytes:
    _require("csv_export", "headers", headers, list)
    _require("csv_export", "rows", rows, list)
    fp = io.StringIO()
    writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
    writer.writerow(headers)
    for row in rows:
        cells = []
        for value in row:
            if value is None or value is False:
                value = ""
            elif isinstance(value, bytes):
                value = value.decode()
            if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
                value = "'" + value
            cells.append(value)
        writer.writerow(cells)
    return fp.getvalue().encode()


def rows_to_dicts_python(
    names: tuple[str, ...], rows: list[tuple[Any, ...]]
) -> list[dict[str, Any]]:
    _require("rows_to_dicts", "names", names, tuple)
    _require("rows_to_dicts", "rows", rows, list)
    keys = names if type(names) is tuple else tuple(tuple.__iter__(names))
    width = len(keys)
    count = list.__len__(rows)
    result = []
    for index in range(count):
        if list.__len__(rows) != count:
            raise ValueError(
                "rows_to_dicts: `rows` changed length during the conversion"
            )
        row = list.__getitem__(rows, index)
        if type(row) is not tuple:
            if not issubclass(type(row), tuple):
                raise TypeError(f"row {index} is not a tuple")
            row = tuple(tuple.__iter__(row))
        if len(row) != width:
            raise ValueError(f"row {index} has {len(row)} elements, expected {width}")
        result.append(dict(zip(keys, row, strict=True)))
    return result


_MAX_CLONE_DEPTH = 500


def fast_clone_python[T](obj: T) -> T:
    return _clone(obj, 0)


def _clone[T](obj: T, depth: int) -> T:
    if depth >= _MAX_CLONE_DEPTH:
        raise RecursionError(
            "fast_clone: maximum nesting depth exceeded (cyclic or too-deep structure)"
        )
    if isinstance(obj, dict):
        return cast("T", {key: _clone(value, depth + 1) for key, value in obj.items()})
    if isinstance(obj, list):
        return cast("T", [_clone(value, depth + 1) for value in obj])
    if isinstance(obj, tuple):
        return cast("T", tuple([_clone(value, depth + 1) for value in obj]))
    return obj


def origin_ids_python(ids: Iterable[Any]) -> tuple[int, ...]:
    return tuple(oid for id_ in ids if (oid := id_ or getattr(id_, "origin", None)))


def _pick[F](name: str, python: F) -> F:
    _debug.lifecycle("accel.pick", function=name, native=_native is not None)
    return getattr(_native, name) if _native is not None else python


csv_export = _pick("csv_export", csv_export_python)
rows_to_dicts = _pick("rows_to_dicts", rows_to_dicts_python)
fast_clone = _pick("fast_clone", fast_clone_python)
origin_ids = _pick("origin_ids", origin_ids_python)
batch_cache_fill = _pick("batch_cache_fill", _field_access.batch_cache_fill)
batch_cache_filter = _pick("batch_cache_filter", _field_access.batch_cache_filter)
batch_cache_get = _pick("batch_cache_get", _field_access.batch_cache_get)
batch_group_ids = _pick("batch_group_ids", _field_access.batch_group_ids)
get_trigger_trees = _pick("get_trigger_trees", _trigger_trees.get_trigger_trees)
sort_ids_by_cache = _pick("sort_ids_by_cache", _field_access.sort_ids_by_cache)
to_prefetch_ids = _pick("to_prefetch_ids", _field_access.to_prefetch_ids)
