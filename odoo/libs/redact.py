from __future__ import annotations

import functools
import json
import logging
import re
import typing
from collections.abc import Mapping
from urllib.parse import quote, unquote_plus, urlparse, urlunparse

from odoo.libs.secret import MASK, Secret

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

__all__ = [
    "MASK",
    "REGISTERED_PATTERNS",
    "dump_masked",
    "find_secret_shapes",
    "is_sensitive_key",
    "mask_data",
    "mask_text",
    "mask_url",
    "register_pattern",
]

_logger = logging.getLogger(__name__)

_SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = (
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "client_secret",
    "private_key",
    "privatekey",
    "credential",
    "passphrase",
    "passcode",
    "sessionid",
    "sessid",
    "auth",
    "bearer",
    "signature",
    "x_amz_security_token",
    "x_amz_signature",
)

_SENSITIVE_KEY_WORDS: tuple[str, ...] = (
    "pass",
    "otp",
    "totp",
    "hotp",
    "jwt",
    "sid",
    "session_id",
    "cookie",
    "cookies",
)

_LABEL_SHAPES: tuple[tuple[str, str], ...] = (
    ("password", r"\b(password|passwd|pwd)[\"']?\s*[:=]\s*\S+"),
    ("api_key", r"\b(api[_-]?key|apikey)[\"']?\s*[:=]\s*\S+"),
    ("secret_or_token", r"\b(secret|token)[\"']?\s*[:=]\s*\S+"),
    ("aws_style_key", r"\b(access[_-]?key|secret[_-]?key)[\"']?\s*[:=]\s*\S+"),
)

_PEM = re.compile(
    r"-----BEGIN[\w ]*PRIVATE KEY(?: BLOCK)?-----.*?"
    r"(?:-----END[\w ]*PRIVATE KEY(?: BLOCK)?-----|\Z)",
    re.DOTALL,
)

_VALUE_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key_pem", _PEM),
    ("github_token", re.compile(r"\bgh[pousr]_[a-zA-Z0-9]{36}\b")),
    ("github_fine_grained_token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    (
        "json_web_token",
        re.compile(
            r"(?<![A-Za-z0-9_-])(?P<lead>(?:(?!(?<!\w)eyJ)[A-Za-z0-9_]*+-)*+)"
            r"(?<!\w)eyJ[A-Za-z0-9_-]++\.[A-Za-z0-9_-]++(?:\.[A-Za-z0-9_-]*+)++"
        ),
    ),
    ("openai_api_key", re.compile(r"\bsk-[a-zA-Z0-9]{48}\b")),
    (
        "prefixed_api_key",
        re.compile(r"\bsk-(?:proj|ant|svcacct|admin)-[A-Za-z0-9_-]{20,}"),
    ),
    ("stripe_secret_key", re.compile(r"\b[rs]k_(?:live|test)_[0-9a-zA-Z]{24,}\b")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer_token", re.compile(r"(?i:(?<=\bbearer\s))\s*[A-Za-z0-9._~+/-]{8,}=*")),
)

_SECRET_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    *((name, re.compile(pattern, re.IGNORECASE)) for name, pattern in _LABEL_SHAPES),
    *_VALUE_SHAPES,
)

REGISTERED_PATTERNS: list[
    tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]
] = []

_URL_IN_TEXT = re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*+://[^\s'\"<>]+")

_SENSITIVE_KEY = re.compile(
    "|".join(
        "auth(?!or)" if fragment == "auth" else re.escape(fragment)
        for fragment in _SENSITIVE_KEY_FRAGMENTS
    )
)

