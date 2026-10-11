"""What a provider's calendar service shares with the others: its connection,
the raw call through the connection's API client, and the refusal of a sync
token the provider no longer knows."""

import requests


class InvalidSyncToken(Exception):
    pass


def requires_connection(func):
    def wrapped(self, *args, **kwargs):
        if not kwargs.get("connection"):
            raise AttributeError("An authorized calendar connection is required")
        return func(self, *args, **kwargs)

    return wrapped


class CalendarService:
    def __init__(self, env) -> None:
        self.env = env

    def _response(self, connection, method, path, **kwargs) -> requests.Response:
        return connection._get_api_client().request(
            method, path, raw=True, raise_for_status=False, **kwargs
        )
