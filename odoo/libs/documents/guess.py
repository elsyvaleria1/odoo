from __future__ import annotations

import codecs
import functools
import re
from collections.abc import Callable, Iterable, Iterator

try:
    import chardet
except ImportError:
    chardet = None


__all__ = [
    "CharsetSniffer",
    "charset_candidates",
    "charset_label",
    "chunked",
    "decode",
    "guess_encoding",
    "sniff_charset",
]
_ENCODING_CHUNK = 1 << 16

_ENCODING_SAMPLE_MAX = 1 << 16

_ENCODING_SAMPLE_LEAD = 1 << 10

_WIDE_BYTE_ORDER_MARKS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

_NON_ASCII = re.compile(rb"[\x80-\xff]")

_ASCII_PROBE = bytes(range(0x20, 0x7F)) + b"\t\n\r"

_WEB_LABELS = {
    "utf-8-sig": "utf-8",
    "utf-16-le": "utf-16le",
    "utf-16-be": "utf-16be",
    "mac-roman": "macintosh",
    "cp866": "ibm866",
    "cp874": "windows-874",
    "cp932": "windows-31j",
    "big5hkscs": "big5-hkscs",
    "iso2022_jp": "iso-2022-jp",
}


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
    if marked := _marked_wide(data):
        return marked, None
    if data.isascii():
        if b"\x1b" not in data and b"\x00" not in data:
            return "ascii", None
    elif (text := _as_utf8(data, final)) is not None:
        return ("utf-8-sig" if data.startswith(codecs.BOM_UTF8) else "utf-8"), text
    if wide := _wide_without_bom(data):
        return wide, None
    if chardet is None:
        return None, None
    detector = chardet.UniversalDetector()
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


def _is_ascii_compatible(encoding: str) -> bool:
    try:
        return _ASCII_PROBE.decode(encoding) == _ASCII_PROBE.decode("ascii")
    except LookupError, UnicodeDecodeError:
        return False


def charset_candidates(declared: str | None) -> tuple[str, ...]:
    if not declared:
        return ("utf-8",)
    if _is_ascii_compatible(declared):
        return ("utf-8", declared)
    return (declared, "utf-8")


def charset_label(encoding: str) -> str | None:
    try:
        codec = codecs.lookup(encoding).name
    except LookupError:
        return None
    if label := _WEB_LABELS.get(codec):
        return label
    if codec.startswith("iso8859-"):
        return f"iso-{codec[3:]}"
    if re.fullmatch(r"cp125\d", codec):
        return f"windows-{codec[2:]}"
    return codec.replace("_", "-")


def guess_encoding(data: bytes) -> str | None:
    return _guess(data, final=True)[0]


def chunked(
    data: bytes | memoryview, size: int = _ENCODING_CHUNK
) -> Iterator[memoryview]:
    view = memoryview(data)
    for start in range(0, len(view), size):
        yield view[start : start + size]


def _decodes(decoder: codecs.IncrementalDecoder, data: bytes | memoryview) -> bool:
    try:
        decoder.decode(data)
    except UnicodeDecodeError:
        return False
    return True


def _closes(decoder: codecs.IncrementalDecoder) -> bool:
    try:
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return False
    return True


def _incremental_decoder(encoding: str) -> codecs.IncrementalDecoder | None:
    try:
        return codecs.getincrementaldecoder(encoding)()
    except LookupError:
        return None


_ASCII_BYTES = bytes(range(0x80))

_WIDE_WITHOUT_BOM = frozenset({"utf-16-le", "utf-16-be"})


def _skips_ascii_prefix(encoding: str) -> bool:
    if encoding in _WIDE_WITHOUT_BOM:
        return True
    try:
        return _ASCII_BYTES.decode(encoding) == _ASCII_BYTES.decode("ascii")
    except LookupError, UnicodeDecodeError:
        return False


class CharsetSniffer:
    def __init__(self, declared: str | None = None) -> None:
        self._candidates = [
            (candidate, decoder)
            for candidate in charset_candidates(declared)
            if (decoder := _incremental_decoder(candidate))
        ]
        self._block = bytearray()
        self._offset = 0
        self._sample_offset = 0
        self.sample = b""
        self._guessed = False
        self._guess: tuple[str, codecs.IncrementalDecoder] | None = None
        self.decided = True

    def feed(self, data: bytes | memoryview) -> None:
        for piece in chunked(data):
            self._candidates = [
                (name, decoder)
                for name, decoder in self._candidates
                if _decodes(decoder, piece)
            ]
            if self._guess and not _decodes(self._guess[1], piece):
                self._guess = None
            if not self.sample:
                rest = self._take_sample(piece)
                if self.sample and not self._candidates:
                    self._start_guess(rest)
            self._offset += len(piece)

    def _take_sample(self, piece: memoryview) -> memoryview:
        offset = self._offset
        while piece:
            taken = piece[: _ENCODING_CHUNK - len(self._block)]
            self._block += taken
            piece = piece[len(taken) :]
            offset += len(taken)
            if len(self._block) < _ENCODING_CHUNK:
                break
            if not self._block.isascii():
                self._capture_sample(offset - len(self._block))
                break
            self._block.clear()
        return piece

    def _capture_sample(self, offset: int) -> None:
        self.sample = bytes(self._block)
        self._sample_offset = offset
        self._block = bytearray()

    @functools.cached_property
    def _guessed_encoding(self) -> str | None:
        return guess_encoding(self.sample)

    def _start_guess(self, rest: bytes | memoryview) -> None:
        guessed = self._guessed_encoding
        if self._sample_offset and guessed and not _skips_ascii_prefix(guessed):
            return
        self._guessed = True
        decoder = _incremental_decoder(guessed) if guessed else None
        if guessed and decoder and _decodes(decoder, self.sample):
            if _decodes(decoder, rest):
                self._guess = (guessed, decoder)

    def close(self) -> str | None:
        sampled_now = not self.sample and not self._block.isascii()
        if sampled_now:
            self._capture_sample(self._offset - len(self._block))
        self._block = bytearray()
        for name, decoder in self._candidates:
            if _closes(decoder):
                return name
        if sampled_now:
            self._start_guess(b"")
        if self._guessed:
            guess = self._guess
            return charset_label(guess[0]) if guess and _closes(guess[1]) else None
        self.decided = not self.sample
        return None

    def recheck(self, chunks: Iterable[bytes | memoryview]) -> str | None:
        guessed = self._guessed_encoding
        decoder = _incremental_decoder(guessed) if guessed else None
        if not guessed or decoder is None:
            return None
        if not all(_decodes(decoder, chunk) for chunk in chunks):
            return None
        return charset_label(guessed) if _closes(decoder) else None


def sniff_charset(
    read: Callable[[], Iterable[bytes | memoryview]], declared: str | None = None
) -> str | None:
    sniffer = CharsetSniffer(declared)
    for chunk in read():
        sniffer.feed(chunk)
    charset = sniffer.close()
    return charset if sniffer.decided else sniffer.recheck(read())


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