_KEY_CANDIDATE = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]++(?=[\"']?\s*[:=])")
_SENSITIVE_KEY_TAIL = re.compile(
    "(?:"
    + "|".join(
        "auth(?!or)" if fragment == "auth" else re.escape(fragment)
        for fragment in _SENSITIVE_KEY_FRAGMENTS
    )
    + ")(?=[_-]|$)"
)
_KEY_VALUE_AFTER = re.compile(
    r"(?i)(?P<sep>[\"']?\s*[:=]\s*)"
    r"(?:(?P<prefix>b?)(?P<quote>[\"'])(?:\\[\s\S]?|(?!(?P=quote))[^\\])*(?:(?P=quote)|\Z)"
    r"|(?:[A-Za-z_][\w.]*+)?(?P<open>[\[{(])"
    r"|(?P<scheme>(?:bearer|basic|digest|token)\s+)?"
    r"(?P<bare>(?:[^\s&;'\"<>,)\]}]++|[,)\]}]++(?![\s&;'\"<>]|\Z))++))"
)
_BARE_VALUE = re.compile(r"(?:[^\s&;'\"<>,)\]}]++|[,)\]}]++(?![\s&;'\"<>]|\Z))++")
_NESTED_TOKEN = re.compile(
    r"""[^()\[\]{}'"]++|(['"])(?:\\[\s\S]?|(?!\1)[^\\])*+(?:\1|\Z)|[(\[{]|[)\]}]"""
)
_LITERALS = frozenset(("True", "False", "None", "true", "false", "null"))
_MASKED_LABEL = re.compile(r"[•●*]{4}(?:[ -]?[•●*]{4})*[ -]?\d{4}(?!\w)")

_LABEL_TAIL = re.compile(r"[.,:;!?]")
_KEY_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_SENSITIVE_KEY_WORD = re.compile(
    "(?:^|_)(?:"
    + "|".join(re.escape(word) for word in _SENSITIVE_KEY_WORDS)
    + ")(?=_|$)"
)

_PAIR_LABEL_KEYS = ("name", "key", "header", "field")


def register_pattern(
    pattern: str | re.Pattern[str],
    replacement: str | Callable[[re.Match[str]], str],
) -> None:
    compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
    REGISTERED_PATTERNS.append((compiled, replacement))


def _snake_words(key: str) -> str:
    return "_".join(_KEY_WORD.findall(key)).lower()


def _has_sensitive_word(key: str) -> bool:
    return _SENSITIVE_KEY_WORD.search(_snake_words(key)) is not None


def is_sensitive_key(key: object) -> bool:
    text = str(key)
    return _SENSITIVE_KEY.search(
        text.lower().replace("-", "_")
    ) is not None or _has_sensitive_word(text)


def find_secret_shapes(text: str) -> list[str]:
    if not text:
        return []
    return [name for name, pattern in _SECRET_SHAPES if pattern.search(text)]


def _apply_registered(value: str) -> str:
    for pattern, replacement in REGISTERED_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


_NESTED_URL_DEPTH = 3


def _mask_pairs(encoded: str, depth: int = 0) -> str:
    pairs = []
    for pair in encoded.split("&"):
        key, sep, value = pair.partition("=")
        if sep and is_sensitive_key(unquote_plus(key)):
            pairs.append(f"{key}={MASK}")
            continue
        if sep and depth < _NESTED_URL_DEPTH:
            nested = unquote_plus(value)
            if any(c in nested for c in "?=#"):
                masked = _mask_url(nested, depth + 1)
                if masked != nested:
                    pair = f"{key}={quote(masked, safe='/:*')}"
        pairs.append(pair)
    return "&".join(pairs)


def _mask_unparsable_url(url: str) -> str:
    before_fragment, hash_mark, fragment = url.partition("#")
    base, question_mark, query = before_fragment.partition("?")
    return "".join(
        (
            _mask_key_values(base),
            question_mark,
            _mask_key_values(query),
            hash_mark,
            _mask_key_values(fragment),
        )
    )


def mask_url(url: str | Secret) -> str:
    if isinstance(url, Secret):
        return MASK
    return _mask_url(url, 0)


def _mask_url(url: str, depth: int) -> str:
    masked = _apply_registered(url)
    try:
        parsed = urlparse(masked)
    except ValueError:
        return _mask_unparsable_url(masked)

    netloc = parsed.netloc
    if "@" in netloc:
        netloc = f"***:***@{netloc.rsplit('@', 1)[1]}"

    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            _mask_pairs(parsed.query, depth),
            _mask_pairs(parsed.fragment, depth),
        ),
    )


