import logging
from uuid import uuid4

import requests

from odoo import fields

from odoo.addons.calendar_google.utils.google_event import GoogleEvent
from odoo.addons.calendar_sync.service import (
    CalendarService,
    InvalidSyncToken,
    requires_connection,
)

_logger = logging.getLogger(__name__)

TIMEOUT = 20
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"


class GoogleCalendarService(CalendarService):
    def _request(self, connection, method, path, *, params=None, json=None, timeout):
        """Google's answer, raising requests.HTTPError for a refusal; 204 and 404
        answer nothing."""
        response = self._response(
            connection, method, path, params=params, json=json, timeout=timeout
        )
        if response.status_code in (204, 404):
            return False
        response.raise_for_status()
        return response.json()

    @requires_connection
    def get_events(self, sync_token=None, connection=None, timeout=TIMEOUT):
        url = "/calendar/v3/calendars/primary/events"
        params = {}
        if sync_token:
            params["syncToken"] = sync_token
        else:
            # full sync, limit to a range of 1y in past to 1y in the futur by default
            day_range = int(
                self.env.registry.settings.get(
                    self.env, "calendar_google.sync.range_days", 365
                )
            )
            _logger.info("Full cal sync, restricting to %s days range", day_range)
            lower_bound = fields.Datetime.subtract(
                fields.Datetime.now(), days=day_range
            )
            upper_bound = fields.Datetime.add(fields.Datetime.now(), days=day_range)
            params["timeMin"] = lower_bound.isoformat() + "Z"  # Z = UTC (RFC3339)
            params["timeMax"] = upper_bound.isoformat() + "Z"  # Z = UTC (RFC3339)
        try:
            data = self._request(connection, "GET", url, params=params, timeout=timeout)
        except requests.HTTPError as e:
            if e.response.status_code == 410 and "fullSyncRequired" in str(
                e.response.content
            ):
                raise InvalidSyncToken("Invalid sync token. Full sync required") from e
            raise

        events = data.get("items", [])
        next_page_token = data.get("nextPageToken")
        while next_page_token:
            data = self._request(
                connection,
                "GET",
                url,
                params={"pageToken": next_page_token},
                timeout=timeout,
            )
            next_page_token = data.get("nextPageToken")
            events += data.get("items", [])

        next_sync_token = data.get("nextSyncToken")
        default_reminders = data.get("defaultReminders")

        return GoogleEvent(events), next_sync_token, default_reminders

    @requires_connection
    def insert(self, values, connection=None, timeout=TIMEOUT, need_video_call=True):
        send_updates = self.env.context.get("send_updates", True)
        url = (
            "/calendar/v3/calendars/primary/events?conferenceDataVersion=%d&sendUpdates=%s"
            % (1 if need_video_call else 0, "all" if send_updates else "none")
        )
        if not values.get("id"):
            values["id"] = uuid4().hex
        return self._request(connection, "POST", url, json=values, timeout=timeout)

    @requires_connection
    def patch(self, event_id, values, connection=None, timeout=TIMEOUT):
        send_updates = self.env.context.get("send_updates", True)
        url = (
            "/calendar/v3/calendars/primary/events/%s?sendUpdates=%s&conferenceDataVersion=1"
            % (event_id, "all" if send_updates else "none")
        )
        self._request(connection, "PATCH", url, json=values, timeout=timeout)

    @requires_connection
    def delete(self, event_id, connection=None, timeout=TIMEOUT):
        url = "/calendar/v3/calendars/primary/events/%s?sendUpdates=all" % event_id
        params = {}
        # Delete all events from recurrence in a single request to Google and triggering a single mail.
        # The 'singleEvents' parameter is a trick that tells Google API to delete all recurrent events individually,
        # making the deletion be handled entirely on their side, and then we archive the events in Odoo.
        is_recurrence = self.env.context.get("is_recurrence", True)
        if is_recurrence:
            params["singleEvents"] = "true"
        try:
            self._request(connection, "DELETE", url, params=params, timeout=timeout)
        except requests.HTTPError as e:
            # For some unknown reason Google can also return a 403 response when the event is already cancelled.
            if e.response.status_code not in (410, 403):
                raise
            _logger.info("Google event %s was already deleted", event_id)
