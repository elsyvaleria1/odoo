from __future__ import annotations

import re
from typing import Any, Protocol

__all__ = [
    "LocaleConventions",
    "format_number",
]


class LocaleConventions(Protocol):
    @property
    def decimal_point(self) -> str: ...

    @property
    def grouping(self) -> str: ...

    @property
    def thousands_sep(self) -> str: ...


_GROUP_SIZES = {"[3,0]": (3, 3), "[3,2,0]": (3, 2)}

_NUMBER_RE = re.compile(r"([^0-9]*)([^ ]*)(.*)")


def _group_sizes(grouping: str) -> tuple[int, int]:
    sizes = _GROUP_SIZES.get(grouping)
    if sizes is None:
        msg = f"a grouping is one of {', '.join(_GROUP_SIZES)}, got {grouping!r}"
        raise ValueError(msg)
    return sizes


def _group(number: str, sizes: tuple[int, int], separator: str) -> tuple[str, int]:
    matched = _NUMBER_RE.match(number)
    assert matched is not None, f"_NUMBER_RE failed on {number!r}"
    left, digits, right = matched.groups()
    first, rest = sizes
    if len(digits) <= first:
        return number, 0
    head, groups = digits[:-first], [digits[-first:]]
    while head:
        groups.append(head[-rest:])
        head = head[:-rest]
    return left + separator.join(reversed(groups)) + right, len(groups) - 1


_FLOATING = frozenset("eEfFgG")
_INTEGRAL = frozenset("diu")

_CONVERSION_RE = re.compile(
    r"%(?:%|[-+ #0']*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlL]?([diouxXeEfFgGcrsab]))"
)


def _get_conversion_match(spec: str) -> re.Match[str] | None:
    return next(
        (match for match in _CONVERSION_RE.finditer(spec) if match[1] is not None),
        None,
    )


def _strip_padding(number: str, amount: int) -> str:
    start = 0
    while amount and start < len(number) and number[start] == " ":
        start += 1
        amount -= 1
    stop = len(number)
    while amount and stop > start and number[stop - 1] == " ":
        stop -= 1
        amount -= 1
    return number[start:stop]


def format_number(
    spec: str,
    value: Any,
    lang_data: LocaleConventions,
    grouping: bool = False,
) -> str:
    if not spec or spec[0] != "%":
        raise ValueError(
            "format_number() must be given exactly one %char format specifier"
        )

    formatted: str = spec % value
    match = _get_conversion_match(spec)
    if match is None:
        return formatted
    conversion = match[1]

    head = spec[: match.start()] % ()
    tail = spec[match.end() :] % ()
    number = formatted[len(head) : len(formatted) - len(tail) or None]

    decimal_point = lang_data.decimal_point
    if grouping:
        lang_grouping, thousands_sep = (
            lang_data.grouping,
            lang_data.thousands_sep or "",
        )
        sizes = _group_sizes(lang_grouping)
        separators = 0

        if conversion in _FLOATING:
            parts = number.split(".")
            scientific = conversion in "eE" or (
                conversion in "gG" and ("e" in number or "E" in number)
            )
            if not scientific:
                parts[0], separators = _group(parts[0], sizes, thousands_sep)

            number = decimal_point.join(parts)

        elif conversion in _INTEGRAL:
            number, separators = _group(number, sizes, thousands_sep)

        number = _strip_padding(number, separators * len(thousands_sep))

    elif conversion in _FLOATING and "." in number:
        number = number.replace(".", decimal_point)

    return head + number + tail
