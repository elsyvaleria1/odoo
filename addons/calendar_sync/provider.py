import dataclasses


@dataclasses.dataclass(frozen=True)
class CalendarSyncCapabilities:
    shared_ids: bool = False
    client_insert_id: bool = False
    series_inserts: bool = True
    answer_endpoint: bool = False
    insert_history: bool = True


@dataclasses.dataclass(frozen=True)
class CalendarSyncProvider:
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
