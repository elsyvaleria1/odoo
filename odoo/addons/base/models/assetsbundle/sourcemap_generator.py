__all__ = ["SourceMapGenerator"]

from typing import NamedTuple

from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.libs.sourcemap import encode_vlq


class _Mapping(NamedTuple):
    generated_line: int
    original_line: int
    source: str


class SourceMapGenerator:
    def __init__(self, source_root: str | None = None) -> None:
        self.file: str | None = None
        self._source_root: str | None = source_root
        self._sources: dict[str, int] = {}
        self._mappings: list[_Mapping] = []
        self._sources_contents: dict[str, str] = {}
        self._cache: dict[tuple[int, int], str] = {}

    def _serialize_mappings(self) -> str:
        previous_generated_line = 1
        previous_original_line = 0
        previous_source = 0
        encoded_column = encode_vlq(0)
        parts: list[str] = []

        for generated_line, original_line, source in self._mappings:
            if generated_line != previous_generated_line:
                parts.append(";" * (generated_line - previous_generated_line))
                previous_generated_line = generated_line

            source_idx = self._sources[source]
            source_delta = source_idx - previous_source
            previous_source = source_idx

            line_delta = original_line - 1 - previous_original_line
            previous_original_line = original_line - 1

            cache_key = (source_delta, line_delta)
            if cache_key not in self._cache:
                self._cache[cache_key] = (
                    encoded_column
                    + encode_vlq(source_delta)
                    + encode_vlq(line_delta)
                    + encoded_column
                )

            parts.append(self._cache[cache_key])

        return "".join(parts)

    def to_json(self) -> dict[str, object]:
        result: dict[str, object] = {
            "version": 3,
            "sources": list(self._sources),
            "mappings": self._serialize_mappings(),
            "sourcesContent": [
                self._sources_contents[source] for source in self._sources
            ],
        }
        if self.file:
            result["file"] = self.file
        if self._source_root:
            result["sourceRoot"] = self._source_root
        return result

    def get_content(self) -> bytes:
        return b")]}'\n" + json_dumps_bytes(self.to_json())

    def add_source(
        self,
        source_name: str,
        source_content: str,
        last_index: int,
        start_offset: int = 0,
    ) -> None:
        source_line_count = source_content.count("\n") + 1

        self._sources.setdefault(source_name, len(self._sources))
        self._sources_contents[source_name] = source_content

        append = self._mappings.append
        if start_offset > 0:
            append(_Mapping(last_index + 1, 1, source_name))

        for i in range(1, source_line_count + 1):
            append(_Mapping(last_index + i + start_offset, i, source_name))
