import math
import re

__all__ = ["parse_amount", "split_amount_str"]

_SPACES = "\u0020\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000"
_GROUPINGS_RE = re.compile(f"[{_SPACES}'\u2019]")
_GROUPING_CLASSES = str.maketrans({**dict.fromkeys(_SPACES, " "), "\u2019": "'"})


def _is_solitary_group(int_part: str, distance: int, has_grouping: bool) -> bool:
    return (
        not has_grouping
        and distance == 3
        and int_part.isdecimal()
        and len(int_part) <= 3
        and int_part != "0"
    )


def _well_grouped(int_part: str, tsep: str) -> bool:
    first, *groups = int_part.split(tsep)
    if not groups:
        return True
    if not 1 <= len(first) <= 3 or len(groups[-1]) != 3:
        return False
    middle = {len(group) for group in groups[:-1]}
    return middle <= {3} or middle == {2}


def _strictly_grouped(text: str, tsep: str, dsep: str, groupings: set[str]) -> bool:
    separator = tsep
    if groupings:
        if len(groupings) > 1 or tsep in text:
            return False
        (separator,) = groupings
    int_end = text.rfind(dsep)
    if int_end < 0:
        int_end = len(text)
    return separator not in text[int_end:] and _well_grouped(text[:int_end], separator)


def _split(text: str, *, strict: bool = False) -> tuple[str, str] | None:
    text = text.strip()
    if not any(char.isdecimal() for char in text):
        return None
    groupings = set(_GROUPINGS_RE.findall(text))
    has_grouping = bool(groupings)
    amount_str = _GROUPINGS_RE.sub("", text)
    commas = amount_str.count(",")
    dots = amount_str.count(".")
    last_comma, last_dot = amount_str.rfind(","), amount_str.rfind(".")
    comma_distance = len(amount_str) - 1 - last_comma if last_comma >= 0 else -1
    dot_distance = len(amount_str) - 1 - last_dot if last_dot >= 0 else -1

    match (commas, dots):
        case (0, 0):
            tsep, dsep = ",", "."
        case (c, 0) if c > 1:
            tsep, dsep = ",", "."
        case (0, d) if d > 1:
            tsep, dsep = ".", ","
        case (c, 1) if c > 1:
            tsep, dsep = ",", "."
        case (1, d) if d > 1:
            tsep, dsep = ".", ","
        case (1, 1) if last_comma > last_dot:
            tsep, dsep = ".", ","
        case (1, 1):
            tsep, dsep = ",", "."
        case (0, 1) if _is_solitary_group(
            amount_str[:last_dot], dot_distance, has_grouping
        ):
            tsep, dsep = ".", ","
        case (0, 1):
            tsep, dsep = ",", "."
        case (1, 0) if _is_solitary_group(
            amount_str[:last_comma], comma_distance, has_grouping
        ):
            tsep, dsep = ",", "."
        case (1, 0):
            tsep, dsep = ".", ","
        case _:
            return None

    if strict and not _strictly_grouped(
        text.translate(_GROUPING_CLASSES),
        tsep,
        dsep,
        {char.translate(_GROUPING_CLASSES) for char in groupings},
    ):
        return None
    parts = amount_str.replace(tsep, "").split(dsep)
    if len(parts) > 2:
        return None
    int_part, dec_part = (parts + ["0"])[:2]
    int_part = int_part or "0"
    dec_part = dec_part or "0"
    if not int_part.isdecimal() or not dec_part.isdecimal():
        return None
    return (int_part, dec_part)


def split_amount_str(amount_str: str) -> tuple[str, str]:
    if not amount_str:
        return ("0", "0")
    return _split(amount_str) or ("0", "0")


def parse_amount(amount_str: str | None) -> float | None:
    if not amount_str:
        return None
    body = amount_str.replace("\u2212", "-").lstrip()
    sign = body[0] if body.startswith(("+", "-")) else ""
    parts = _split(body[len(sign) :].strip(), strict=True)
    if parts is None:
        return None
    value = float(f"{parts[0]}.{parts[1]}")
    if not math.isfinite(value):
        return None
    return -value if sign == "-" else value
