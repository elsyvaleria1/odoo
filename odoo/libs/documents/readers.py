from __future__ import annotations

import csv
import io
from collections.abc import Callable, Mapping
from typing import Any

from odoo.libs.json import loads as json_loads

from .availability import is_available
from .formats import RECORDING_EXTENSIONS, RECORDING_MIMETYPES, mimetypes_for
from .representations import (
    ANY,
    CHEAP,
    CUES,
    DATA,
    FREE,
    IMAGES,
    REPRESENTATIONS,
    ROWS,
    SHEETS,
    TEXT,
    TREE,
)

__all__ = [
    "VIDEO_MIMETYPES",
    "BaseReader",
    "get_known_reader_names",
    "get_readers",
    "reader_rank",
    "register_reader",
    "registered_readers",
    "unregister_reader",
]


class BaseReader:
    name: str = ""
    mimetypes: frozenset[str] = frozenset()
    yields: tuple[str, ...] = ()
    cost: int = FREE
    defers: bool = False
    module: str = ""
    async_only: bool = False
    # the answer is stored in the file (captions, a text layer), not inferred
    carried: bool = False

    def available(self, options: Mapping[str, Any]) -> bool:
        _ = options
        return True

    def defers_on(self, document: Any) -> bool:
        _ = document
        return self.defers

    def read(self, document: Any) -> Any:
        raise NotImplementedError

    def applies_to(self, mimetype: str) -> bool:
        return ANY in self.mimetypes or mimetype in self.mimetypes

    def provides(self, document: Any) -> bool | None:
        _ = document
        return None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name}>"


_READERS: dict[str, list[BaseReader]] = {
    name: [] for name in REPRESENTATIONS if name != SHEETS
}


def register_reader(reader: BaseReader) -> BaseReader:
    if not reader.name:
        raise ValueError(f"{reader!r} must name itself")
    if not reader.yields:
        raise ValueError(f"Reader {reader.name!r} yields no representation")
    unknown = set(reader.yields) - set(REPRESENTATIONS)
    if unknown:
        raise ValueError(
            f"Reader {reader.name!r} yields unknown representation(s) "
            f"{', '.join(sorted(unknown))}; expected one of "
            f"{', '.join(_READERS)}"
        )
    if SHEETS in reader.yields:
        raise ValueError(
            f"Reader {reader.name!r} yields {SHEETS}, which are built to be "
            "written and never read back"
        )
    if not reader.mimetypes:
        raise ValueError(f"Reader {reader.name!r} accepts no mimetype")
    if not isinstance(getattr(reader, "cost", None), int):
        raise ValueError(f"Reader {reader.name!r} declares no cost")
    if any(reader is known for readers in _READERS.values() for known in readers):
        raise ValueError(f"Reader {reader.name!r} is already registered")
    for representation in reader.yields:
        _READERS[representation].append(reader)
    return reader


def unregister_reader(reader: BaseReader) -> None:
    for readers in _READERS.values():
        while reader in readers:
            readers.remove(reader)


def get_readers(
    mimetype: str,
    representation: str,
    document: Any = None,
    *,
    up_to: int | None = None,
    options: Mapping[str, Any] | None = None,
) -> tuple[BaseReader, ...]:
    if representation not in _READERS:
        raise ValueError(f"Unknown representation {representation!r}")
    if options is None and document is not None:
        options = document.options
    named: list[BaseReader] = []
    fallback: list[BaseReader] = []
    for reader in _READERS[representation]:
        if not reader.applies_to(mimetype):
            continue
        # cost first: availability may ask a vendor router, which a read that
        # could never reach this reader must not pay for
        if up_to is not None and reader.cost > up_to:
            continue
        if options is not None and not is_available(reader, options):
            continue
        (fallback if ANY in reader.mimetypes else named).append(reader)

    def rank(reader: BaseReader) -> tuple[int, bool]:
        return reader_rank(reader, document)

    return (*sorted(named, key=rank), *sorted(fallback, key=rank))


