from __future__ import annotations

import bisect
from collections.abc import Iterable, Iterator, Mapping
from typing import Any, Final, NamedTuple

__all__ = ["Original", "Segment", "SourceMap", "encode_vlq", "iter_segments"]

_B64: Final = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_B64_BYTES: Final = _B64.encode()
_DIGIT: Final = {char: value for value, char in enumerate(_B64)}
_SHIFT: Final = 5
_CONTINUE: Final = 1 << _SHIFT
_MASK: Final = _CONTINUE - 1


def encode_vlq(*values: int) -> str:
    out = bytearray()
    for value in values:
        value = (abs(value) << 1) | int(value < 0)
        while True:
            digit, value = value & _MASK, value >> _SHIFT
            out.append(_B64_BYTES[digit | (_CONTINUE if value else 0)])
            if not value:
                break
    return out.decode()


def _decode_vlq(segment: str) -> list[int]:
    values = []
    value = shift = 0
    for char in segment:
        digit = _DIGIT[char]
        value += (digit & _MASK) << shift
        if digit & _CONTINUE:
            shift += _SHIFT
        else:
            values.append(-(value >> 1) if value & 1 else value >> 1)
            value = shift = 0
    return values


class Segment(NamedTuple):

    line: int
    column: int
    source: int | None
    source_line: int
    source_column: int
    name: int | None


def iter_segments(mappings: str, *, until_line: int | None = None) -> Iterator[Segment]:
    source = source_line = source_column = name = 0
    for line, text in enumerate(mappings.split(";")):
        if until_line is not None and line > until_line:
            return
        column = 0
        for raw in text.split(","):
            if not raw:
                continue
            fields = _decode_vlq(raw)
            column += fields[0]
            if len(fields) < 4:
                yield Segment(line, column, None, 0, 0, None)
                continue
            source += fields[1]
            source_line += fields[2]
            source_column += fields[3]
            named = None
            if len(fields) > 4:
                name += fields[4]
                named = name
            yield Segment(line, column, source, source_line, source_column, named)


class Original(NamedTuple):

    source: str
    line: int
    column: int
    name: str | None
    text: str | None


class SourceMap:
    __slots__ = ("_contents", "_mappings", "_names", "_sources")

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._sources: list[str] = list(data.get("sources") or ())
        self._names: list[str] = list(data.get("names") or ())
        self._contents: list[str | None] = list(data.get("sourcesContent") or ())
        self._mappings: str = data.get("mappings") or ""

    def locate(
        self, positions: Iterable[tuple[int, int]]
    ) -> dict[tuple[int, int], Original | None]:
        wanted = set(positions)
        if not wanted:
            return {}
        by_line: dict[int, list[Segment]] = {line: [] for line, _ in wanted}
        for segment in iter_segments(self._mappings, until_line=max(by_line)):
            if segment.line in by_line:
                by_line[segment.line].append(segment)
        found: dict[tuple[int, int], Original | None] = {}
        for line, column in wanted:
            segments = by_line[line]
            index = bisect.bisect_right([s.column for s in segments], column) - 1
            found[line, column] = (
                self._original(segments[index]) if index >= 0 else None
            )
        return found

    def _original(self, segment: Segment) -> Original | None:
        if segment.source is None or not 0 <= segment.source < len(self._sources):
            return None
        content = (
            self._contents[segment.source]
            if segment.source < len(self._contents)
            else None
        )
        text = None
        if content is not None:
            lines = content.splitlines()
            if 0 <= segment.source_line < len(lines):
                text = lines[segment.source_line]
        name = (
            self._names[segment.name]
            if segment.name is not None and 0 <= segment.name < len(self._names)
            else None
        )
        return Original(
            self._sources[segment.source],
            segment.source_line,
            segment.source_column,
            name,
            text,
        )
