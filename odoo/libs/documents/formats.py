from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass, field

from odoo.libs.debug_log import DebugLog
from odoo.libs.filesystem import mimetypes as filesystem_mimetypes

__all__ = [
    "RECORDING_EXTENSIONS",
    "RECORDING_MIMETYPES",
    "Format",
    "canonical_mimetypes",
    "extension_for",
    "fix_filename_extension",
    "get_format",
    "get_format_of_extension",
    "get_known_formats",
    "mimetype_for",
    "mimetypes_for",
    "register_extension",
    "register_format",
]


@dataclass(frozen=True, slots=True)
class Format:
    mimetype: str
    extension: str
    aliases: frozenset[str] = field(default_factory=frozenset)
    read_from: frozenset[str] = field(default_factory=frozenset)

    @property
    def spellings(self) -> frozenset[str]:
        return frozenset({self.mimetype, *self.aliases})

    @property
    def mimetypes(self) -> frozenset[str]:
        return self.spellings | self.read_from

    def __repr__(self) -> str:
        return f"<Format {self.extension} {self.mimetype}>"


_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

_FORMATS: list[Format] = []
_BY_MIMETYPE: dict[str, Format] = {}
_BY_EXTENSION: dict[str, Format] = {}
_BY_ALIAS: dict[str, Format] = {}


def register_format(fmt: Format) -> Format:
    if not fmt.mimetype:
        raise ValueError(f"{fmt!r} must name a mimetype")
    if not fmt.extension:
        raise ValueError(f"Format {fmt.mimetype!r} must name an extension")
    mimetype = fmt.mimetype.lower()
    extension = fmt.extension.lower().lstrip(".")
    if mimetype in _BY_MIMETYPE:
        raise ValueError(f"{mimetype!r} is already registered")
    if extension in _BY_EXTENSION:
        raise ValueError(f"{extension!r} is already registered")
    _FORMATS.append(fmt)
    _BY_MIMETYPE[mimetype] = fmt
    _BY_EXTENSION[extension] = fmt
    for alias in fmt.aliases:
        _BY_ALIAS.setdefault(alias.lower(), fmt)
    return fmt


def register_extension(extension: str, mimetype: str) -> Format:
    extension = (extension or "").lower().lstrip(".")
    fmt = _BY_MIMETYPE.get((mimetype or "").lower())
    if fmt is None:
        raise ValueError(f"No format is registered for {mimetype!r}")
    if not extension:
        raise ValueError(f"An extension for {mimetype!r} cannot be empty")
    registered = _BY_EXTENSION.get(extension)
    if registered is not None and registered is not fmt:
        raise ValueError(
            f"{extension!r} already means {registered.mimetype!r}, not {mimetype!r}"
        )
    _BY_EXTENSION[extension] = fmt
    return fmt


def get_format(mimetype: str) -> Format | None:
    mimetype = (mimetype or "").lower()
    return _BY_MIMETYPE.get(mimetype) or _BY_ALIAS.get(mimetype)


def get_format_of_extension(extension: str) -> Format | None:
    return _BY_EXTENSION.get((extension or "").lower().lstrip("."))


def mimetype_for(extension: str) -> str:
    fmt = get_format_of_extension(extension)
    return fmt.mimetype if fmt else ""


def extension_for(mimetype: str) -> str:
    fmt = get_format(mimetype)
    return fmt.extension if fmt else ""


def mimetypes_for(*extensions: str) -> frozenset[str]:
    claimed: set[str] = set()
    for fmt in _get_formats_of_extensions(extensions):
        claimed |= fmt.mimetypes
    return frozenset(claimed)


def canonical_mimetypes(*extensions: str) -> frozenset[str]:
    return frozenset(fmt.mimetype for fmt in _get_formats_of_extensions(extensions))


def _get_formats_of_extensions(extensions: tuple[str, ...]) -> tuple[Format, ...]:
    found = []
    for extension in extensions:
        fmt = get_format_of_extension(extension)
        if fmt is None:
            raise ValueError(f"No format is registered under {extension!r}")
        found.append(fmt)
    return tuple(found)