def reader_rank(reader: BaseReader, document: Any = None) -> tuple[int, bool]:
    defers_on = getattr(reader, "defers_on", None)
    if document is not None and defers_on is not None:
        return (reader.cost, bool(defers_on(document)))
    return (reader.cost, getattr(reader, "defers", False))


def registered_readers() -> tuple[BaseReader, ...]:
    seen: dict[int, BaseReader] = {}
    for readers in _READERS.values():
        for reader in readers:
            seen.setdefault(id(reader), reader)
    return tuple(seen.values())


def get_known_reader_names() -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for readers in _READERS.values():
        for reader in readers:
            seen.setdefault(reader.name, None)
    return tuple(sorted(seen))


def _prepare_reader(
    name: str,
    mimetypes: frozenset[str],
    yields: tuple[str, ...],
    read: Callable[..., Any],
    cost: int = FREE,
    carried: bool = False,
) -> BaseReader:
    reader = BaseReader()
    reader.name = name
    reader.mimetypes = mimetypes
    reader.yields = yields
    reader.cost = cost
    reader.carried = carried
    reader.read = read  # type: ignore[method-assign]
    return reader


def _read_tree(document: Any) -> Any:
    from lxml import etree

    return etree.fromstring(
        document.data,
        parser=etree.XMLParser(
            remove_comments=True, resolve_entities=False, decompress=False
        ),
    )


def _read_data(document: Any) -> Any:
    return json_loads(document.data)


def _read_csv_rows(document: Any) -> list[list[str]]:
    options = document.options
    separator = options.get("separator") or ","
    quoting = options.get("quoting") or '"'
    reader = csv.reader(
        io.StringIO(document.decoded), delimiter=separator, quotechar=quoting
    )
    return [list(row) for row in reader]


def _read_vtt_cues(document: Any) -> Any:
    from .cues import parse_vtt

    return parse_vtt(document.decoded)


def _read_srt_cues(document: Any) -> Any:
    from .cues import parse_srt

    return parse_srt(document.decoded)


def _read_cued_text(document: Any) -> str:
    from .cues import cues_as_text

    return cues_as_text(document.cues, speakers=True)


register_reader(_prepare_reader("xml", mimetypes_for("xml"), (TREE,), _read_tree))
register_reader(_prepare_reader("json", mimetypes_for("json"), (DATA,), _read_data))
register_reader(_prepare_reader("csv", mimetypes_for("csv"), (ROWS,), _read_csv_rows))
register_reader(
    _prepare_reader("vtt", mimetypes_for("vtt"), (CUES,), _read_vtt_cues, carried=True)
)
register_reader(
    _prepare_reader("srt", mimetypes_for("srt"), (CUES,), _read_srt_cues, carried=True)
)
register_reader(
    _prepare_reader(
        "cued_text",
        mimetypes_for("vtt", "srt", *RECORDING_EXTENSIONS),
        (TEXT,),
        _read_cued_text,
    )
)


VIDEO_MIMETYPES = frozenset(
    mimetype for mimetype in RECORDING_MIMETYPES if mimetype.startswith("video/")
)


class _MediaReader(BaseReader):
    mimetypes = VIDEO_MIMETYPES
    cost = CHEAP

    def available(self, options: Mapping[str, Any]) -> bool:
        from .media import can_decode_media

        _ = options
        return can_decode_media()


class _VideoFrames(_MediaReader):
    name = "video_frames"
    yields = (IMAGES,)

    def read(self, document: Any) -> list[bytes] | None:
        from .media import keyframes

        return (
            keyframes(
                document.data,
                every_s=document.options.get("frame_every_s", 10.0),
                limit=document.options.get("frame_limit", 8),
            )
            or None
        )


class _EmbeddedSubtitles(_MediaReader):
    name = "embedded_subtitles"
    yields = (CUES,)
    carried = True

    def read(self, document: Any) -> Any:
        from .media import subtitle_cues

        return subtitle_cues(document.data) or None


register_reader(_VideoFrames())
register_reader(_EmbeddedSubtitles())
