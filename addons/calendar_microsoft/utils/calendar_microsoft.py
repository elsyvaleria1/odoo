import logging
from urllib.parse import parse_qs, urlsplit

import requests

from odoo import fields

from odoo.addons.calendar_microsoft.utils.microsoft_event import MicrosoftEvent

_logger = logging.getLogger(__name__)

TIMEOUT = 20
RESOURCE_NOT_FOUND_STATUSES = (204, 404)
CALENDAR_SCOPE = "offline_access openid Calendars.ReadWrite"


def requires_connection(func):
    def wrapped(self, *args, **kwargs):
        if not kwargs.get("connection"):
            raise AttributeError("An authorized Microsoft connection is required")
        return func(self, *args, **kwargs)

    return wrapped


class InvalidSyncToken(Exception):
    pass


# In Outlook, an event can be:
# - a 'singleInstance' event,
# - a 'serie master' which contains all the information about an event reccurrence such as
# - an 'occurrence' which is an event from a reccurrence (serie) that follows this reccurrence
# - an 'exception' which is an event from a reccurrence (serie) but some differences with the reccurrence template (could be
#   the name, the day of occurrence, ...)
#
#  All these kinds of events are identified by:
#  - a event ID (id) which is specific to an Outlook calendar.
#  - a global event ID (iCalUId) which is common to all Outlook calendars containing this event.
#
#  - 'singleInstance' and 'serie master' events are retrieved through the end-point `/v1.0/me/calendarView/delta` which provides
#  the last modified/deleted items since the last sync (or all of these items at the first time).
#  - 'occurrence' and 'exception' events are retrieved through the end-point `/v1.0/me/events/{serieMaster.id}/instances`,
#  using the corresponding serie master ID.


