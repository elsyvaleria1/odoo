import dataclasses
from collections.abc import Callable


@dataclasses.dataclass(frozen=True)
class Oauth2MailProvider:
    """A mail vendor: whose OAuth service authorizes its servers, and for what."""

    label: str
    service: str
    scope: str | Callable

    def resolve(self, value, records):
        return value(records) if callable(value) else value
