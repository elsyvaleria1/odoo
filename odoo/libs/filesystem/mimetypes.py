import codecs
import logging
import mimetypes
import re
import struct
import zipfile
from collections.abc import Callable, Iterator
from typing import Literal, NamedTuple

from odoo.libs.debug_log import DebugLog
from odoo.libs.json import loads as json_loads

_utf8_incremental_decoder = codecs.getincrementaldecoder("utf-8")

__all__ = [
    "MIMETYPE_HEAD_SIZE",
    "OLECF_MIMETYPES",
    "UNKNOWN_MIMETYPE",
    "UNSPECIFIC_MIMETYPES",
    "fix_filename_extension",
    "get_essential_mimetype",
    "get_extension",
    "guess_mimetype",
    "is_svg",
    "opens_on_markup",
]

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)
_logger_guess_mimetype = _logger.getChild("guess_mimetype")
MIMETYPE_HEAD_SIZE = 2048
UNKNOWN_MIMETYPE = "application/octet-stream"
_XML_MIMETYPE = "application/xml"


_OOXML_CONTENT_TYPES = b"[Content_Types].xml"
_OOXML_DIRS = (
    (
        b"word/",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    (
        b"ppt/",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    (b"xl/", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
)


_ZIP_LOCAL_HEADER = struct.Struct("<4sHHHHHIIIHH")
_ZIP_LOCAL_SIGNATURE = b"PK\x03\x04"
_ZIP_SIZES_FOLLOW_DATA = 0x08


class _ZipLocalEntry(NamedTuple):
    name: bytes
    compression: int
    start: int
    size: int


def _zip_local_entries(data: bytes) -> Iterator[_ZipLocalEntry]:
    # the local headers in archive order: all a caller holding only the head
    # of a file can read, the central directory being at its end
    offset = 0
    end = len(data) - _ZIP_LOCAL_HEADER.size
    while offset <= end and data.startswith(_ZIP_LOCAL_SIGNATURE, offset):
        (_, _, flags, compression, _, _, _, size, _, name_length, extra_length) = (
            _ZIP_LOCAL_HEADER.unpack_from(data, offset)
        )
        name_start = offset + _ZIP_LOCAL_HEADER.size
        start = name_start + name_length + extra_length
        yield _ZipLocalEntry(
            data[name_start : name_start + name_length], compression, start, size
        )
        if flags & _ZIP_SIZES_FOLLOW_DATA and not size:
            offset = data.find(_ZIP_LOCAL_SIGNATURE, start)
            if offset < 0:
                return
        else:
            offset = start + size


_ZIP_END = struct.Struct("<4s4H2LH")
_ZIP_END_SIGNATURE = b"PK\x05\x06"
_ZIP_END_SEARCH = _ZIP_END.size + 0xFFFF
_ZIP64_LOCATOR = struct.Struct("<4sLQL")
_ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
_ZIP64_END = struct.Struct("<4sQ2H2L4Q")
_ZIP64_END_SIGNATURE = b"PK\x06\x06"
_ZIP_CENTRAL_SIZE = 46
_ZIP_CENTRAL_LENGTHS = struct.Struct("<3H")
_ZIP_CENTRAL_LENGTHS_OFFSET = 28
_ZIP_CENTRAL_SIGNATURE = b"PK\x01\x02"


def _zip_central_directory(data: bytes) -> tuple[int, int] | None:
    # where the central directory starts and how many entries it lists,
    # measured back from the end record, so data prepended to the archive
    # moves nothing
    end = data.rfind(_ZIP_END_SIGNATURE, max(len(data) - _ZIP_END_SEARCH, 0))
    if end < 0 or end + _ZIP_END.size > len(data):
        return None
    _, _, _, _, count, size, _, _ = _ZIP_END.unpack_from(data, end)
    locator = end - _ZIP64_LOCATOR.size
    record = locator - _ZIP64_END.size
    if (
        record >= 0
        and data.startswith(_ZIP64_LOCATOR_SIGNATURE, locator)
        and data.startswith(_ZIP64_END_SIGNATURE, record)
    ):
        *_, count, size, _ = _ZIP64_END.unpack_from(data, record)
    else:
        record = end
    start = record - size
    if start < 0 or (count and not data.startswith(_ZIP_CENTRAL_SIGNATURE, start)):
        return None
    return start, count


def _zip_central_names(data: bytes, position: int, count: int) -> Iterator[bytes]:
    for _ in range(count):
        if position + _ZIP_CENTRAL_SIZE > len(data) or not data.startswith(
            _ZIP_CENTRAL_SIGNATURE, position
        ):
            return
        name_length, extra_length, comment_length = _ZIP_CENTRAL_LENGTHS.unpack_from(
            data, position + _ZIP_CENTRAL_LENGTHS_OFFSET
        )
        name_start = position + _ZIP_CENTRAL_SIZE
        yield data[name_start : name_start + name_length]
        position = name_start + name_length + extra_length + comment_length


def _zip_names(data: bytes) -> Iterator[bytes]:
    # the central directory when the data reaches the end of the archive,
    # else the local headers its head holds
    if (directory := _zip_central_directory(data)) is None:
        return (entry.name for entry in _zip_local_entries(data))
    return _zip_central_names(data, *directory)


def _get_ooxml_mimetype(data: bytes) -> str | None:
    # the first part directory in archive order names the document, so the
    # scan ends on the entries every Office writer puts first
    typed = False
    mimetype: str | None = None
    for name in _zip_names(data):
        if name == _OOXML_CONTENT_TYPES:
            typed = True
        elif not mimetype:
            mimetype = next(
                (mime for dirname, mime in _OOXML_DIRS if name.startswith(dirname)),
                None,
            )
        if typed and mimetype:
            return mimetype
    return None


_OPEN_CONTAINER_MIMETYPE = re.compile(
    rb"application/(?:vnd\.oasis\.opendocument\.[a-z-]+(?:\.[a-z-]+)*|epub\+zip)"
)


def _get_open_container_mimetype(data: bytes) -> str | None:
    # ODF and EPUB store their type uncompressed as the first entry; a
    # "mimetype" entry anywhere else, or naming another type, is only a zip
    # saying what it wants to be served as
    first = next(_zip_local_entries(data), None)
    if (
        first is None
        or first.name != b"mimetype"
        or first.compression != zipfile.ZIP_STORED
    ):
        return None
    declared = data[first.start : first.start + min(first.size, 256)]
    if _OPEN_CONTAINER_MIMETYPE.fullmatch(declared):
        return declared.decode("ascii")
    return None


_old_ms_office_mimetypes = {
    ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel",
    ".ppt": "application/vnd.ms-powerpoint",
}
OLECF_MIMETYPES = ("application/x-ole-storage", "application/CDFV2")

_olecf_streams = (
    ("WordDocument".encode("utf-16-le"), "application/msword"),
    ("Workbook".encode("utf-16-le"), "application/vnd.ms-excel"),
    ("Book".encode("utf-16-le"), "application/vnd.ms-excel"),
    ("PowerPoint Document".encode("utf-16-le"), "application/vnd.ms-powerpoint"),
)
_ppt_pattern = re.compile(
    rb"""
    \x00\x6e\x1e\xf0
  | \x0f\x00\xe8\x03
  | \xa0\x46\x1d\xf0
  | \xfd\xff\xff\xff(\x0e|\x1c|\x43)\x00\x00\x00
""",
    re.VERBOSE,
)


_OLECF_SCAN_LIMIT = 1 << 16
_OLECF_DIRECTORY_ENTRY = struct.Struct("<64sHBxIII")
_OLECF_DIRECTORY_ENTRY_SIZE = 128
_OLECF_DIRECTORY_SECTORS = 64
_OLECF_ROOT, _OLECF_STREAM = 5, 2
_OLECF_LAST_SECTOR = 0xFFFFFFFA


class _OlecfEntry(NamedTuple):
    name: bytes
    kind: int
    left: int
    right: int
    child: int


def _olecf_directory(data: bytes) -> Iterator[_OlecfEntry]:
    # the directory sectors the data holds, by the header's FAT chain: a
    # caller holding only the head of a large file may reach none
    if len(data) < 0x200:
        return
    shift = int.from_bytes(data[0x1E:0x20], "little")
    if shift not in (9, 12):
        return
    size = 1 << shift
    fat_sectors = struct.unpack_from("<109I", data, 0x4C)
    sector = int.from_bytes(data[0x30:0x34], "little")
    for _ in range(_OLECF_DIRECTORY_SECTORS):
        start = (sector + 1) * size
        if sector >= _OLECF_LAST_SECTOR or start + size > len(data):
            return
        for offset in range(start, start + size, _OLECF_DIRECTORY_ENTRY_SIZE):
            name, length, kind, left, right, child = _OLECF_DIRECTORY_ENTRY.unpack_from(
                data, offset
            )
            yield _OlecfEntry(name[: max(length - 2, 0)], kind, left, right, child)
        fat_index, slot = divmod(sector, size // 4)
        if fat_index >= len(fat_sectors):
            return
        position = (fat_sectors[fat_index] + 1) * size + slot * 4
        if fat_sectors[fat_index] >= _OLECF_LAST_SECTOR or position + 4 > len(data):
            return
        sector = int.from_bytes(data[position : position + 4], "little")


def _olecf_root_streams(data: bytes) -> set[bytes]:
    # only the root storage's own streams: a document embedding another
    # keeps the embedded one's streams under a storage of its own
    entries = list(_olecf_directory(data))
    if not entries or entries[0].kind != _OLECF_ROOT:
        return set()
    streams: set[bytes] = set()
    seen: set[int] = set()
    pending = [entries[0].child]
    while pending:
        index = pending.pop()
        if index >= len(entries) or index in seen:
            continue
        seen.add(index)
        entry = entries[index]
        if entry.kind == _OLECF_STREAM:
            streams.add(entry.name)
        pending += (entry.left, entry.right)
    return streams


def _get_olecf_mimetype(data: bytes) -> str | None:
    streams = _olecf_root_streams(data)
    for stream, mimetype in _olecf_streams:
        if stream in streams:
            return mimetype
    offset = 0x200
    head = data[:_OLECF_SCAN_LIMIT]
    if data.startswith(b"\xec\xa5\xc1\x00", offset):
        return "application/msword"
    if _ppt_pattern.match(data, offset):
        return "application/vnd.ms-powerpoint"
    for stream, mimetype in _olecf_streams:
        if stream in head:
            return mimetype
    if b"Microsoft Excel" in head:
        return "application/vnd.ms-excel"
    return None


def _get_webp_mimetype(data: bytes) -> str | None:
    if data[8:15] == b"WEBPVP8":
        return "image/webp"
    return None


_BMP_DIB_HEADER_SIZES = frozenset({12, 40, 52, 56, 64, 108, 124})


def _get_bmp_mimetype(data: bytes) -> str | None:
    # "BM" alone opens any text starting with those letters
    if len(data) >= 18 and data[6:10] == b"\0\0\0\0":
        if int.from_bytes(data[14:18], "little") in _BMP_DIB_HEADER_SIZES:
            return "image/bmp"
    return None


_MARKUP_START = re.compile(
    rb"<(?:\?xml|!--|!DOCTYPE|[A-Za-z_][\w.:-]*[\s/>])", re.IGNORECASE
)
_HTML_START = re.compile(rb"<(?:!DOCTYPE\s+html|html[\s>])", re.IGNORECASE)
# the root element, past the prolog; each loop is possessive and each
# alternative unambiguous, so a prolog that never closes is read once, and
# each loop is unrolled around a character class, which the engine runs
# without stepping a group per byte. A doctype is read token by token, its
# literals and the declarations of its subset quoting "]" and ">" freely;
# past the literals it is as lenient as a sloppy editor, which the parser
# is not
_SVG_ROOT = re.compile(
    rb"""
    (?:
        \s++
      | <\?[^?]*+(?:\?(?!>)[^?]*+)*+\?>
      | <!--[^-]*+(?:-(?!->)[^-]*+)*+-->
      | <!DOCTYPE
        [^\[>"']*+(?:(?:"[^"]*+"|'[^']*+')[^\[>"']*+)*+
        (?:
            \[
            [^\]"'<]*+
            (?:
                (?:
                    "[^"]*+"
                  | '[^']*+'
                  | <!--[^-]*+(?:-(?!->)[^-]*+)*+-->
                  | <\?[^?]*+(?:\?(?!>)[^?]*+)*+\?>
                  | <[^>"']*+(?:(?:"[^"]*+"|'[^']*+')[^>"']*+)*+>
                )
                [^\]"'<]*+
            )*+
            \]
            [^>]*+
        )?
        >
    )*+
    <(?:[\w.-]+:)?svg[\s/>]
    """,
    re.VERBOSE,
)
# UTF-32 before UTF-16: the UTF-32-LE mark opens on the UTF-16-LE one
_WIDE_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
_MARKUP_LEADING_SPACE = b"\t\n\x0b\x0c\r "
_LEADING_SPACE = re.compile(rb"[\t\n\x0b\x0c\r ]*+")
_OPENS_ON_MARKUP = re.compile(rb"\s*+(?:<|\Z)")
# the parser reads all it is fed: a window growing from a few lines finds a
# root near the top cheaply, and a long prolog in few feeds
_MARKUP_FIRST_WINDOW = 1 << 8
_MARKUP_LAST_WINDOW = 1 << 16
# libxml2 builds every attribute of a start tag before it reports the tag, at
# some thirty bytes of memory per byte of tag: the parser is fed this much of
# the markup and no more, which no image's prolog outgrows
_SVG_ROOT_BUDGET = 1 << 18


def _utf8_bom_length(data: bytes) -> int:
    return len(codecs.BOM_UTF8) if data.startswith(codecs.BOM_UTF8) else 0


def _wide_bom(data: bytes, start: int = 0) -> tuple[bytes, str] | None:
    for bom, encoding in _WIDE_BOMS:
        if data.startswith(bom, start):
            return bom, encoding
    return None


def opens_on_markup(head: bytes) -> bool:
    start = _utf8_bom_length(head)
    return (
        _wide_bom(head, start) is not None
        or _OPENS_ON_MARKUP.match(head, start) is not None
    )


def _markup_start(data: bytes) -> tuple[int, str]:
    # where the markup begins, past its byte order marks and, in UTF-8, the
    # space before it, so a budget counts markup only
    start = _utf8_bom_length(data)
    if wide := _wide_bom(data, start):
        return start + len(wide[0]), wide[1]
    match = _LEADING_SPACE.match(data, start)
    return (start if match is None else match.end()), "utf-8"


def _markup_text(data: bytes, start: int, encoding: str) -> Iterator[str]:
    # decoded a window at a time, so the parse reading it stops a text that
    # is no markup at its first window rather than after decoding all of it
    decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
    leading = True
    offset, window = start, _MARKUP_FIRST_WINDOW
    while offset < len(data):
        text = decoder.decode(data[offset : offset + window])
        offset += window
        window = min(window * 2, _MARKUP_LAST_WINDOW)
        if leading:
            text = text.lstrip(_MARKUP_LEADING_SPACE.decode())
            leading = not text
        if text:
            yield text


def _root_tag(data: bytes) -> str | Literal[False] | None:
    # the root element's tag; False when the markup breaks or ends before a
    # root, None when the budget runs out before one begins
    from lxml import etree

    start, encoding = _markup_start(data)
    end = start + _SVG_ROOT_BUDGET
    parser = etree.XMLPullParser(
        events=("start",), resolve_entities=False, no_network=True
    )
    try:
        for chunk in _markup_text(data[:end], start, encoding):
            parser.feed(chunk)
            if (event := next(parser.read_events(), None)) is not None:
                return event[1].tag
    except etree.XMLSyntaxError:
        # an error past the root's start tag, in the window that held it
        event = next(parser.read_events(), None)
        return False if event is None else event[1].tag
    return None if len(data) > end else False


def _is_svg_tag(tag: str | Literal[False] | None) -> bool:
    return isinstance(tag, str) and tag.rpartition("}")[2].rpartition(":")[2] == "svg"


def _svg_by_prolog(data: bytes) -> bool:
    # a UTF-8 source is read whole, the grammar being linear; a wide one is
    # decoded only as far as the parser reads, and a prolog the parser
    # refuses past that is no svg a browser renders
    start, encoding = _markup_start(data)
    if encoding != "utf-8":
        window = data[start : start + _SVG_ROOT_BUDGET]
        data, start = window.decode(encoding, errors="replace").encode(), 0
    return _SVG_ROOT.match(data, start) is not None


def _svg_verdict(data: bytes) -> bool | None:
    # what either the prolog grammar or the parser roots in an svg is one: a
    # browser renders what the parser reads, and an SVG a sloppy editor wrote
    # is still meant as an image. None: the parser's budget ran out before
    # the root began, and only the caller knows which answer is safe
    if not opens_on_markup(data):
        return False
    if _svg_by_prolog(data):
        return True
    tag = _root_tag(data)
    return None if tag is None else _is_svg_tag(tag)


def is_svg(data: bytes, *, undecided: bool = False) -> bool:
    verdict = _svg_verdict(data)
    return undecided if verdict is None else verdict


def _markup_heads(data: bytes) -> tuple[bytes, bytes]:
    # the head the byte patterns read, decoded out of UTF-16 and UTF-32, and
    # the head the XML parser reads, still in the encoding its declaration
    # names
    start = _utf8_bom_length(data)
    data = data[start : start + MIMETYPE_HEAD_SIZE]
    if wide := _wide_bom(data):
        bom, encoding = wide
        decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        text = decoder.decode(data[len(bom) :], final=False)
        return text.encode().lstrip(_MARKUP_LEADING_SPACE), data
    data = data.lstrip(_MARKUP_LEADING_SPACE)
    return data, data


_XML_PROLOG = re.compile(rb"<(?:\?xml|!DOCTYPE)\s")


def _is_xml(head: bytes, *, complete: bool, prolog: bool) -> bool:
    from lxml import etree

    parser = etree.XMLPullParser(
        events=("start", "end", "start-ns"), resolve_entities=False, no_network=True
    )
    try:
        parser.feed(head)
        if complete:
            parser.close()
    except Exception:
        return False
    events = {event for event, _element in parser.read_events()}
    if complete:
        return "start" in events
    # an unclosed start tag is a valid prefix of XML and of "<alice> hi"
    # alike: a cut head is XML only on what prose does not write
    return prolog or not events.isdisjoint(("end", "start-ns"))


def _get_markup_mimetype(data: bytes) -> str | None:
    # a head is judged as a prefix, so a caller holding only the head and one
    # holding the whole file get one answer; only a shorter input is known
    # to end where it ends
    head, xml_head = _markup_heads(data)
    complete = len(data) < MIMETYPE_HEAD_SIZE
    if _HTML_START.match(head):
        return "text/html"
    if _SVG_ROOT.match(head) or (
        head.startswith(b"<") and _is_svg_tag(_root_tag(xml_head))
    ):
        return "image/svg+xml"
    if _MARKUP_START.match(head) and _is_xml(
        xml_head, complete=complete, prolog=_XML_PROLOG.match(head) is not None
    ):
        return _XML_MIMETYPE
    return None


class _Entry(NamedTuple):
    mimetype: str
    signatures: list[bytes]
    discriminants: list[Callable[[bytes], str | bool | None]]
    # False when the signature is too weak to name the type by itself: an entry
    # none of whose discriminants answers leaves the data to later entries
    decisive: bool = True


_mime_mappings = (
    _Entry("application/pdf", [b"%PDF"], []),
    _Entry("image/jpeg", [b"\xff\xd8\xff"], []),
    _Entry("image/png", [b"\x89PNG\r\n\x1a\n"], []),
    _Entry("image/gif", [b"GIF87a", b"GIF89a"], []),
    _Entry("image/bmp", [b"BM"], [_get_bmp_mimetype], decisive=False),
    _Entry("image/x-icon", [b"\x00\x00\x01\x00"], []),
    _Entry("image/webp", [b"RIFF"], [_get_webp_mimetype], decisive=False),
    _Entry(
        "application/msword",
        [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", b"\x0d\x44\x4f\x43"],
        [_get_olecf_mimetype],
    ),
    _Entry(
        "application/zip",
        [b"PK\x03\x04"],
        [_get_ooxml_mimetype, _get_open_container_mimetype],
    ),
)


def _guess_mimetype_by_signature(data: bytes, default: str = UNKNOWN_MIMETYPE) -> str:
    bin_data = data.removeprefix(codecs.BOM_UTF8)
    for entry in _mime_mappings:
        for signature in entry.signatures:
            if bin_data.startswith(signature):
                for discriminant in entry.discriminants:
                    try:
                        guess = discriminant(bin_data)
                        if isinstance(guess, str):
                            return guess
                    except Exception:
                        _logger_guess_mimetype.warning(
                            "Sub-checker '%s' of type '%s' failed",
                            discriminant.__name__,
                            entry.mimetype,
                            exc_info=True,
                        )
                if entry.decisive:
                    return entry.mimetype
    if markup := _get_markup_mimetype(data):
        return markup
    head = _text_head(bin_data)
    if head is None:
        return default
    if head and all(c >= " " or c in "\t\n\r" for c in head):
        return "text/plain"
    return default


def _text_head(data: bytes) -> str | None:
    if wide := _wide_bom(data):
        bom, encoding = wide
        decoder = codecs.getincrementaldecoder(encoding)()
        try:
            return decoder.decode(data[len(bom) : 2048], final=False)
        except ValueError:
            return None
    try:
        return _utf8_incremental_decoder().decode(data[:1024], final=False)
    except ValueError:
        return None


try:
    import magic
except ImportError:
    magic = None


UNSPECIFIC_MIMETYPES = frozenset(
    {"", UNKNOWN_MIMETYPE, "text/plain", "application/x-empty", "binary/octet-stream"}
)


def get_essential_mimetype(mimetype: str) -> str:
    return mimetype.split(";", 1)[0].strip().lower()


_JSON_TOKEN = re.compile(
    r"""
    [\ \t\n\r]*+
    (?:
        (?P<open>[{\[])
      | (?P<close>[}\]])
      | (?P<colon>:)
      | (?P<comma>,)
      | (?P<string>"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*+")
      | (?P<scalar>
            -?(?:0|[1-9][0-9]*+)(?:\.[0-9]++)?(?:[eE][+-]?[0-9]++)?(?![0-9.eE+-])
          | true|false|null
        )
    )
    """,
    re.VERBOSE,
)
_JSON_PARTIAL_STRING = re.compile(
    r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*+'
    r"(?:\\(?:u[0-9a-fA-F]{0,3})?)?"
)
_JSON_PARTIAL_SCALAR = re.compile(
    r"-|-?(?:0|[1-9][0-9]*+)(?:\.[0-9]*+)?(?:[eE][+-]?[0-9]*+)?"
    r"|t(?:ru?)?|f(?:a(?:ls?)?)?|n(?:ul?)?"
)
_JSON_CLOSES = {"{": "}", "[": "]"}


def _is_json_prefix(text: str) -> bool:
    # a hand-walked grammar, since the stdlib parses only a whole document:
    # every token must be where JSON allows it, and the last may be cut
    stack: list[str] = []
    expect = "value"
    position = 0
    while True:
        token = _JSON_TOKEN.match(text, position)
        if token is None:
            tail = text[position:].lstrip(" \t\n\r")
            if not tail:
                return bool(stack) or expect == "end"
            if expect in ("key", "first_key"):
                return _JSON_PARTIAL_STRING.fullmatch(tail) is not None
            return expect in ("value", "first_value") and bool(
                _JSON_PARTIAL_STRING.fullmatch(tail)
                or _JSON_PARTIAL_SCALAR.fullmatch(tail)
            )
        kind = token.lastgroup
        lexeme = token[kind or 0]
        position = token.end()
        if kind == "open" and expect in ("value", "first_value"):
            stack.append(lexeme)
            expect = "first_key" if lexeme == "{" else "first_value"
        elif (
            kind == "close"
            and stack
            and _JSON_CLOSES[stack[-1]] == lexeme
            and (
                expect == "next"
                or (expect == "first_key" and lexeme == "}")
                or (expect == "first_value" and lexeme == "]")
            )
        ):
            stack.pop()
            expect = "next" if stack else "end"
        elif kind == "colon" and expect == "colon":
            expect = "value"
        elif kind == "comma" and expect == "next":
            expect = "key" if stack[-1] == "{" else "value"
        elif kind == "string" and expect in ("key", "first_key"):
            expect = "colon"
        elif kind in ("string", "scalar") and expect in ("value", "first_value"):
            if not stack:
                return False
            expect = "next"
        else:
            return False


def _is_json(head: bytes, *, complete: bool) -> bool:
    if complete:
        try:
            json_loads(head)
        except Exception:
            return False
        return True
    try:
        text = _utf8_incremental_decoder().decode(head, final=False)
    except ValueError:
        return False
    return _is_json_prefix(text)


def _resolve_json_mimetype(data: bytes) -> str | None:
    head = data[:MIMETYPE_HEAD_SIZE]
    if head.lstrip()[:1] in (b"{", b"[") and _is_json(
        head, complete=len(data) < MIMETYPE_HEAD_SIZE
    ):
        return "application/json"
    return None


def guess_mimetype(
    bin_data: bytes | bytearray,
    default: str = UNKNOWN_MIMETYPE,
    *,
    declared: str = "",
) -> str:
    if isinstance(bin_data, bytearray):
        bin_data = bytes(bin_data)
    elif not isinstance(bin_data, bytes):
        msg = "`bin_data` must be bytes or bytearray"
        raise TypeError(msg)
    declared = (declared or "").lower()
    if declared and declared not in UNSPECIFIC_MIMETYPES:
        _debug.logic("mimetype.guessed", source="declared", mimetype=declared)
        return declared
    mimetype = _probe_mimetype(bin_data, default)
    if mimetype.lower() not in UNSPECIFIC_MIMETYPES:
        _debug.logic(
            "mimetype.guessed",
            source="probe",
            mimetype=mimetype,
            declared=declared or None,
            size=len(bin_data),
        )
        return mimetype
    resolved = _resolve_json_mimetype(bin_data)
    _debug.logic(
        "mimetype.guessed",
        source="json" if resolved else "fallback",
        mimetype=resolved or mimetype,
        probed=mimetype,
        declared=declared or None,
        size=len(bin_data),
    )
    return resolved or mimetype


# libmagic says only "text" or "XML" for markup it does not place (a leading
# newline, UTF-16), and "text/xml" where the signature table says the RFC 7303
# name: its answer is refined by the same markup sniff
_MAGIC_GENERIC_TEXT = frozenset({"text/plain", "text/xml", _XML_MIMETYPE})


def _probe_mimetype(bin_data: bytes, default: str) -> str:
    if magic is None:
        return _probe_mimetype_by_signature(bin_data, default)
    mimetype = magic.from_buffer(bin_data[:MIMETYPE_HEAD_SIZE], mime=True)
    if mimetype in _MAGIC_GENERIC_TEXT:
        mimetype = _get_markup_mimetype(bin_data) or mimetype
        if mimetype == "text/xml":
            mimetype = _XML_MIMETYPE
    if mimetype == UNKNOWN_MIMETYPE:
        return _probe_mimetype_by_signature(bin_data, default)
    # the signature table runs these as discriminants already: only a
    # container libmagic named is opened here
    if mimetype in OLECF_MIMETYPES:
        try:
            if msoffice_mimetype := _get_olecf_mimetype(bin_data):
                return msoffice_mimetype
        except Exception:
            _logger_guess_mimetype.warning(
                "Sub-checker '_get_olecf_mimetype' of type '%s' failed",
                mimetype,
                exc_info=True,
            )
    if mimetype == "application/zip":
        try:
            if msoffice_mimetype := _get_ooxml_mimetype(bin_data):
                return msoffice_mimetype
        except Exception:
            _logger_guess_mimetype.warning(
                "Sub-checker '_get_ooxml_mimetype' of type '%s' failed",
                mimetype,
                exc_info=True,
            )
    return mimetype


def _probe_mimetype_by_signature(bin_data: bytes, default: str) -> str:
    mimetype = _guess_mimetype_by_signature(bin_data, default)
    _debug.logic(
        "mimetype.probed_by_signature",
        magic=magic is not None,
        mimetype=mimetype,
        size=len(bin_data),
    )
    return mimetype


_extension_pattern = re.compile(r"\w+")


def get_extension(filename: str) -> str:
    _stem, dot, ext = filename.lstrip(".").rpartition(".")
    if not dot or not _extension_pattern.fullmatch(ext):
        return ""

    if len(ext) <= 4 or mimetypes.guess_type(filename)[0]:
        return f".{ext}".lower()
    return ""


_INERT_TEXT_EXTENSIONS = frozenset(
    {
        "cfg",
        "conf",
        "csv",
        "diff",
        "geojson",
        "ini",
        "json",
        "jsonl",
        "log",
        "markdown",
        "md",
        "ndjson",
        "patch",
        "po",
        "pot",
        "properties",
        "rst",
        "srt",
        "text",
        "toml",
        "tsv",
        "txt",
        "vtt",
        "xml",
        "yaml",
        "yml",
    }
)
_UNNAMED_TEXT_APPLICATION_MIMETYPES = frozenset(
    {
        "application/javascript",
        "application/x-mswinurl",
        "application/x-setupscript",
        "application/x-sh",
        "application/x-wine-extension-ini",
    }
)
# the system table may name another member of the family first:
# /etc/mime.types lists .xsl before .xml under application/xml
_CANONICAL_EXTENSIONS = {"application/xml": ".xml", "text/xml": ".xml"}


def _has_inert_text_extension(filename: str) -> bool:
    stem, dot, extension = filename.rpartition(".")
    return bool(dot and stem.strip(".")) and extension.lower() in _INERT_TEXT_EXTENSIONS


def fix_filename_extension(filename: str, mimetype: str) -> str:
    extension = get_extension(filename)
    added = _CANONICAL_EXTENSIONS.get(mimetype) or mimetypes.guess_extension(mimetype)
    if mimetype == "text/plain" or (
        added is None
        and (
            mimetype.startswith("text/")
            or mimetype in _UNNAMED_TEXT_APPLICATION_MIMETYPES
        )
    ):
        # a script is text too: a sniff saying no more than that vouches only
        # for an extension no program runs, and .txt defuses any other
        if _has_inert_text_extension(filename):
            return filename
        added = ".txt"
    elif (
        mimetypes.guess_type(filename)[0] == mimetype
        or (
            mimetype not in UNSPECIFIC_MIMETYPES
            and extension in mimetypes.guess_all_extensions(mimetype)
        )
        or (mimetype in OLECF_MIMETYPES and extension in _old_ms_office_mimetypes)
        or (mimetype == "application/zip" and extension in {".docx", ".xlsx", ".pptx"})
    ):
        return filename

    if added:
        _debug.logic(
            "mimetype.extension_fixed",
            extension=extension or None,
            mimetype=mimetype,
            added=added,
        )
        _logger.warning(
            "File %r has an invalid extension for mimetype %r, adding %r",
            filename,
            mimetype,
            added,
        )
        return filename + added

    _debug.logic(
        "mimetype.extension_unknown", extension=extension or None, mimetype=mimetype
    )
    _logger.warning(
        "File %r has an unknown extension for mimetype %r", filename, mimetype
    )
    return filename