def get_known_formats() -> tuple[Format, ...]:
    return tuple(_FORMATS)


def fix_filename_extension(filename: str, mimetype: str) -> str:
    named = get_format_of_extension(filesystem_mimetypes.get_extension(filename))
    if named is not None and mimetype.lower() in named.mimetypes:
        return filename
    fmt = get_format(mimetype)
    if fmt is None or mimetypes.guess_type(filename)[0] == mimetype:
        return filesystem_mimetypes.fix_filename_extension(filename, mimetype)
    extension = f".{fmt.extension}"
    _debug.logic("format.extension_fixed", mimetype=mimetype, added=extension)
    _logger.warning(
        "File %r has an invalid extension for mimetype %r, adding %r",
        filename,
        mimetype,
        extension,
    )
    return filename + extension


_BUILTIN_FORMATS = (
    ("text/csv", "csv", {"application/csv"}, {"text/plain"}),
    ("application/xml", "xml", {"text/xml"}, {"application/xhtml+xml"}),
    ("application/json", "json", {"text/json"}, ()),
    ("text/vtt", "vtt", (), ()),
    ("application/x-subrip", "srt", {"application/x-srt", "text/srt"}, ()),
    ("application/pdf", "pdf", (), ()),
    ("image/png", "png", (), ()),
    ("image/jpeg", "jpg", {"image/jpg", "image/jpe"}, ()),
    ("image/webp", "webp", (), ()),
    ("image/gif", "gif", (), ()),
    ("image/bmp", "bmp", (), ()),
    ("image/svg+xml", "svg", (), ()),
    (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
        (),
        {"application/vnd.ms-excel.sheet.macroenabled.12"},
    ),
    ("application/vnd.ms-excel", "xls", (), ()),
    ("application/vnd.oasis.opendocument.spreadsheet", "ods", (), ()),
    (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
        (),
        (),
    ),
    (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "pptx",
        (),
        (),
    ),
    ("application/vnd.oasis.opendocument.text", "odt", (), ()),
    ("application/vnd.oasis.opendocument.presentation", "odp", (), ()),
    ("application/vnd.oasis.opendocument.graphics", "odg", (), ()),
    ("application/msword", "doc", (), ()),
    ("application/vnd.ms-powerpoint", "ppt", (), ()),
)
_BUILTIN_RECORDING_FORMATS = (
    ("audio/mpeg", "mp3", {"audio/mp3", "audio/x-mpeg"}),
    ("audio/ogg", "ogg", {"audio/opus", "audio/vorbis"}),
    ("audio/wav", "wav", {"audio/x-wav", "audio/wave"}),
    ("audio/webm", "weba", ()),
    ("audio/mp4", "m4a", {"audio/x-m4a"}),
    ("audio/flac", "flac", {"audio/x-flac"}),
    ("audio/aac", "aac", ()),
    ("video/webm", "webm", ()),
    ("video/mp4", "mp4", ()),
    ("video/quicktime", "mov", ()),
    ("video/x-matroska", "mkv", {"video/matroska"}),
    ("video/mpeg", "mpeg", ()),
    ("video/ogg", "ogv", ()),
)
RECORDING_EXTENSIONS = tuple(
    extension for _, extension, _ in _BUILTIN_RECORDING_FORMATS
)
_BUILTIN_EXTENSION_ALIASES = (("jpeg", "image/jpeg"),)

for _mimetype, _extension, _aliases, _read_from in _BUILTIN_FORMATS:
    register_format(
        Format(
            mimetype=_mimetype,
            extension=_extension,
            aliases=frozenset(_aliases),
            read_from=frozenset(_read_from),
        )
    )
for _mimetype, _extension, _aliases in _BUILTIN_RECORDING_FORMATS:
    register_format(
        Format(mimetype=_mimetype, extension=_extension, aliases=frozenset(_aliases))
    )
for _extension, _mimetype in _BUILTIN_EXTENSION_ALIASES:
    register_extension(_extension, _mimetype)

RECORDING_MIMETYPES = mimetypes_for(*RECORDING_EXTENSIONS)
