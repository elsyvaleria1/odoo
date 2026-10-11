import dataclasses


@dataclasses.dataclass(frozen=True)
class CalendarSyncCapabilities:
    """What a provider's calendar does that the engine must know of."""

    shared_ids: bool = False
    client_insert_id: bool = False
    series_inserts: bool = True
    answer_endpoint: bool = False
    insert_history: bool = True


@dataclasses.dataclass(frozen=True)
class CalendarSyncProvider:
    """What the engine knows of a provider; its adapter knows the rest."""

    code: str
    label: str
    key: str
    service: str
    scope: str
    paused_param: str
    adapter: str | None = None
    capabilities: CalendarSyncCapabilities = CalendarSyncCapabilities()
    range_param: str | None = None
    icon: str | None = None
