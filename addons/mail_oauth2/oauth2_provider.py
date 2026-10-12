import dataclasses
from collections.abc import Callable


@dataclasses.dataclass(frozen=True)
class Oauth2MailProvider:
    label: str
    service: str
    scope: str | Callable

    def resolve(self, value, records):
        return value(records) if callable(value) else value
