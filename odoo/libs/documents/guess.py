from __future__ import annotations

import codecs
import re

try:
    import chardet
except ImportError:
    chardet = None


__all__ = [
    "decode",
    "guess_encoding",
]
_ENCODING_CHUNK = 1 << 16

_ENCODING_SAMPLE_MAX = 1 << 16

_ENCODING_SAMPLE_LEAD = 1 << 10

# UTF-32 first: its little-endian mark begins with UTF-16's. Each codec
# reads the mark to learn its byte order and drops it from the text.
_WIDE_BYTE_ORDER_MARKS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

_NON_ASCII = re.compile(rb"[\x80-\xff]")


def _first_non_ascii(data: bytes) -> int:
    for start in range(0, len(data), _ENCODING_CHUNK):
        chunk = data[start : start + _ENCODING_CHUNK]
        if not chunk.isascii():
            match = _NON_ASCII.search(chunk)
            assert match is not None
            return start + match.start()
    return 0


def _decode(data: bytes, encoding: str, final: bool) -> str:
    if final:
        return data.decode(encoding)
    return codecs.getincrementaldecoder(encoding)().decode(data, final=False)


def _as_utf8(data: bytes, final: bool) -> str | None:
    try:
        return _decode(data, "utf-8-sig", final)
    except UnicodeDecodeError:
        return None


def _nul_share(data: bytes) -> float:
    return data.count(0) / len(data) if data else 0.0


def _marked_wide(data: bytes) -> str | None:
    for mark, encoding in _WIDE_BYTE_ORDER_MARKS:
        if data.startswith(mark):
            return encoding
    return None


def _wide_without_bom(data: bytes) -> str | None:
    # text in UTF-16 carries a NUL in every other byte for each Latin character;
    # text in an 8-bit encoding carries none, and UTF-32 NULs its even bytes too
    sample = data[:_ENCODING_CHUNK]
    if len(sample) < 4:
        return None
    even, odd = _nul_share(sample[0::2]), _nul_share(sample[1::2])
    if odd >= 0.9 and even <= 0.1:
        return "utf-16-le"
    if even >= 0.9 and odd <= 0.1:
        return "utf-16-be"
    return None


def _guess(data: bytes, final: bool) -> tuple[str | None, str | None]:
    # UTF-8 validates itself: a multibyte sequence that decodes strictly is
    # UTF-8 for any practical purpose, while chardet's probers, fed a short
    # Spanish sentence, answered johab. The text it decoded is kept.
    if marked := _marked_wide(data):
        return marked, None
    if data.isascii():
        # 7-bit data is ASCII unless it carries the escapes of ISO-2022 or the
        # NUL bytes of UTF-16/32 without a BOM
        if b"\x1b" not in data and b"\x00" not in data:
            return "ascii", None
    elif (text := _as_utf8(data, final)) is not None:
        return ("utf-8-sig" if data.startswith(codecs.BOM_UTF8) else "utf-8"), text
    if wide := _wide_without_bom(data):
        return wide, None
    if chardet is None:
        return None, None
    detector = chardet.UniversalDetector()
    # the probers learn nothing from plain ASCII, so the sample starts just
    # before the first byte that is not; an all-ASCII buffer (which may still
    # be ISO-2022 escapes) keeps the head window
    sample_start = max(0, _first_non_ascii(data) - _ENCODING_SAMPLE_LEAD)
    sample_end = min(len(data), sample_start + _ENCODING_SAMPLE_MAX)
    for start in range(sample_start, sample_end, _ENCODING_CHUNK):
        detector.feed(data[start : min(start + _ENCODING_CHUNK, sample_end)])
        if detector.done:
            break
    detector.close()
    encoding = detector.result["encoding"]
    if not encoding:
        return None, None
    encoding = encoding.lower()
    try:
        codecs.lookup(encoding)
    except LookupError:
        return None, None
    return encoding, None


def guess_encoding(data: bytes) -> str | None:
    return _guess(data, final=True)[0]


def decode(data: bytes, encoding: str = "", *, final: bool = True) -> str:
    if encoding:
        return _decode(data, encoding, final)
    name, text = _guess(data, final)
    if text is not None:
        return text
    if not name:
        raise UnicodeDecodeError(
            "undetermined", data, 0, len(data), "the encoding could not be guessed"
        )
    return _decode(data, name, final)


def is_text_like(text: str) -> bool:
    if not text:
        return False
    if "\x00" in text:
        return False
    control = sum(1 for c in text[:4096] if c < " " and c not in "\t\n\r\f\v")
    return control <= len(text[:4096]) // 20