class MicrosoftCalendarService:
    def __init__(self, env) -> None:
        self.env = env

    def _request(
        self, connection, method, path, *, params=None, json=None, headers=None, timeout
    ) -> tuple:
        """(status, body) of Graph's answer, raising requests.HTTPError for a
        refusal; 204 and 404 answer an empty body."""
        response = connection._get_api_client().request(
            method,
            path,
            raw=True,
            raise_for_status=False,
            params=params,
            json=json,
            headers=headers,
            timeout=timeout,
        )
        if response.status_code in RESOURCE_NOT_FOUND_STATUSES:
            return response.status_code, {}
        response.raise_for_status()
        # Some answers return empty content
        return response.status_code, (response.content and response.json()) or {}

    @requires_connection
    def _get_single_event(self, iCalUId, connection, timeout=TIMEOUT) -> tuple:
        """Fetch a single event from Graph API filtered by its iCalUId."""
        url = "/v1.0/me/events?$filter=iCalUId eq '%s'" % iCalUId
        status, event = self._request(connection, "GET", url, timeout=timeout)
        return status not in RESOURCE_NOT_FOUND_STATUSES, event

    @requires_connection
    def _get_events_from_paginated_url(
        self, url, connection=None, params=None, timeout=TIMEOUT
    ) -> tuple:
        """
        Get a list of events from a paginated URL.
        Each page contains a link to the next page, so loop over all the pages to get all the events.
        """
        headers = {
            "Prefer": 'outlook.body-content-type="html", odata.maxpagesize=50',
        }
        if not params:
            # By default, fetch events from at most one year in the past and two years in the future.
            # Can be modified by calendar_microsoft.sync.range_days system parameter.
            day_range = int(
                self.env.registry.settings.get(
                    self.env, "calendar_microsoft.sync.range_days", 365
                )
            )
            params = {
                "startDateTime": fields.Datetime.subtract(
                    fields.Datetime.now(), days=day_range
                ).strftime("%Y-%m-%dT00:00:00Z"),
                "endDateTime": fields.Datetime.add(
                    fields.Datetime.now(), days=day_range * 2
                ).strftime("%Y-%m-%dT00:00:00Z"),
            }

        # get the first page of events
        _, data = self._request(
            connection, "GET", url, params=params, headers=headers, timeout=timeout
        )

        # and then, loop on other pages to get all the events
        events = data.get("value", [])
        next_page_token = data.get("@odata.nextLink")
        while next_page_token:
            _, data = self._request(
                connection, "GET", next_page_token, headers=headers, timeout=timeout
            )
            next_page_token = data.get("@odata.nextLink")
            events += data.get("value", [])

        token_url = data.get("@odata.deltaLink")
        next_sync_token = (
            parse_qs(urlsplit(token_url).query).get("$deltatoken", [False])[0]
            if token_url
            else None
        )

        return events, next_sync_token

    def _check_full_sync_required(self, response) -> bool:
        """Checks if full sync is required according to the error code received."""
        response_json = response.json()
        response_code = response_json.get("error", {}).get("code", "")
        return any(
            error_code in response_code
            for error_code in ["fullSyncRequired", "SyncStateNotFound"]
        )

    @requires_connection
    def _get_events_delta(self, sync_token=None, connection=None, timeout=TIMEOUT):
        """
        Get a set of events that have been added, deleted or updated in a time range.
        See: https://docs.microsoft.com/en-us/graph/api/event-delta?view=graph-rest-1.0&tabs=http
        """
        url = "/v1.0/me/calendarView/delta"
        params = {"$deltatoken": sync_token} if sync_token else None

        try:
            events, next_sync_token = self._get_events_from_paginated_url(
                url, params=params, connection=connection, timeout=timeout
            )
        except requests.HTTPError as e:
            full_sync_needed = self._check_full_sync_required(e.response)
            if e.response.status_code == 410 and full_sync_needed and sync_token:
                raise InvalidSyncToken from e
            raise

        # event occurrences (from a recurrence) are retrieved separately to get all their info,
        # # and mainly the iCalUId attribute which is not provided by the 'get_delta' api end point
        events = [e for e in events if e.get("type") != "occurrence"]

        return MicrosoftEvent(events), next_sync_token

    @requires_connection
    def _get_occurrence_details(self, serieMasterId, connection=None, timeout=TIMEOUT):
        """
        Get all occurrences details from a serie master.
        See: https://docs.microsoft.com/en-us/graph/api/event-list-instances?view=graph-rest-1.0&tabs=http
        """
        url = f"/v1.0/me/events/{serieMasterId}/instances"

        events, _ = self._get_events_from_paginated_url(
            url, connection=connection, timeout=timeout
        )
        return MicrosoftEvent(events)

    @requires_connection
    def get_events(self, sync_token=None, connection=None, timeout=TIMEOUT):
        """
        Retrieve all the events that have changed (added/updated/removed) from Microsoft Outlook.
        This is done in 2 steps:
        1) get main changed events (so single events and serie masters)
        2) get occurrences linked to a serie masters (to retrieve all needed details such as iCalUId)
        """
        events, next_sync_token = self._get_events_delta(
            sync_token=sync_token, connection=connection, timeout=timeout
        )

        # get occurences details for all serie masters
        for master in filter(lambda e: e.type == "seriesMaster", events):
            events |= self._get_occurrence_details(
                master.id, connection=connection, timeout=timeout
            )

        return events, next_sync_token

    @requires_connection
    def insert(self, values, connection=None, timeout=TIMEOUT) -> dict:
        """The event Outlook made of `values`."""
        url = "/v1.0/me/calendar/events"
        _dummy, data = self._request(
            connection, "POST", url, json=values, timeout=timeout
        )
        return data

    @requires_connection
    def patch(self, event_id, values, connection=None, timeout=TIMEOUT) -> dict | None:
        """The event as Outlook holds it after the patch; None when Outlook
        no longer has it."""
        url = "/v1.0/me/calendar/events/%s" % event_id
        status, data = self._request(
            connection, "PATCH", url, json=values, timeout=timeout
        )
        if status in RESOURCE_NOT_FOUND_STATUSES:
            return None
        return data

    @requires_connection
    def delete(self, event_id, connection=None, timeout=TIMEOUT):
        url = "/v1.0/me/calendar/events/%s" % event_id
        try:
            status, _dummy = self._request(connection, "DELETE", url, timeout=timeout)
        except requests.HTTPError as e:
            # For some unknown reason Microsoft can also return a 403 response when the event is already cancelled.
            status = e.response.status_code
            if status in (410, 403):
                _logger.info("Microsoft event %s was already deleted", event_id)
            else:
                raise

        return status not in RESOURCE_NOT_FOUND_STATUSES

    @requires_connection
    def answer(
        self, event_id, answer, values, connection=None, timeout=TIMEOUT
    ) -> bool:
        url = "/v1.0/me/calendar/events/%s/%s" % (event_id, answer)
        status, _dummy = self._request(
            connection, "POST", url, json=values, timeout=timeout
        )

        return status not in RESOURCE_NOT_FOUND_STATUSES