_COUNTER_KEY = re.compile(r"(?:^|[_-])(?:count|total|length|len|size|limit|ttl|id)$")
_DIGITS = re.compile(r"\d+")


def _is_counter(key: object, value: typing.Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        if not _DIGITS.fullmatch(value):
            return False
    elif not isinstance(value, int):
        return False
    return _COUNTER_KEY.search(_snake_words(str(key))) is not None


def _is_masked_label(value: typing.Any) -> bool:
    return isinstance(value, str) and _MASKED_LABEL.fullmatch(value) is not None


def _masks(key: object, value: typing.Any) -> bool:
    return (
        is_sensitive_key(key)
        and not _is_counter(key, value)
        and not _is_masked_label(value)
    )


@functools.lru_cache(maxsize=4096)
def _is_sensitive_text_key(key: str) -> bool:
    return bool(
        _SENSITIVE_KEY_TAIL.search(_snake_words(key))
        or _SENSITIVE_KEY_TAIL.search(key.lower().replace("-", "_"))
        or _has_sensitive_word(key)
    )


_CLOSER = {"(": ")", "[": "]", "{": "}"}
_BARE_TAIL = re.compile(r"[^\s&;'\"<>,)\]}]*+")


def _match_end(pattern: re.Pattern[str], text: str, at: int) -> int:
    match = pattern.match(text, at)
    return match.end() if match else at


def _balanced_end(text: str, start: int) -> int:
    expected: list[str] = []
    pos = start
    while token := _NESTED_TOKEN.match(text, pos):
        pos = token.end()
        if token[0] in _CLOSER:
            expected.append(_CLOSER[token[0]])
        elif token[0] in ")]}":
            if not expected or token[0] != expected.pop():
                return len(text)
            if not expected:
                return pos
    return len(text)


def _label_spans(text: str, start: int, end: int) -> bool:
    label = _MASKED_LABEL.match(text, start)
    return label is not None and (
        label.end() >= end or _LABEL_TAIL.fullmatch(text, label.end(), end) is not None
    )


def _value_mask(
    text: str, key: str, at: int, *, listed: bool
) -> tuple[int, int, str] | None:
    value = _KEY_VALUE_AFTER.match(text, at)
    if value is None:
        return None
    start = value.end("sep")
    if value["open"] is not None:
        closed = _balanced_end(text, value.start("open"))
        end = max(
            _match_end(_BARE_VALUE, text, start), _match_end(_BARE_TAIL, text, closed)
        )
        return start, end, MASK
    if value["quote"] is not None:
        quote = value["quote"]
        inner = text[value.end("quote") : value.end()].removesuffix(quote)
        if _is_masked_label(inner):
            return None
        return start, value.end(), f"{value['prefix']}{quote}{MASK}{quote}"
    bare = value["bare"]
    if value["scheme"] is None and (
        bare in _LITERALS
        or _is_masked_label(bare)
        or _label_spans(text, value.start("bare"), value.end("bare"))
        or (not listed and _is_counter(key, bare))
    ):
        return None
    return start, value.end(), f"{value['scheme'] or ''}{MASK}"


def _mask_values_after(
    text: str, keys: Iterator[re.Match[str]], *, listed: bool
) -> str:
    parts: list[str] = []
    done = 0
    for key in keys:
        if key.start() < done or not (listed or _is_sensitive_text_key(key[0])):
            continue
        masked = _value_mask(text, key[0], key.end(), listed=listed)
        if masked is None:
            continue
        start, end, replacement = masked
        parts.append(text[done:start])
        parts.append(replacement)
        done = end
    parts.append(text[done:])
    return "".join(parts)


def _mask_key_values(text: str) -> str:
    return _mask_values_after(text, _KEY_CANDIDATE.finditer(text), listed=False)


@functools.lru_cache(maxsize=64)
def _listed_key_pattern(keys: frozenset[str]) -> re.Pattern[str]:
    names = "|".join(map(re.escape, sorted(keys, key=len, reverse=True)))
    return re.compile(rf"""(?<![\w.-])(?P<kq>['"]?)(?:{names})(?=(?P=kq)\s*[:=])""")


_WINDOW_MARGIN = 4096


def mask_text(
    text: str | Secret, limit: int | None = None, *, keys: Iterable[str] = ()
) -> str:
    if isinstance(text, Secret):
        return MASK
    if not text:
        return text
    listed = frozenset(keys)
    if limit:
        return _mask_text(str(text)[: limit + _WINDOW_MARGIN], listed)[:limit]
    return _mask_text(str(text), listed)


_SHAPE_GATES: dict[str, re.Pattern[str]] = {
    "private_key_pem": re.compile(r"PRIVATE KEY(?: BLOCK)?-----"),
    "github_token": re.compile(r"gh[pousr]_"),
    "github_fine_grained_token": re.compile(r"github_pat_"),
    "slack_token": re.compile(r"xox"),
    "json_web_token": re.compile(r"eyJ"),
    "openai_api_key": re.compile(r"sk-"),
    "prefixed_api_key": re.compile(r"sk-"),
    "stripe_secret_key": re.compile(r"k_(?:live|test)_"),
    "aws_access_key_id": re.compile(r"AKIA"),
    "bearer_token": re.compile(r"(?i)bearer"),
}


def _mask_text(text: str, keys: frozenset[str] = frozenset()) -> str:
    masked = _apply_registered(text)
    if "-----BEGIN" in masked:
        masked = _PEM.sub(MASK, masked)
    masked = _URL_IN_TEXT.sub(lambda match: mask_url(match.group(0)), masked)
    masked = _mask_key_values(masked)
    if keys:
        masked = _mask_values_after(
            masked, _listed_key_pattern(keys).finditer(masked), listed=True
        )
    for name, shape in _VALUE_SHAPES:
        gate = _SHAPE_GATES.get(name)
        if gate is None or gate.search(masked):
            masked = shape.sub(_mask_shape, masked)
    return masked


def _mask_shape(match: re.Match[str]) -> str:
    return match["lead"] + MASK if "lead" in match.re.groupindex else MASK


def _is_sensitive_pair(data: Mapping[typing.Any, typing.Any]) -> bool:
    if "value" not in data:
        return False
    return any(
        isinstance(label := data.get(key), str) and is_sensitive_key(label)
        for key in _PAIR_LABEL_KEYS
    )


class _BudgetSpent(Exception):
    pass


def _json_key(key: typing.Any) -> str:
    if isinstance(key, str):
        return key
    if key is True:
        return "true"
    if key is False:
        return "false"
    if key is None:
        return "null"
    if isinstance(key, (int, float)):
        return json.dumps(key)
    return str(key)


def _json_scalar(value: typing.Any) -> str:
    if isinstance(value, Secret):
        return json.dumps(MASK)
    try:
        return json.dumps(value)
    except TypeError, ValueError:
        return json.dumps(mask_text(str(value)))


def _json_default(value: typing.Any) -> typing.Any:
    if isinstance(value, Secret):
        return MASK
    if isinstance(value, (set, frozenset)):
        return list(value)
    return mask_text(str(value))


_WALKED = (Mapping, list, tuple, set, frozenset)


def _item_pairs(value: typing.Any) -> list[tuple[typing.Any, typing.Any]] | None:
    items = getattr(value, "items", None)
    if isinstance(value, (str, bytes)) or not callable(items):
        return None
    try:
        pairs = list(items())
    except TypeError, ValueError:
        return None
    if all(isinstance(pair, tuple) and len(pair) == 2 for pair in pairs):
        return pairs
    return None


def _is_secret_pair(
    value: typing.Any, in_sequence: bool
) -> typing.TypeGuard[tuple[typing.Any, ...] | list[typing.Any]]:
    return (
        (isinstance(value, tuple) or (in_sequence and isinstance(value, list)))
        and len(value) == 2
        and isinstance(value[0], str)
        and is_sensitive_key(value[0])
    )


def dump_masked(
    data: typing.Any, max_bytes: int | None = None, *, max_depth: int = 50
) -> str:
    limit = max_bytes or None
    if limit is None:
        try:
            return json.dumps(
                mask_data(data, max_depth=max_depth), default=_json_default
            )
        except TypeError, ValueError:
            pass
    parts: list[str] = []
    used = 0

    def write(chunk: str) -> None:
        nonlocal used
        parts.append(chunk)
        used += len(chunk)
        if limit is not None and used > limit:
            raise _BudgetSpent

    def emit(value: typing.Any, depth: int, *, in_sequence: bool = False) -> None:
        if isinstance(value, Secret):
            write(json.dumps(MASK))
            return
        if isinstance(value, str):
            window = None if limit is None else max(limit - used, 1)
            write(json.dumps(mask_text(value, window) if window else mask_text(value)))
            return
        if not isinstance(value, _WALKED) and (pairs := _item_pairs(value)) is not None:
            value = pairs
        if value and depth > max_depth:
            _logger.warning(
                "Redaction depth limit (%s) exceeded; the structure below it is "
                "dropped",
                max_depth,
            )
            write(json.dumps("***REDACTED_DEEP_NESTING***"))
            return
        if isinstance(value, Mapping):
            pair = _is_sensitive_pair(value)
            write("{")
            for index, (key, item) in enumerate(value.items()):
                if index:
                    write(", ")
                write(json.dumps(_json_key(key)))
                write(": ")
                if _masks(key, item) or (pair and key == "value"):
                    write(json.dumps(MASK))
                else:
                    emit(item, depth + 1)
            write("}")
            return
        if isinstance(value, (list, tuple, set, frozenset)):
            if _is_secret_pair(value, in_sequence):
                value = (value[0], MASK)
            write("[")
            for index, item in enumerate(value):
                if index:
                    write(", ")
                emit(item, depth + 1, in_sequence=True)
            write("]")
            return
        write(_json_scalar(value))

    try:
        emit(data, 0)
    except _BudgetSpent:
        return "".join(parts)[:limit]
    return "".join(parts)


def mask_data(data: typing.Any, *, max_depth: int = 50) -> typing.Any:
    return _mask_data(data, max_depth, 0, in_sequence=False)


def _mask_data(
    data: typing.Any, max_depth: int, depth: int, *, in_sequence: bool
) -> typing.Any:
    if isinstance(data, Secret):
        return MASK
    if isinstance(data, str):
        return mask_text(data)
    if not isinstance(data, _WALKED) and (pairs := _item_pairs(data)) is not None:
        data = pairs
    if not data:
        return data
    if depth > max_depth:
        _logger.warning(
            "Redaction depth limit (%s) exceeded; the structure below it is dropped",
            max_depth,
        )
        return "***REDACTED_DEEP_NESTING***"

    def walk(value: typing.Any) -> typing.Any:
        return _mask_data(value, max_depth, depth + 1, in_sequence=False)

    def walk_item(value: typing.Any) -> typing.Any:
        return _mask_data(value, max_depth, depth + 1, in_sequence=True)

    if isinstance(data, Mapping):
        pair = _is_sensitive_pair(data)
        return {
            key: (
                MASK if _masks(key, value) or (pair and key == "value") else walk(value)
            )
            for key, value in data.items()
        }
    if _is_secret_pair(data, in_sequence):
        masked = (mask_text(data[0]), MASK)
        return list(masked) if isinstance(data, list) else masked
    if isinstance(data, list):
        return [walk_item(item) for item in data]
    if isinstance(data, tuple):
        return tuple(walk_item(item) for item in data)
    if isinstance(data, (set, frozenset)):
        return type(data)(walk_item(item) for item in data)
    return data
