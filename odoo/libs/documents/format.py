from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from typing import Any

__all__ = [
    "ABSOLUTE",
    "LEAD",
    "PARENS",
    "SIGN_STYLES",
    "TRAIL",
    "from_bool",
    "from_date",
    "from_float",
    "from_value",
]

LEAD = "lead"
TRAIL = "trail"
PARENS = "parens"
ABSOLUTE = "absolute"

SIGN_STYLES = (LEAD, TRAIL, PARENS, ABSOLUTE)

_ISO_DATE = "%Y-%m-%d"
_ISO_DATETIME = "%Y-%m-%d %H:%M:%S"


def _group_digits(digits: str, thousand: str) -> str:
    if not thousand or len(digits) <= 3:
        return digits
    head = len(digits) % 3 or 3
    parts = [digits[:head]]
    parts += [digits[i : i + 3] for i in range(head, len(digits), 3)]
    return thousand.join(parts)


def from_float(
    value: float | str | Decimal,
    *,
    places: int = 2,
    thousand: str = "",
    decimal: str = ".",
    symbol: str = "",
    sign: str = LEAD,
    implied_point: bool = False,
) -> str:
    if sign not in SIGN_STYLES:
        raise ValueError(f"Unknown sign style {sign!r}; expected one of {SIGN_STYLES}")
    if places < 0:
        raise ValueError(f"places must not be negative, got {places}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"{value!r} is not a number") from e
    if not number.is_finite():
        raise ValueError(f"{value!r} has no finite value to write")

    # the default context holds 28 digits, fewer than a large amount carries
    with localcontext() as context:
        context.prec = max(context.prec, number.adjusted() + places + 2)
        number = number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)

    negative = number < 0
    digits = f"{number.copy_abs():.{places}f}"
    whole, _, fraction = digits.partition(".")

    if implied_point:
        body = f"{whole}{fraction}"
    else:
        body = _group_digits(whole, thousand)
        if fraction:
            body = f"{body}{decimal}{fraction}"
    if symbol:
        body = f"{symbol}{body}"

    if not negative or sign == ABSOLUTE:
        return body
    if sign == PARENS:
        return f"({body})"
    if sign == TRAIL:
        return f"{body}-"
    return f"-{body}"


def from_date(value: datetime.date | str, fmt: str = _ISO_DATE) -> str:
    if isinstance(value, str):
        if len(value) != 10:
            msg = f"{value!r} is not a valid date"
            raise ValueError(msg)
        value = datetime.date.fromisoformat(value)
    if isinstance(value, datetime.datetime):
        value = value.date()
    if not isinstance(value, datetime.date):
        raise ValueError(f"{value!r} is not a date")
    return value.strftime(fmt)


def _carried_places(value: float | Decimal) -> int:
    # the places a number carries: an int none, a float those of its shortest
    # repr, a Decimal its own exponent
    if isinstance(value, int):
        return 0
    number = Decimal(repr(value)) if isinstance(value, float) else value
    if not number.is_finite():
        return 0
    exponent = number.as_tuple().exponent
    assert isinstance(exponent, int)
    return max(0, -exponent)


def from_bool(value: object, true: str = "1", false: str = "0") -> str:
    return true if value else false


_NUMBER_OPTIONS = ("places", "thousand", "decimal", "symbol", "sign", "implied_point")
_OPTIONS = frozenset(
    (*_NUMBER_OPTIONS, "true", "false", "date_format", "datetime_format")
)


def from_value(value: object, **options: Any) -> str:
    if unknown := options.keys() - _OPTIONS:
        raise TypeError(
            f"from_value got unknown option(s) {', '.join(sorted(unknown))}"
        )
    if value is None:
        return ""
    if isinstance(value, bool):
        return from_bool(
            value,
            str(options.get("true", "1")),
            str(options.get("false", "0")),
        )
    if isinstance(value, datetime.datetime):
        return value.strftime(str(options.get("datetime_format", _ISO_DATETIME)))
    if isinstance(value, datetime.date):
        return from_date(value, str(options.get("date_format", _ISO_DATE)))
    if isinstance(value, (int, float, Decimal)):
        number = {name: options[name] for name in _NUMBER_OPTIONS if name in options}
        if "places" not in number:
            number["places"] = _carried_places(value)
        return from_float(value, **number)
    return str(value)
