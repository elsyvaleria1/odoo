import logging
from urllib.parse import parse_qs, urlsplit

import requests

from odoo import fields

from odoo.addons.calendar_microsoft.utils.microsoft_event import MicrosoftEvent
from odoo.addons.calendar_sync.service import (
    CalendarService,
    InvalidSyncToken,
    requires_connection,
)

_logger = logging.getLogger(__name__)

TIMEOUT = 20
RESOURCE_NOT_FOUND_STATUSES = (204, 404)
CALENDAR_SCOPE = "offline_access openid Calendars.ReadWrite"




class MicrosoftCalendarService(CalendarService):
    def _request(
        self, connection, method, path, *, params=None, json=None, headers=None, timeout
    ) -> tuple:
        response = self._response(
            connection,
            method,
            path,
            params=params,
            json=json,
            headers=headers,
            timeout=timeout,
        )
        if response.status_code in RESOURCE_NOT_FOUND_STATUSES:
            return response.status_code, {}
        response.raise_for_status()
        return response.status_code, (response.content and response.json()) or {}

    @requires_connection
    def _get_single_event(self, iCalUId, connection, timeout=TIMEOUT) -> tuple:
        url = "/v1.0/me/events?$filter=iCalUId eq '%s'" % iCalUId
        status, event = self._request(connection, "GET", url, timeout=timeout)
        return status not in RESOURCE_NOT_FOUND_STATUSES, event

    @requires_connection
    def _get_events_from_paginated_url(
        self, url, connection=None, params=None, timeout=TIMEOUT
    ) -> tuple:
        headers = {
            "Prefer": 'outlook.body-content-type="html", odata.maxpagesize=50',
        }
        if not params:
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

        _, data = self._request(
            connection, "GET", url, params=params, headers=headers, timeout=timeout
        )

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
        response_json = response.json()
        response_code = response_json.get("error", {}).get("code", "")
        return any(
            error_code in response_code
            for error_code in ["fullSyncRequired", "SyncStateNotFound"]
        )

    @requires_connection
    def _get_events_delta(self, sync_token=None, connection=None, timeout=TIMEOUT):
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

        events = [e for e in events if e.get("type") != "occurrence"]

        return MicrosoftEvent(events), next_sync_token

    @requires_connection
    def _get_occurrence_details(self, serieMasterId, connection=None, timeout=TIMEOUT):
        url = f"/v1.0/me/events/{serieMasterId}/instances"

        events, _ = self._get_events_from_paginated_url(
            url, connection=connection, timeout=timeout
        )
        return MicrosoftEvent(events)

    @requires_connection
    def get_events(self, sync_token=None, connection=None, timeout=TIMEOUT):
        events, next_sync_token = self._get_events_delta(
            sync_token=sync_token, connection=connection, timeout=timeout
        )

        for master in filter(lambda e: e.type == "seriesMaster", events):
            events |= self._get_occurrence_details(
                master.id, connection=connection, timeout=timeout
            )

        return events, next_sync_token

    @requires_connection
    def insert(self, values, connection=None, timeout=TIMEOUT) -> dict:
        url = "/v1.0/me/calendar/events"
        _dummy, data = self._request(
            connection, "POST", url, json=values, timeout=timeout
        )
        return data

    @requires_connection
    def patch(self, event_id, values, connection=None, timeout=TIMEOUT) -> dict | None:
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
