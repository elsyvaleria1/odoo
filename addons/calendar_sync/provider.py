import dataclasses


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
