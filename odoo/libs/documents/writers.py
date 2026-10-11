from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping
from typing import Any, Protocol

from .availability import is_available
from .format import from_value
from .formats import mimetype_for
from .representations import ANY, CUES, DATA, REPRESENTATIONS, ROWS, TEXT, TREE

__all__ = [
    "BaseWriter",
    "get_known_writer_names",
    "get_writers",
    "register_writer",
    "registered_writers",
    "unregister_writer",
]


class BaseWriter:
    name: str = ""
    mimetype: str = ""
    consumes: str = ""
    module: str = ""

    def available(self, options: Mapping[str, Any]) -> bool:
        _ = options
        return True

    def write(self, value: Any, **options: Any) -> bytes:
        raise NotImplementedError

    def applies_to(self, mimetype: str) -> bool:
        return self.mimetype in (ANY, mimetype)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name}>"


class _WriteCallback(Protocol):
    def __call__(self, value: Any, **options: Any) -> bytes: ...


_WRITERS: dict[str, list[BaseWriter]] = {name: [] for name in REPRESENTATIONS}


def register_writer(writer: BaseWriter) -> BaseWriter:
    if not writer.name:
        raise ValueError(f"{writer!r} must name itself")
    if writer.consumes not in REPRESENTATIONS:
        raise ValueError(
            f"Writer {writer.name!r} consumes unknown representation "
            f"{writer.consumes!r}; expected one of {', '.join(REPRESENTATIONS)}"
        )
    if not writer.mimetype:
        raise ValueError(f"Writer {writer.name!r} emits no mimetype")
    if any(writer is known for writers in _WRITERS.values() for known in writers):
        raise ValueError(f"Writer {writer.name!r} is already registered")
    _WRITERS[writer.consumes].append(writer)
    return writer


def unregister_writer(writer: BaseWriter) -> None:
    for writers in _WRITERS.values():
        while writer in writers:
            writers.remove(writer)


def get_writers(
    mimetype: str,
    representation: str,
    *,
    options: Mapping[str, Any] | None = None,
) -> tuple[BaseWriter, ...]:
    if representation not in _WRITERS:
        raise ValueError(f"Unknown representation {representation!r}")
    named: list[BaseWriter] = []
    fallback: list[BaseWriter] = []
    for writer in _WRITERS[representation]:
        if not writer.applies_to(mimetype):
            continue
        if options is not None and not is_available(writer, options):
            continue
        (fallback if writer.mimetype == ANY else named).append(writer)
    return (*named, *fallback)


def registered_writers() -> tuple[BaseWriter, ...]:
    seen: dict[int, BaseWriter] = {}
    for writers in _WRITERS.values():
        for writer in writers:
            seen.setdefault(id(writer), writer)
    return tuple(seen.values())


def get_known_writer_names() -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for writers in _WRITERS.values():
        for writer in writers:
            seen.setdefault(writer.name, None)
    return tuple(sorted(seen))


def _prepare_writer(
    name: str,
    mimetype: str,
    consumes: str,
    write: _WriteCallback,
) -> BaseWriter:
    writer = BaseWriter()
    writer.name = name
    writer.mimetype = mimetype
    writer.consumes = consumes
    setattr(writer, "write", write)  # noqa: B010 - install a callback with the BaseWriter.write signature on this instance
    return writer


def _write_csv(value: Any, **options: Any) -> bytes:
    separator = options.get("separator") or ","
    quoting = options.get("quoting") or '"'
    encoding = options.get("encoding") or "utf-8"
    buffer = io.StringIO()
    writer = csv.writer(
        buffer,
        delimiter=separator,
        quotechar=quoting,
        lineterminator=options.get("lineterminator") or "\r\n",
    )
    cells = options.get("cells") or {}
    for row in value:
        writer.writerow([from_value(cell, **cells) for cell in row])
    return buffer.getvalue().encode(encoding)


def _write_json(value: Any, **options: Any) -> bytes:
    encoding = options.get("encoding") or "utf-8"
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=options.get("indent"),
        sort_keys=bool(options.get("sort_keys")),
        default=str,
    ).encode(encoding)


def _write_tree(value: Any, **options: Any) -> bytes:
    from lxml import etree

    return etree.tostring(
        value,
        xml_declaration=options.get("xml_declaration", True),
        encoding=options.get("encoding") or "utf-8",
        pretty_print=bool(options.get("pretty_print")),
    )


def _write_text(value: Any, **options: Any) -> bytes:
    return str(value).encode(options.get("encoding") or "utf-8")


def _write_vtt(value: Any, **options: Any) -> bytes:
    from .cues import render_vtt

    return render_vtt(value).encode(options.get("encoding") or "utf-8")


def _write_srt(value: Any, **options: Any) -> bytes:
    from .cues import render_srt

    return render_srt(value).encode(options.get("encoding") or "utf-8")


register_writer(_prepare_writer("csv", mimetype_for("csv"), ROWS, _write_csv))
register_writer(_prepare_writer("json", mimetype_for("json"), DATA, _write_json))
register_writer(_prepare_writer("xml", mimetype_for("xml"), TREE, _write_tree))
register_writer(_prepare_writer("text", ANY, TEXT, _write_text))
register_writer(_prepare_writer("vtt", mimetype_for("vtt"), CUES, _write_vtt))
register_writer(_prepare_writer("srt", mimetype_for("srt"), CUES, _write_srt))
