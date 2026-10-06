from __future__ import annotations

import functools
import heapq
import itertools
import logging
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, cast

if TYPE_CHECKING:
    import types
    from collections.abc import Callable, Iterable

__all__ = ["CHANNELS", "ROOT", "DebugLog", "debug_scope", "format_event"]

# Every debug logger this module hands out lives under ROOT, so one
# `--log-handler odoo.debug:DEBUG` enables all of them and
# `--log-handler odoo.debug.perf:DEBUG` enables one channel across the tree.
# The JS twin (@web/core/debug/debug_logger) uses the same four channel names.
ROOT = "odoo.debug"
CHANNELS = ("logic", "perf", "pipeline", "lifecycle")

# An addon's layer segment is dropped from its scope unless an earlier layer of
# the same addon holds a module of the same name: controllers/event_track.py
# then keeps "controllers" so its loggers stay apart from models/event_track.py.
_ADDON_LAYERS = ("models", "wizards", "wizard", "reports", "controllers")


def debug_scope(module_name: str) -> str:
    parts = module_name.split(".")
    if parts[:2] == ["odoo", "addons"] and len(parts) >= 3:
        parts = parts[2:]
        if len(parts) >= 3 and parts[1] in _ADDON_LAYERS and not _shadowed(parts):
            del parts[1]
        return ".".join(parts)
    if parts[0] == "odoo" and len(parts) > 1:
        parts = parts[1:]
    return ".".join(parts)


def _shadowed(parts: list[str]) -> bool:
    package = sys.modules.get(f"odoo.addons.{parts[0]}")
    roots = getattr(package, "__path__", None) or ()
    earlier = _ADDON_LAYERS[: _ADDON_LAYERS.index(parts[1])]
    return any(
        _is_module(Path(root, layer, *parts[2:])) for root in roots for layer in earlier
    )


def _is_module(path: Path) -> bool:
    return (
        path.with_name(f"{path.name}.py").is_file() or (path / "__init__.py").is_file()
    )


_MAX_IDS = 8


def _format_records(model: str, ids: Any) -> str:
    shown = ",".join(str(i).replace(" ", "") for i in ids[:_MAX_IDS])
    hidden = len(ids) - _MAX_IDS
    return f"{model}({shown},+{hidden})" if hidden > 0 else f"{model}({shown})"


def _format_text(text: str) -> str:
    return text if text and not any(c.isspace() for c in text) else repr(text)


_MAX_DEPTH = 3
# an item holding one of these would read as the collection's own syntax
_ITEM_SYNTAX = frozenset(",[](){}'\"")


# a string that would read as another value -- a number, inf or nan,
# None/True/False, the overflow (+N) or depth (<list:N>) markers -- is quoted
# inside a collection, so ["1", 1] and [None, "None"] stay apart; inside
# braces, one holding ":" too, so a set {"a:b"} is no dict {a:b}
_READS_AS_OTHER = re.compile(r"[+-]?(?:\d[\d.e+-]*|inf|nan)|None|True|False|[+<].*")


def _format_item(value: Any, depth: int, *, braced: bool = False) -> str:
    if isinstance(value, str) and (
        not value
        or _ITEM_SYNTAX.intersection(value)
        or (braced and ":" in value)
        or _READS_AS_OTHER.fullmatch(value)
    ):
        return repr(value)
    return _format_value(value, depth)


def _format_items(
    items: Iterable[Any], size: int, depth: int, *, braced: bool = False
) -> str:
    shown = [
        _format_item(item, depth + 1, braced=braced)
        for item in itertools.islice(items, _MAX_IDS)
    ]
    if (hidden := size - _MAX_IDS) > 0:
        shown.append(f"+{hidden}")
    return ",".join(shown)


def _first_sorted(items: Any) -> list[Any]:
    try:
        return heapq.nsmallest(_MAX_IDS, items)
    except TypeError:
        return list(itertools.islice(items, _MAX_IDS))


_COLLECTIONS = (list, tuple, set, frozenset, dict)
_SETS = (set, frozenset)


def _format_collection(value: Any, depth: int) -> str | None:
    if isinstance(value, list):
        return f"[{_format_items(value, len(value), depth)}]"
    if isinstance(value, tuple):
        shown = _format_items(value, len(value), depth)
        return f"({shown},)" if len(value) == 1 else f"({shown})"
    if isinstance(value, _SETS):
        # a snapshot: another thread may be changing a live set or dict
        items = tuple(value)
        if not items:
            return "set()"
        shown = _format_items(_first_sorted(items), len(items), depth, braced=True)
        return f"{{{shown}}}"
    if isinstance(value, dict):
        pairs = [
            f"{_format_item(k, depth + 1, braced=True)}"
            f":{_format_item(v, depth + 1, braced=True)}"
            for k, v in itertools.islice(tuple(value.items()), _MAX_IDS)
        ]
        if (hidden := len(value) - _MAX_IDS) > 0:
            pairs.append(f"+{hidden}")
        return f"{{{','.join(pairs)}}}"
    return None


