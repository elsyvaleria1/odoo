from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from odoo.libs.debug_log import DebugLog
from odoo.libs.filesystem.mimetypes import (
    UNSPECIFIC_MIMETYPES,
    get_essential_mimetype,
    guess_mimetype,
)

from .formats import mimetype_for
from .guess import decode, is_text_like
from .readers import get_readers
from .representations import (
    BARCODES,
    CHEAP,
    CHILDREN,
    CUES,
    DATA,
    FREE,
    GENERATIVE,
    IMAGES,
    REPRESENTATIONS,
    ROWS,
    TEXT,
    TREE,
)
from .writers import get_known_writer_names, get_writers

__all__ = [
    "DEFAULT_READ_UP_TO",
    "TEXT_MAX_CHARS",
    "Document",
]

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

TEXT_MAX_CHARS = 60_000

_OPAQUE_MIMETYPE_FAMILIES = ("image/", "audio/", "video/", "font/", "model/")

DEFAULT_READ_UP_TO = CHEAP

_DEFAULT_MIMETYPES = {
    ROWS: mimetype_for("csv"),
    TEXT: "text/plain",
    TREE: mimetype_for("xml"),
    DATA: mimetype_for("json"),
    CUES: mimetype_for("vtt"),
}


_PROPERTIES = {
    ROWS: "rows",
    TEXT: "text",
    TREE: "tree",
    DATA: "data_dict",
    IMAGES: "images",
    BARCODES: "barcodes",
    CHILDREN: "children",
    CUES: "cues",
}


def _clamp(text: str, name: str, limit: int = TEXT_MAX_CHARS) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    _debug.logic("document.text_clamped", name=name, chars=len(text), limit=limit)
    return text[:limit]


