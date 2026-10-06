import dataclasses
import enum
import json as _json
import math
import re
import uuid
from collections.abc import Callable
from typing import Any

import orjson as _orjson

__all__ = [
    "OPT_INDENT_2",
    "OPT_SORT_KEYS",
    "dataclass_attributes",
    "dumps",
    "dumps_bytes",
    "loads",
]

OPT_INDENT_2: int = _orjson.OPT_INDENT_2
OPT_SORT_KEYS: int = _orjson.OPT_SORT_KEYS

_DEFAULT_OPT = _orjson.OPT_NON_STR_KEYS | _orjson.OPT_PASSTHROUGH_DATETIME


_SCALARS = frozenset({str, int, bool, type(None)})


def _orjson_shaped(value: Any, option: int) -> Any:
    kind = type(value)
    if kind in _SCALARS:
        return value
    if kind is float:
        return value if math.isfinite(value) else None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {
            _orjson_key(key, option): _orjson_shaped(item, option)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_orjson_shaped(item, option) for item in value]
    if isinstance(value, enum.Enum):
        return _orjson_shaped(value.value, option)
    if isinstance(value, uuid.UUID):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _orjson_shaped(dataclass_attributes(value), option)
    return value


def dataclass_attributes(value: Any) -> dict[str, Any]:
    attributes = getattr(value, "__dict__", None)
    if attributes is None:
        attributes = {
            field.name: getattr(value, field.name)
            for field in dataclasses.fields(value)
        }
    return {name: item for name, item in attributes.items() if not name.startswith("_")}


def _orjson_key(key: Any, option: int) -> str:
    if isinstance(key, str):
        return key
    if type(key) is int:
        return str(key)
    # orjson's own spelling ("1e-7", "true", an Enum's value) keeps the
    # fallback identical, and all-str keys still sort when the stdlib sorts
    (spelled,) = _orjson.loads(_orjson.dumps({key: None}, option=option))
    return spelled


def _encode(obj: Any, default: Callable | None, option: int) -> bytes:
    try:
        return _orjson.dumps(obj, default=default, option=option)
    except TypeError as error:
        # orjson refuses what JSON can carry: an integer past 64 bits, and a
        # str holding a lone surrogate (text decoded with surrogateescape).
        # The stdlib writes both; the payload keeps orjson's shape otherwise.
        # What the stdlib refuses too re-raises orjson's own error.
        indent = 2 if option & _orjson.OPT_INDENT_2 else None
        key_option = option & ~(_orjson.OPT_INDENT_2 | _orjson.OPT_SORT_KEYS)
        try:
            return _json.dumps(
                _orjson_shaped(obj, key_option),
                default=default and (lambda o: _orjson_shaped(default(o), key_option)),
                indent=indent,
                separators=(",", ": ") if indent else (",", ":"),
                sort_keys=bool(option & _orjson.OPT_SORT_KEYS),
            ).encode()
        except TypeError, ValueError, RecursionError:
            raise error from None


def dumps(
    obj: Any,
    *,
    default: Callable | None = None,
    ensure_ascii: bool = False,
    option: int | None = None,
) -> str:
    if ensure_ascii:
        msg = "orjson cannot produce ASCII-escaped output; use stdlib json.dumps"
        raise ValueError(msg)
    return _encode(obj, default, _DEFAULT_OPT | (option or 0)).decode("utf-8")


def dumps_bytes(
    obj: Any,
    *,
    default: Callable | None = None,
    option: int | None = None,
) -> bytes:
    return _encode(obj, default, _DEFAULT_OPT | (option or 0))