def _format_value(value: Any, depth: int = 0) -> str:
    if isinstance(value, str):
        return _format_text(value)
    # a collection prints bounded and unquoted, like a recordset: a field
    # list reads [a,b,c]; one holding whitespace is quoted whole, so an item
    # cannot forge a field of the line
    if isinstance(value, _COLLECTIONS):
        if depth >= _MAX_DEPTH:
            return f"<{type(value).__name__}:{len(value)}>"
        text = _format_collection(value, depth)
        assert text is not None
        return _format_text(text) if depth == 0 else text
    if isinstance(value, float):
        return f"{value:.3f}"
    # Duck-typed recordset, so a site passes the recordset itself: nothing is
    # computed when the channel is off, and a large one prints bounded.
    # A value that refuses inspection (an unbound werkzeug proxy raises
    # RuntimeError on any attribute) prints as its type: a log line must never
    # break the code it observes.
    try:
        model = getattr(value, "_name", None)
        if isinstance(model, str) and not isinstance(value, type):
            ids = getattr(value, "_ids", None)
            if isinstance(ids, tuple):
                return _format_records(model, ids)
        return _format_text(str(value))
    except Exception:
        return f"<unformattable:{type(value).__name__}>"


def format_event(event: str, fields: dict[str, Any]) -> str:
    parts = [f"event={event}"]
    parts.extend(f"{key}={_format_field(value)}" for key, value in fields.items())
    return " ".join(parts)


# a field whose formatting raises (a closed cursor, a failing lazy label)
# costs its own value, not the line, and never the code that logged it
def _format_field(value: Any) -> str:
    try:
        return _format_value(value)
    except Exception as error:
        return f"<unformattable:{type(error).__name__}>"


class _Channel:
    __slots__ = ("logger",)

    def __init__(self, name: str) -> None:
        self.logger = logging.getLogger(name)

    @property
    def enabled(self) -> bool:
        return self.logger.isEnabledFor(logging.DEBUG)

    def __call__(self, event: str, /, **fields: Any) -> None:
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("%s", format_event(event, fields))


# Round trips, not sql_log_count: executemany adds len(rows) to the latter, so a
# batched INSERT of N rows would read as N queries.
def _statements(cr: Any) -> int:
    try:
        return getattr(cr, "sql_statement_count", 0)
    except Exception:
        return 0


def _clock(_read: Callable[[], float] = time.perf_counter) -> float:
    # Capture the C clock in a default: freezing business time must neither
    # freeze spans nor exempt a timed method's whole call stack from freezing.
    return _read()


class _Span:
    __slots__ = ("_cr", "_fields", "_logger", "_queries", "_start", "event")

    def __init__(
        self, logger: logging.Logger, event: str, cr: Any, fields: dict[str, Any]
    ) -> None:
        self._logger = logger
        self.event = event
        self._cr = cr
        self._fields = fields
        self._start = 0.0
        self._queries = 0

    def set(self, **fields: Any) -> None:
        self._fields.update(fields)

    def __enter__(self) -> Self:
        self._queries = _statements(self._cr)
        self._start = _clock()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        elapsed_ms = (_clock() - self._start) * 1000.0
        fields = self._fields
        fields["ms"] = elapsed_ms
        if self._cr is not None:
            fields["queries"] = _statements(self._cr) - self._queries
        if exc_type is not None:
            fields["error"] = exc_type.__name__
        self._logger.debug("%s", format_event(self.event, fields))


class _DisabledSpan:
    __slots__ = ()

    def set(self, **fields: Any) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        pass


_DISABLED_SPAN = _DisabledSpan()


def _receiver_cursor(receiver: Any, fields: dict[str, Any]) -> Any:
    if receiver is None or isinstance(receiver, type):
        return None
    try:
        if isinstance(getattr(receiver, "_name", None), str):
            fields["records"] = receiver
        return getattr(getattr(receiver, "env", None), "cr", None)
    except Exception:
        return None


class _PerfChannel(_Channel):
    __slots__ = ()

    def count(self, event: str, /, **fields: Any) -> None:
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("%s", format_event(event, fields))

    def __call__(  # type: ignore[override]  # a perf event is a span, not a line
        self, event: str, /, cr: Any = None, **fields: Any
    ) -> _Span | _DisabledSpan:
        if not self.logger.isEnabledFor(logging.DEBUG):
            return _DISABLED_SPAN
        return _Span(self.logger, event, cr, fields)

    def timed[F: Callable[..., Any]](self, func: F) -> F:
        logger = self.logger
        event = func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not logger.isEnabledFor(logging.DEBUG):
                return func(*args, **kwargs)
            fields: dict[str, Any] = {}
            cr = _receiver_cursor(args[0] if args else None, fields)
            with _Span(logger, event, cr, fields):
                return func(*args, **kwargs)

        return cast("F", wrapper)


class DebugLog:
    __slots__ = ("lifecycle", "logic", "perf", "pipeline", "scope")

    def __init__(self, module_name: str) -> None:
        self.scope = debug_scope(module_name)
        self.logic = _Channel(f"{ROOT}.logic.{self.scope}")
        self.perf = _PerfChannel(f"{ROOT}.perf.{self.scope}")
        self.pipeline = _Channel(f"{ROOT}.pipeline.{self.scope}")
        self.lifecycle = _Channel(f"{ROOT}.lifecycle.{self.scope}")