class Document:
    def __init__(
        self,
        data: bytes | Callable[[], bytes],
        mimetype: str = "",
        name: str = "",
        **options: Any,
    ) -> None:
        self._load: Callable[[], bytes] | None = None
        self._data: bytes | None = None
        declared = get_essential_mimetype(mimetype)
        if callable(data) and declared not in UNSPECIFIC_MIMETYPES:
            self._load = data
            mimetype = declared
        else:
            raw = data() if callable(data) else data
            if not raw:
                raise ValueError("A document needs data.")
            self._data = raw
            mimetype = guess_mimetype(raw, declared=declared)
        self.name: str = name
        self.mimetype: str = get_essential_mimetype(mimetype)
        self.options: dict[str, Any] = options
        self.errors: dict[str, str] = {}
        self.wanted: set[str] = set()
        self._derived: dict[str, Any] = {}
        self._derived_at: dict[str, int] = {}
        self._read_by: dict[str, str] = {}
        self._read_cost: dict[str, int] = {}
        self._consulted: set[str] = set()
        self._decoded: str | UnicodeDecodeError | None = None
        _debug.lifecycle(
            "document.created",
            mimetype=self.mimetype,
            declared=declared or None,
            size=None if self._data is None else len(self._data),
            named=bool(name),
            options=",".join(sorted(options)) or None,
        )

    @property
    def data(self) -> bytes:
        if self._data is None:
            assert self._load is not None
            loaded = self._load()
            if not loaded:
                raise ValueError("A document needs data.")
            self._data, self._load = loaded, None
            _debug.lifecycle("document.loaded", name=self.name, size=len(loaded))
        return self._data

    @property
    def decoded(self) -> str:
        if self._decoded is None:
            try:
                self._decoded = decode(self.data, self.options.get("encoding") or "")
            except UnicodeDecodeError as e:
                self._decoded = e
        if isinstance(self._decoded, UnicodeDecodeError):
            raise self._decoded
        return self._decoded

    @property
    def read_up_to(self) -> int:
        read_up_to: int = self.options.get("read_up_to", DEFAULT_READ_UP_TO)
        return read_up_to

    @property
    def text_max_chars(self) -> int:
        text_max_chars: int = self.options.get("text_max_chars", TEXT_MAX_CHARS)
        return text_max_chars

    @classmethod
    def of(
        cls,
        *,
        rows: Any = None,
        text: Any = None,
        tree: Any = None,
        data: Any = None,
        cues: Any = None,
        mimetype: str = "",
        name: str = "",
        **options: Any,
    ) -> Document:
        given = {
            ROWS: rows,
            TEXT: text,
            TREE: tree,
            DATA: data,
            CUES: cues,
        }
        named = [rep for rep, value in given.items() if value is not None]
        if len(named) != 1:
            raise ValueError(
                "A document is written from exactly one representation; got "
                f"{', '.join(named) if named else 'none'}"
            )
        representation = named[0]
        value = given[representation]
        mimetype = get_essential_mimetype(
            mimetype or _DEFAULT_MIMETYPES[representation]
        )
        writers = get_writers(mimetype, representation, options=options)
        _debug.logic(
            "document.writer_chosen",
            representation=representation,
            mimetype=mimetype,
            candidates=len(writers),
            writer=writers[0].name if writers else None,
        )
        if not writers:
            raise ValueError(
                f"Nothing writes {representation} as {mimetype!r}; "
                f"registered: {', '.join(get_known_writer_names()) or 'none'}"
            )
        with _debug.perf(
            "document.write", writer=writers[0].name, mimetype=mimetype
        ) as span:
            written = writers[0].write(value, **options)
            span.set(size=len(written))
        document = cls(written, mimetype, name, **options)
        document._derived[representation] = value
        return document

    @property
    def rows(self) -> list[list[Any]]:
        return self._derive(ROWS) or []

    @property
    def text(self) -> str:
        derived = self._derive(TEXT)
        if derived is None and self._falls_back_to_decoding():
            if self.mimetype.startswith(_OPAQUE_MIMETYPE_FAMILIES):
                decoded = ""
            else:
                try:
                    decoded = self._decode_head()
                except UnicodeDecodeError as e:
                    _logger.info("Could not decode %r: %s", self.name, e)
                    decoded = ""
            derived = decoded if is_text_like(decoded) else ""
            self._derived[TEXT] = _clamp(derived, self.name, self.text_max_chars)
        return self._derived.get(TEXT) or ""

    def _falls_back_to_decoding(self) -> bool:
        if TEXT in self._consulted:
            return False
        ceiling = self.read_up_to
        return not any(
            reader.cost > ceiling for reader in get_readers(self.mimetype, TEXT)
        )

    def _decode_head(self) -> str:
        limit = self.text_max_chars
        data = self.data
        if isinstance(self._decoded, str) or limit <= 0 or len(data) <= limit * 4:
            return self.decoded
        return decode(
            data[: limit * 4], self.options.get("encoding") or "", final=False
        )

    @property
    def tree(self) -> Any:
        return self._derive(TREE)

    @property
    def data_dict(self) -> dict[str, Any] | list[Any] | None:
        data: dict[str, Any] | list[Any] | None = self._derive(DATA)
        return data

    @property
    def images(self) -> list[bytes]:
        return self._derive(IMAGES) or []

    @property
    def barcodes(self) -> list[str]:
        return self._derive(BARCODES) or []

    @property
    def children(self) -> list[Document]:
        return self._derive(CHILDREN) or []

    @property
    def cues(self) -> list[Any]:
        return self._derive(CUES) or []

    def _is_read(self, representation: str, value: Any) -> bool:
        if value is None:
            return False
        return True if representation == TREE else bool(value)

    def read(self, representation: str) -> Any:
        if representation not in _PROPERTIES:
            raise ValueError(f"{representation!r} is not read by name")
        return getattr(self, _PROPERTIES[representation])

    def seed(self, representation: str, value: Any, read_by: str = "") -> None:
        if representation not in _PROPERTIES:
            raise ValueError(f"{representation!r} is not read from a document")
        self._derived[representation] = value
        self._derived_at[representation] = GENERATIVE
        self._read_by[representation] = read_by
        self.errors.pop(representation, None)

    def _seeded(self, representation: str) -> bool:
        seeder = self.options.get("seeder")
        if seeder is None or representation in self._derived:
            return False
        found = seeder(representation)
        if found is None:
            return False
        value, read_by = found
        self.seed(representation, value, read_by)
        return True

    def provides(self, representation: str) -> bool:
        if representation not in REPRESENTATIONS:
            raise ValueError(f"Unknown representation {representation!r}")
        if representation not in _PROPERTIES:
            return False
        if self._seeded(representation):
            return self._is_read(representation, self._derived[representation])
        cheap = [
            answer
            for reader in get_readers(
                self.mimetype, representation, self, up_to=self.read_up_to
            )
            if (answer := reader.provides(self)) is not None
        ]
        if cheap:
            return any(cheap)
        return self._is_read(representation, self.read(representation))

    def _derive(self, representation: str) -> Any:
        ceiling = self.read_up_to
        self._seeded(representation)
        if representation in self._derived:
            cached = self._derived[representation]
            if self._is_read(representation, cached) or ceiling <= self._derived_at.get(
                representation, ceiling
            ):
                _debug.logic(
                    "document.derive.cached",
                    representation=representation,
                    mimetype=self.mimetype,
                    ceiling=ceiling,
                )
                return cached
        value = None
        clamp = representation == TEXT
        deferring = bool(self.options.get("defer_async"))
        wanted_before = len(self.wanted)
        with _debug.perf(
            "document.derive",
            representation=representation,
            mimetype=self.mimetype,
            ceiling=ceiling,
        ) as span:
            tried = failed = deferred = 0
            winner = ""
            winner_cost = FREE
            for reader in get_readers(
                self.mimetype,
                representation,
                self,
                up_to=None if deferring else ceiling,
            ):
                if deferring and reader.async_only:
                    deferred += 1
                    self._consulted.add(representation)
                    self.wanted.add(representation)
                    continue
                if reader.cost > ceiling:
                    continue
                self._consulted.add(representation)
                tried += 1
                try:
                    answer = reader.read(self)
                except Exception as e:
                    failed += 1
                    self.errors[representation] = str(e) or type(e).__name__
                    _debug.logic(
                        "document.reader_failed",
                        reader=reader.name,
                        representation=representation,
                        mimetype=self.mimetype,
                        error=type(e).__name__,
                    )
                    _logger.info(
                        "Reader %s could not derive %s from %r: %s",
                        reader.name,
                        representation,
                        self.name or self.mimetype,
                        e,
                    )
                    continue
                if answer is None:
                    continue
                read = self._is_read(representation, answer)
                if value is None or read:
                    value = answer
                    winner = reader.name
                    winner_cost = reader.cost
                if read:
                    break
            if clamp and value:
                value = _clamp(value, self.name, self.text_max_chars)
            span.set(
                tried=tried,
                failed=failed,
                deferred=deferred,
                reader=winner,
                read=self._is_read(representation, value),
            )
        if self._is_read(representation, value):
            self.errors.pop(representation, None)
        if len(self.wanted) > wanted_before:
            return value
        self._derived[representation] = value
        self._derived_at[representation] = ceiling
        self._read_by[representation] = winner
        self._read_cost[representation] = winner_cost
        return value

    def read_by(self, representation: str) -> str:
        return self._read_by.get(representation, "")

    def read_cost(self, representation: str) -> int:
        return self._read_cost.get(representation, FREE)

    def __repr__(self) -> str:
        size = "?" if self._data is None else len(self._data)
        return f"<Document {self.name or '?'} {self.mimetype} {size}B>"