def loads(
    s: str | bytes | bytearray | memoryview,
    *,
    lone_surrogates: bool = False,
    parse_float: Callable[[str], Any] | None = None,
    parse_constant: Callable[[str], Any] | None = None,
    strict: bool = True,
) -> Any:
    # orjson refuses a subclass (Markup, a lazy text); the stdlib reads it,
    # and raises TypeError, not a decode error, for what is no text at all
    if type(s) is not str and isinstance(s, str):
        s = str(s)
    elif type(s) is not bytes and isinstance(s, bytes):
        s = bytes(s)
    elif not isinstance(s, (str, bytes, bytearray, memoryview)):
        msg = f"the JSON object must be str, bytes or bytearray, not {type(s).__name__}"
        raise TypeError(msg)
    if parse_float is not None or parse_constant is not None or not strict:
        # orjson has no parse hooks and no lenient mode: they are the stdlib's
        return _json.loads(
            bytes(s) if isinstance(s, memoryview) else s,
            parse_float=parse_float,
            parse_constant=parse_constant,
            strict=strict,
        )
    try:
        value = _orjson.loads(s)
    except _orjson.JSONDecodeError as error:
        if not _is_what_dumps_writes(error, lone_surrogates):
            raise
        data = s.encode(errors="surrogatepass") if isinstance(s, str) else bytes(s)
        if not _orjson_reads_it_rewritten(data, error, lone_surrogates):
            raise
        try:
            return _json.loads(
                data.decode(),
                parse_constant=_refuse_constant,
                parse_float=_finite_float,
            )
        except ValueError, RecursionError:
            raise error from None
    if isinstance(value, (dict, list, float)) and _has_wide_integer(s):
        # orjson reads an integer past 64 bits as a float; the stdlib keeps it
        # exact. orjson parsed first, so what it rejects is still rejected.
        return _json.loads(bytes(s) if isinstance(s, memoryview) else s)
    return value


# orjson's wording (pinned in requirements.txt) for the two things dumps
# writes through the stdlib; the round-trip tests fail if it changes
_LONE_SURROGATE_ERRORS = frozenset(
    {
        "no low surrogate in string",
        "invalid high surrogate in string",
        "invalid low surrogate in string",
    }
)
_DOUBLE_OVERFLOW_ERROR = "number is infinity when parsed as double"


def _is_what_dumps_writes(
    error: _orjson.JSONDecodeError, lone_surrogates: bool
) -> bool:
    return error.msg == _DOUBLE_OVERFLOW_ERROR or (
        lone_surrogates and error.msg in _LONE_SURROGATE_ERRORS
    )


def _orjson_reads_it_rewritten(
    data: bytes, error: _orjson.JSONDecodeError, lone_surrogates: bool
) -> bool:
    # The stdlib reads more than orjson: a BOM, UTF-16, raw surrogate bytes,
    # nesting past 1024. Each rewrite clears its kind of error everywhere and
    # keeps the document's grammar, so orjson accepting the rewritten bytes
    # proves those two kinds were its only objection.
    for _ in range(2):
        if not _is_what_dumps_writes(error, lone_surrogates):
            return False
        if error.msg == _DOUBLE_OVERFLOW_ERROR:
            rewritten = _with_short_digit_runs(data)
            if rewritten is None:
                return False
            data = rewritten
        else:
            data = data.replace(b"\\ud", b"\\u0").replace(b"\\uD", b"\\u0")
        try:
            _orjson.loads(data)
        except _orjson.JSONDecodeError as next_error:
            error = next_error
        else:
            return True
    return False


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def _finite_float(text: str) -> float:
    value = float(text)
    if math.isinf(value):
        raise ValueError(f"{text} overflows a double")
    return value


_DIGIT_MASK = bytes(
    0x30 if 0x30 <= b <= 0x39 else b if b == 0x2D else 0x78 for b in range(256)
)
# orjson reads any 19-digit integer exactly, and a negative one down to i64
# only, so 20 digits or a minus and 19 are where it may read a float instead
_WIDE_POSITIVE = b"0" * 20
_WIDE_NEGATIVE = b"-" + b"0" * 19
# a 309-digit integer is where a double may overflow; two leading digits keep
# a run's grammar (a leading zero followed by more digits stays invalid)
_OVERFLOWING_RUN = b"0" * 309
_NOT_A_DIGIT = re.compile(rb"[^0]")


def _has_wide_integer(s: str | bytes | bytearray | memoryview) -> bool:
    data = s.encode(errors="surrogatepass") if isinstance(s, str) else bytes(s)
    masked = data.translate(_DIGIT_MASK)
    return _WIDE_POSITIVE in masked or _WIDE_NEGATIVE in masked


def _with_short_digit_runs(data: bytes) -> bytes | None:
    masked = data.translate(_DIGIT_MASK)
    pieces: list[bytes] = []
    end = 0
    while (start := masked.find(_OVERFLOWING_RUN, end)) != -1:
        pieces += (data[end:start], data[start : start + 2])
        run_end = _NOT_A_DIGIT.search(masked, start + len(_OVERFLOWING_RUN))
        end = run_end.start() if run_end else len(data)
    if not pieces:
        return None
    pieces.append(data[end:])
    return b"".join(pieces)
