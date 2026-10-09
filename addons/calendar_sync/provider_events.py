"""A provider's events as it lists them, before an adapter reads them into
the engine's `RemoteEvent`."""

from collections import abc
from collections.abc import Iterable, Iterator, Mapping
from typing import Any, Self

from odoo.libs.collections import ReadonlyDict
from odoo.libs.json import dumps as json_dumps


class ProviderEvents(abc.Set):
    """One or several of a provider's events, by id, as an immutable set:
    the usual set operations apply, and a single event reads its payload's
    keys as attributes. A provider's adapter subclasses it with what its
    payloads mean."""

    def __init__(self, iterable: Iterable[Self | Mapping[str, Any]] = ()) -> None:
        events = {}
        for item in iterable:
            if isinstance(item, type(self)):
                events[item.id] = item._events[item.id]
            elif isinstance(item, Mapping):
                events[item.get("id")] = item
            else:
                raise ValueError(
                    f"Only {type(self).__name__} or iterable of dict are supported"
                )
        self._events = ReadonlyDict(events)

    def __iter__(self) -> Iterator[Self]:
        return iter(type(self)([vals]) for vals in self._events.values())

    def __contains__(self, event) -> bool:
        return event.id in self._events

    def __len__(self) -> int:
        return len(self._events)

    def __bool__(self) -> bool:
        return bool(self._events)

    def __getattr__(self, name):
        try:
            (event_id,) = self._events
        except ValueError:
            raise ValueError(f"Expected singleton: {self}") from None
        value = self._events[event_id].get(name)
        json_dumps(value)
        return value

    def __repr__(self) -> str:
        return f"{type(self).__name__}{self.ids}"

    @property
    def ids(self) -> tuple:
        """The events' ids, each the calendar's own."""
        return tuple(event.id for event in self)

    def filter(self, func) -> Self:
        return type(self)(event for event in self if func(event))
