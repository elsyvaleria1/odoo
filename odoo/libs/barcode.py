import logging
import re
from threading import RLock
from typing import Any

from odoo.libs.debug_log import DebugLog

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

__all__ = [
    "createBarcodeDrawing",
    "get_barcode_check_digit",
    "get_barcode_font",
    "gs1_check_digit",
    "is_barcode_encoding_valid",
    "is_gtin_valid",
]
_barcode_init_lock: RLock = RLock()


_barcode_init: tuple[Any, str] | None = None

_COURIER = "Courier"
_SUBSTITUTE_FONT = "NimbusMonoPS-Regular"
_SUBSTITUTE_METRICS = {"ascent": 629, "descent": -157}
_UNSET = object()


def _init_barcode() -> tuple[Any, str]:
    global _barcode_init  # noqa: PLW0603 -- Updates process-wide state shared by callers of this module.
    with _barcode_init_lock:
        if _barcode_init is not None:
            return _barcode_init
        try:
            from reportlab.graphics import barcode

            font_name = _validated_font(barcode)
        except ImportError:
            _debug.lifecycle("barcode.init", available=False)
            raise
        _barcode_init = (barcode, font_name)
        _debug.lifecycle(
            "barcode.init",
            available=True,
            font=font_name,
            substituted=font_name != _COURIER,
        )
        return _barcode_init


def _validated_font(barcode: Any) -> str:
    from reportlab.pdfbase.pdfmetrics import TypeFace, getFont

    candidate = _COURIER
    font = None
    saved: dict[str, Any] = {}
    try:
        if not TypeFace(_COURIER).findT1File():
            candidate = _SUBSTITUTE_FONT
            font = getFont(candidate)
            saved = {name: vars(font).get(name, _UNSET) for name in _SUBSTITUTE_METRICS}
            vars(font).update(_SUBSTITUTE_METRICS)
        barcode.createBarcodeDrawing(
            "Code128",
            value="foo",
            format="png",
            width=100,
            height=100,
            humanReadable=1,
            fontName=candidate,
        ).asString("png")
    except Exception as error:
        for name, value in saved.items():
            if value is _UNSET:
                vars(font).pop(name, None)
            else:
                vars(font)[name] = value
        if isinstance(error, ImportError):
            raise
        _logger.warning(
            "Barcode font %r could not be validated%s.",
            candidate,
            "" if candidate == _COURIER else "; falling back to Courier",
            exc_info=True,
        )
        return _COURIER
    return candidate


def createBarcodeDrawing(codeName: str, **options: Any) -> Any:
    barcode, _font = _init_barcode()
    return barcode.createBarcodeDrawing(codeName, **options)


def get_barcode_font() -> str:
    _barcode, font = _init_barcode()
    return font


_ASCII_DIGITS_RE = re.compile(r"\A[0-9]+\Z")


def _require_digits(value: str, what: str) -> None:
    if not _ASCII_DIGITS_RE.match(value or ""):
        msg = f"{what} must be a non-empty string of ASCII digits, got {value!r}"
        raise ValueError(msg)


def _weighted_check_digit(data: str) -> int:
    total = sum(
        int(digit) * (3 if i % 2 == 0 else 1) for i, digit in enumerate(reversed(data))
    )
    return (10 - total % 10) % 10


def gs1_check_digit(data: str) -> int:
    _require_digits(data, "barcode data")
    return _weighted_check_digit(data)


def get_barcode_check_digit(numeric_barcode: str) -> int:
    _require_digits(numeric_barcode, "barcode")
    return _weighted_check_digit(numeric_barcode[:-1])


_BARCODE_SIZES = {
    "ean8": 8,
    "ean13": 13,
    "gtin14": 14,
    "upca": 12,
    "sscc": 18,
}


def is_gtin_valid(code: object, size: int) -> bool:
    return bool(
        isinstance(code, str)
        and len(code) == size
        and _ASCII_DIGITS_RE.match(code)
        and _weighted_check_digit(code[:-1]) == int(code[-1])
    )


def is_barcode_encoding_valid(barcode: object, encoding: object) -> bool:
    if not isinstance(barcode, str) or not isinstance(encoding, str):
        return False
    encoding = encoding.lower()
    if encoding == "any":
        return True
    barcode_size = _BARCODE_SIZES.get(encoding)
    if barcode_size is None:
        _debug.logic("barcode.encoding_unknown", encoding=encoding)
        return False
    valid = is_gtin_valid(barcode, barcode_size) and (
        encoding != "ean13" or barcode[0] != "0"
    )
    if not valid:
        _debug.logic(
            "barcode.invalid",
            encoding=encoding,
            length=len(barcode),
            expected=barcode_size,
            digits=bool(_ASCII_DIGITS_RE.match(barcode)),
        )
    return valid
