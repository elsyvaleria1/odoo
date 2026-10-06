from collections.abc import Iterable, Mapping
from typing import Protocol, TypedDict

from odoo.libs.collections import ReadonlyDict

type EventId = str | None


class EventPayload(TypedDict, total=False):
    id: EventId


class EventRecord(Protocol):
    id: EventId
    _events: Mapping[EventId, EventPayload]


def prepare_event_mapping[T: EventRecord](
    event_type: type[T], iterable: Iterable[T | EventPayload]
) -> ReadonlyDict[EventId, EventPayload]:
    events: dict[EventId, EventPayload] = {}
    for item in iterable:
        if isinstance(item, event_type):
            events[item.id] = item._events[item.id]
        elif isinstance(item, Mapping):
            events[item.get("id")] = item
        else:
            raise ValueError(
                "Only %s or iterable of dict are supported" % event_type.__name__
            )
    return ReadonlyDict(events)
