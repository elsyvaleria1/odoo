import dataclasses


@dataclasses.dataclass(frozen=True)
class CalendarSyncCapabilities:
    """What a provider's calendar does that the engine must know of."""

    # an item's id is the same in every calendar holding it
    shared_ids: bool = False
    # the insert id is the item's id, so a repeated insert is refused as a
    # conflict; otherwise the provider deduplicates on it
    client_insert_id: bool = False
    # Odoo may create a series in the provider's calendars
    series_inserts: bool = True
    # an attendee answers in their own calendar, which tells the organizer;
    # otherwise the organizer's copy is sent again with the answers
    answer_endpoint: bool = False


@dataclasses.dataclass(frozen=True)
class CalendarSyncProvider:
    """What the engine knows of a provider; its adapter knows the rest."""

    code: str
    label: str
    # the key the calendar view and its readers file the provider's status under
    key: str
    service: str
    scope: str
    paused_param: str
    # the adapter model the engine runs; None while the provider runs its own
    adapter: str | None = None
    capabilities: CalendarSyncCapabilities = CalendarSyncCapabilities()
    # how many days around today a full synchronization reaches
    range_param: str | None = None
