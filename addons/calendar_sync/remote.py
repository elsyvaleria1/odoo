
import dataclasses
import enum
from collections.abc import Mapping
from datetime import datetime
from typing import Any


class RemoteKind(enum.StrEnum):
    SINGLE = "single"
    SERIES = "series"
    OCCURRENCE = "occurrence"


@dataclasses.dataclass(frozen=True)
class RemoteEvent:
    remote_id: str
    kind: RemoteKind = RemoteKind.SINGLE
    universal_id: str | None = None
    master_id: str | None = None
    cancelled: bool = False
    updated: datetime | None = None
    etag: str | None = None
    odoo_hint: int | None = None
    insert_id: str | None = None
    payload: Mapping[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class RemoteChanges:
    events: tuple[RemoteEvent, ...]
    next_token: str | None
    full: bool


class ErrorKind(enum.StrEnum):
    GONE = "gone"
    TOKEN_INVALID = "token_invalid"
    CONFLICT = "conflict"
    PRECONDITION = "precondition"
    FORBIDDEN = "forbidden"
    INVALID = "invalid"
    THROTTLED = "throttled"
    TRANSIENT = "transient"
    AUTH = "auth"


PERMANENT = frozenset({ErrorKind.FORBIDDEN, ErrorKind.INVALID})


class CalendarSyncError(Exception):
    def __init__(self, kind: ErrorKind, message: str = "") -> None:
        super().__init__(message or kind)
        self.kind = kind
        self.message = message or str(kind)
