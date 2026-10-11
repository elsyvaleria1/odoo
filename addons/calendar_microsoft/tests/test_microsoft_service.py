from unittest.mock import MagicMock, call, patch

import requests

from odoo import fields
from odoo.libs.guarded_http import GuardedSession
from odoo.tests import TransactionCase

from odoo.addons.calendar_microsoft.tests.common import authorize_microsoft_calendar
from odoo.addons.calendar_microsoft.utils.calendar_microsoft import (
    MicrosoftCalendarService,
)
from odoo.addons.calendar_microsoft.utils.microsoft_event import MicrosoftEvent
from odoo.addons.calendar_sync.models.res_users import ResUsers as CalendarSyncUsers
from odoo.addons.calendar_sync.service import InvalidSyncToken

DEFAULT_TIMEOUT = 20


class _UnexpectedError(Exception):
    pass


class TestMicrosoftService(TransactionCase):
    def _do_request_result(self, data):
        return (200, data)

    def setUp(self):
        super().setUp()

        self.service = MicrosoftCalendarService(self.env)
        self.fake_connection = "MY_CONNECTION"
        self.fake_sync_token = "MY_SYNC_TOKEN"
        self.fake_next_sync_token = "MY_NEXT_SYNC_TOKEN"
        self.fake_next_sync_token_url = f"https://graph.microsoft.com/v1.0/me/calendarView/delta?$deltatoken={self.fake_next_sync_token}"

        self.prefer = {
            "Prefer": 'outlook.body-content-type="html", odata.maxpagesize=50'
        }
        self.call_with_sync_token = call(
            self.fake_connection,
            "GET",
            "/v1.0/me/calendarView/delta",
            params={"$deltatoken": self.fake_sync_token},
            headers=self.prefer,
            timeout=DEFAULT_TIMEOUT,
        )
        self.call_without_sync_token = call(
            self.fake_connection,
            "GET",
            "/v1.0/me/calendarView/delta",
            params={
                "startDateTime": fields.Datetime.subtract(
                    fields.Datetime.now(), days=365
                ).strftime("%Y-%m-%dT00:00:00Z"),
                "endDateTime": fields.Datetime.add(
                    fields.Datetime.now(), days=365 * 2
                ).strftime("%Y-%m-%dT00:00:00Z"),
            },
            headers=self.prefer,
            timeout=DEFAULT_TIMEOUT,
        )

    def test_get_events_delta_without_token(self):
        with self.assertRaises(AttributeError):
            self.service._get_events_delta()

    @patch.object(MicrosoftCalendarService, "_request")
    def test_get_events_unexpected_exception(self, mock_do_request):
        mock_do_request.side_effect = _UnexpectedError()

        with self.assertRaises(_UnexpectedError):
            self.service._get_events_delta(
                connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
            )

    @patch.object(MicrosoftCalendarService, "_check_full_sync_required")
    @patch.object(MicrosoftCalendarService, "_request")
    def test_get_events_delta_token_error(
        self, mock_do_request, mock_check_full_sync_required
    ):
        mock_do_request.side_effect = [
            requests.HTTPError(
                response=MagicMock(status_code=410, content="fullSyncRequired")
            ),
        ]
        mock_check_full_sync_required.return_value = True

        with self.assertRaises(InvalidSyncToken):
            self.service._get_events_delta(
                connection=self.fake_connection,
                sync_token=self.fake_sync_token,
                timeout=DEFAULT_TIMEOUT,
            )
        mock_do_request.assert_has_calls([self.call_with_sync_token])

    @patch.object(MicrosoftCalendarService, "_request")
    def test_get_events_delta_without_sync_token(self, mock_do_request):
        mock_do_request.return_value = self._do_request_result({"value": []})

        events, next_token = self.service._get_events_delta(
            connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
        )

        self.assertEqual(next_token, None)
        self.assertFalse(events)
        mock_do_request.assert_has_calls([self.call_without_sync_token])

    @patch.object(MicrosoftCalendarService, "_request")
    def test_get_events_delta_with_sync_token(self, mock_do_request):
        mock_do_request.return_value = self._do_request_result(
            {"value": [], "@odata.deltaLink": self.fake_next_sync_token_url}
        )

        events, next_token = self.service._get_events_delta(
            connection=self.fake_connection,
            sync_token=self.fake_sync_token,
            timeout=DEFAULT_TIMEOUT,
        )

        self.assertEqual(next_token, "MY_NEXT_SYNC_TOKEN")
        self.assertFalse(events)
        mock_do_request.assert_has_calls([self.call_with_sync_token])

    @patch.object(MicrosoftCalendarService, "_request")
    def test_get_events_one_page(self, mock_do_request):
        mock_do_request.return_value = self._do_request_result(
            {
                "value": [
                    {"id": 1, "type": "singleInstance", "subject": "ev1"},
                    {"id": 2, "type": "singleInstance", "subject": "ev2"},
                    {"id": 3, "type": "singleInstance", "subject": "ev3"},
                ],
            }
        )
        events, _ = self.service._get_events_delta(
            connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
        )

        self.assertEqual(
            events,
            MicrosoftEvent(
                [
                    {"id": 1, "type": "singleInstance", "subject": "ev1"},
                    {"id": 2, "type": "singleInstance", "subject": "ev2"},
                    {"id": 3, "type": "singleInstance", "subject": "ev3"},
                ]
            ),
        )
        mock_do_request.assert_has_calls([self.call_without_sync_token])

    @patch.object(MicrosoftCalendarService, "_request")
    def test_get_events_loop_over_pages(self, mock_do_request):
        mock_do_request.side_effect = [
            self._do_request_result(
                {
                    "value": [{"id": 1, "type": "singleInstance", "subject": "ev1"}],
                    "@odata.nextLink": "link_1",
                }
            ),
            self._do_request_result(
                {
                    "value": [{"id": 2, "type": "singleInstance", "subject": "ev2"}],
                    "@odata.nextLink": "link_2",
                }
            ),
            self._do_request_result(
                {
                    "value": [{"id": 3, "type": "singleInstance", "subject": "ev3"}],
                }
            ),
        ]

        events, _ = self.service._get_events_delta(
            connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
        )

        self.assertEqual(
            events,
            MicrosoftEvent(
                [
                    {"id": 1, "type": "singleInstance", "subject": "ev1"},
                    {"id": 2, "type": "singleInstance", "subject": "ev2"},
                    {"id": 3, "type": "singleInstance", "subject": "ev3"},
                ]
            ),
        )
        mock_do_request.assert_has_calls(
            [
                self.call_without_sync_token,
                call(
                    self.fake_connection,
                    "GET",
                    "link_1",
                    headers=self.prefer,
                    timeout=DEFAULT_TIMEOUT,
                ),
                call(
                    self.fake_connection,
                    "GET",
                    "link_2",
                    headers=self.prefer,
                    timeout=DEFAULT_TIMEOUT,
                ),
            ]
        )

    @patch.object(MicrosoftCalendarService, "_request")
    def test_get_events_filter_out_occurrences(self, mock_do_request):
        mock_do_request.return_value = self._do_request_result(
            {
                "value": [
                    {"id": 1, "type": "singleInstance", "subject": "ev1"},
                    {"id": 2, "type": "occurrence", "subject": "ev2"},
                    {"id": 3, "type": "seriesMaster", "subject": "ev3"},
                ],
            }
        )
        events, _ = self.service._get_events_delta(
            connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
        )

        self.assertEqual(
            events,
            MicrosoftEvent(
                [
                    {"id": 1, "type": "singleInstance", "subject": "ev1"},
                    {"id": 3, "type": "seriesMaster", "subject": "ev3"},
                ]
            ),
        )
        mock_do_request.assert_has_calls([self.call_without_sync_token])

    def test_get_occurrence_details_token_error(self):
        with self.assertRaises(AttributeError):
            self.service._get_occurrence_details(1)

    @patch.object(MicrosoftCalendarService, "_request")
    def test_get_occurrence_details(self, mock_do_request):
        mock_do_request.return_value = self._do_request_result(
            {
                "value": [
                    {"id": 1, "type": "singleInstance", "subject": "ev1"},
                    {"id": 2, "type": "occurrence", "subject": "ev2"},
                    {"id": 3, "type": "seriesMaster", "subject": "ev3"},
                ],
            }
        )
        events = self.service._get_occurrence_details(
            123, connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
        )

        self.assertEqual(
            events,
            MicrosoftEvent(
                [
                    {"id": 1, "type": "singleInstance", "subject": "ev1"},
                    {"id": 2, "type": "occurrence", "subject": "ev2"},
                    {"id": 3, "type": "seriesMaster", "subject": "ev3"},
                ]
            ),
        )

        mock_do_request.assert_called_with(
            self.fake_connection,
            "GET",
            "/v1.0/me/events/123/instances",
            params={
                "startDateTime": fields.Datetime.subtract(
                    fields.Datetime.now(), days=365
                ).strftime("%Y-%m-%dT00:00:00Z"),
                "endDateTime": fields.Datetime.add(
                    fields.Datetime.now(), days=365 * 2
                ).strftime("%Y-%m-%dT00:00:00Z"),
            },
            headers=self.prefer,
            timeout=DEFAULT_TIMEOUT,
        )

    def test_get_events_token_error(self):
        with self.assertRaises(AttributeError):
            self.service.get_events()

    @patch.object(MicrosoftCalendarService, "_request")
    def test_get_events_no_serie_master(self, mock_do_request):
        mock_do_request.return_value = self._do_request_result(
            {
                "value": [
                    {"id": 1, "type": "singleInstance", "subject": "ev1"},
                    {"id": 2, "type": "singleInstance", "subject": "ev2"},
                    {"id": 3, "type": "singleInstance", "subject": "ev3"},
                ],
            }
        )

        events, _ = self.service.get_events(
            connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
        )

        self.assertEqual(
            events,
            MicrosoftEvent(
                [
                    {"id": 1, "type": "singleInstance", "subject": "ev1"},
                    {"id": 2, "type": "singleInstance", "subject": "ev2"},
                    {"id": 3, "type": "singleInstance", "subject": "ev3"},
                ]
            ),
        )

    @patch.object(MicrosoftCalendarService, "_request")
    def test_get_events_with_one_serie_master(self, mock_do_request):
        mock_do_request.side_effect = [
            self._do_request_result(
                {
                    "value": [
                        {"id": 1, "type": "singleInstance", "subject": "ev1"},
                        {"id": 2, "type": "seriesMaster", "subject": "ev2"},
                    ],
                }
            ),
            self._do_request_result(
                {
                    "value": [
                        {"id": 3, "type": "occurrence", "subject": "ev3"},
                    ],
                }
            ),
        ]

        events, _ = self.service.get_events(
            connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
        )

        self.assertEqual(
            events,
            MicrosoftEvent(
                [
                    {"id": 1, "type": "singleInstance", "subject": "ev1"},
                    {"id": 2, "type": "seriesMaster", "subject": "ev2"},
                    {"id": 3, "type": "occurrence", "subject": "ev3"},
                ]
            ),
        )

    def test_insert_token_error(self):
        with self.assertRaises(AttributeError):
            self.service.insert({})

    @patch.object(MicrosoftCalendarService, "_request")
    def test_insert(self, mock_do_request):

        mock_do_request.return_value = self._do_request_result({"id": 1, "iCalUId": 2})

        event = self.service.insert(
            {"subject": "ev1"}, connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
        )

        self.assertEqual(event, {"id": 1, "iCalUId": 2})
        mock_do_request.assert_called_with(
            self.fake_connection,
            "POST",
            "/v1.0/me/calendar/events",
            json={"subject": "ev1"},
            timeout=DEFAULT_TIMEOUT,
        )

    def test_patch_token_error(self):
        with self.assertRaises(AttributeError):
            self.service.patch(123, {})

    @patch.object(MicrosoftCalendarService, "_request")
    def test_a_refused_patch_raises(self, mock_do_request):
        mock_do_request.side_effect = requests.HTTPError(
            response=MagicMock(status_code=400)
        )
        with self.assertRaises(requests.HTTPError):
            self.service.patch(
                "123", {}, connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
            )

    @patch.object(MicrosoftCalendarService, "_request")
    def test_patch_returns_false_if_event_does_not_exist(self, mock_do_request):
        event_id = 123
        values = {"subject": "ev2"}
        mock_do_request.return_value = (404, {})

        res = self.service.patch(
            event_id, values, connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
        )

        self.assertIsNone(res)
        mock_do_request.assert_called_with(
            self.fake_connection,
            "PATCH",
            f"/v1.0/me/calendar/events/{event_id}",
            json=values,
            timeout=DEFAULT_TIMEOUT,
        )

    @patch.object(MicrosoftCalendarService, "_request")
    def test_patch_an_existing_event(self, mock_do_request):
        event_id = 123
        values = {"subject": "ev2"}
        mock_do_request.return_value = (200, {"id": "123", "changeKey": "ck2"})

        res = self.service.patch(
            event_id, values, connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
        )

        self.assertEqual(res, {"id": "123", "changeKey": "ck2"})
        mock_do_request.assert_called_with(
            self.fake_connection,
            "PATCH",
            f"/v1.0/me/calendar/events/{event_id}",
            json=values,
            timeout=DEFAULT_TIMEOUT,
        )

    def test_delete_token_error(self):
        with self.assertRaises(AttributeError):
            self.service.delete(123)

    @patch.object(MicrosoftCalendarService, "_request")
    def test_delete_returns_false_if_event_does_not_exist(self, mock_do_request):
        event_id = 123
        mock_do_request.return_value = (404, {})

        res = self.service.delete(
            event_id, connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
        )

        self.assertFalse(res)
        mock_do_request.assert_called_with(
            self.fake_connection,
            "DELETE",
            f"/v1.0/me/calendar/events/{event_id}",
            timeout=DEFAULT_TIMEOUT,
        )

    @patch.object(MicrosoftCalendarService, "_request")
    def test_delete_an_already_cancelled_event(self, mock_do_request):
        event_id = 123

        for status in (403, 410):
            mock_do_request.return_value = (status, {})

            res = self.service.delete(
                event_id, connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
            )

            self.assertTrue(res)
            mock_do_request.assert_called_with(
                self.fake_connection,
                "DELETE",
                f"/v1.0/me/calendar/events/{event_id}",
                timeout=DEFAULT_TIMEOUT,
            )

    @patch.object(MicrosoftCalendarService, "_request")
    def test_delete_an_existing_event(self, mock_do_request):
        event_id = 123
        mock_do_request.return_value = (200, {})

        res = self.service.delete(
            event_id, connection=self.fake_connection, timeout=DEFAULT_TIMEOUT
        )

        self.assertTrue(res)
        mock_do_request.assert_called_with(
            self.fake_connection,
            "DELETE",
            f"/v1.0/me/calendar/events/{event_id}",
            timeout=DEFAULT_TIMEOUT,
        )

    def test_answer_token_error(self):
        with self.assertRaises(AttributeError):
            self.service.answer(123, "ok", {})

    @patch.object(MicrosoftCalendarService, "_request")
    def test_answer_returns_false_if_event_does_not_exist(self, mock_do_request):
        event_id = 123
        answer = "accept"
        values = {"a": 1, "b": 2}
        mock_do_request.return_value = (404, {})

        res = self.service.answer(
            event_id,
            answer,
            values,
            connection=self.fake_connection,
            timeout=DEFAULT_TIMEOUT,
        )

        self.assertFalse(res)
        mock_do_request.assert_called_with(
            self.fake_connection,
            "POST",
            f"/v1.0/me/calendar/events/{event_id}/{answer}",
            json=values,
            timeout=DEFAULT_TIMEOUT,
        )

    @patch.object(MicrosoftCalendarService, "_request")
    def test_answer_to_an_existing_event(self, mock_do_request):
        event_id = 123
        answer = "decline"
        values = {"a": 1, "b": 2}
        mock_do_request.return_value = (200, {})

        res = self.service.answer(
            event_id,
            answer,
            values,
            connection=self.fake_connection,
            timeout=DEFAULT_TIMEOUT,
        )

        self.assertTrue(res)
        mock_do_request.assert_called_with(
            self.fake_connection,
            "POST",
            f"/v1.0/me/calendar/events/{event_id}/{answer}",
            json=values,
            timeout=DEFAULT_TIMEOUT,
        )

    @patch.object(MicrosoftCalendarService, "_check_full_sync_required")
    @patch.object(MicrosoftCalendarService, "_request")
    @patch.object(
        CalendarSyncUsers,
        "_calendar_sync_connection",
        lambda user, code: code == "microsoft" and "MY_CONNECTION",
    )
    def test_get_events_delta_with_outdated_sync_token(
        self, mock_do_request, mock_check_full_sync_required
    ):
        mock_do_request.side_effect = [
            requests.HTTPError(
                response=MagicMock(status_code=410, error={"code": "SyncStateNotFound"})
            ),
            self._do_request_result({"value": []}),
        ]
        mock_check_full_sync_required.return_value = True
        account = self.env.user._calendar_sync_account("microsoft")
        account.sync_token = self.fake_sync_token

        changes, __ = account._as_engine()._read()

        self.assertTrue(changes.full)
        mock_do_request.assert_has_calls(
            [self.call_with_sync_token, self.call_without_sync_token]
        )

    def test_a_refresh_goes_to_the_services_token_endpoint(self):
        service = self.env.ref("integration_microsoft.service_microsoft")
        service._set_oauth_client("dummy_client_id", "dummy_secret", company=False)
        tenant_endpoint = (
            "https://login.microsoftonline.com/dummy_tenant_id/oauth2/v2.0/token"
        )
        service.oauth_token_endpoint = tenant_endpoint
        connection = authorize_microsoft_calendar(self.env.user)
        response = MagicMock(ok=True, status_code=200, headers={})
        response.json.return_value = {
            "access_token": "fresh_access_token",
            "expires_in": 3599,
        }

        with patch.object(GuardedSession, "request", return_value=response) as sent:
            token = connection._oauth2_access_token(force=True)

        self.assertEqual(token, "fresh_access_token")
        self.assertEqual(sent.call_args.args[1], tenant_endpoint)
        self.assertEqual(sent.call_args.kwargs["data"]["scope"], connection.oauth_scope)
