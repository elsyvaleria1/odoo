from unittest.mock import Mock, patch

import requests

from odoo.libs.guarded_http import GuardedSession
from odoo.tests import TransactionCase

REQUEST_MODULE = "odoo.addons.web_map.models.res_config_settings.request"


class TestCheckMapBoxToken(TransactionCase):
    """Cover the extracted MapBox HTTP probe in isolation, no network involved."""

    def test_returns_the_response_status_code(self):
        settings = self.env["res.config.settings"].new()
        response = Mock(status_code=200)

        with patch.object(
            GuardedSession, "request", return_value=response
        ) as head_mock:
            error_code = settings._check_map_box_token("url", {"a": "b"}, {"c": "d"})

        self.assertEqual(error_code, 200)
        head_mock.assert_called_once_with(
            "HEAD", "url", headers={"a": "b"}, params={"c": "d"}, timeout=5
        )

    def test_a_request_exception_is_reported_as_500(self):
        settings = self.env["res.config.settings"].new()

        with patch.object(
            GuardedSession,
            "request",
            side_effect=requests.exceptions.ConnectionError(),
        ):
            error_code = settings._check_map_box_token("url", {}, {})

        self.assertEqual(error_code, 500)


class TestMapBoxTokenOnchange(TransactionCase):
    """Cover _onchange_map_box_token's warning/reset behavior, MapBox mocked out.

    `request` (werkzeug's context-local proxy) can't be auto-mocked by
    @patch's default decorator form outside an HTTP request context (its own
    introspection touches the unbound proxy), so every patch below passes an
    explicit `new=` Mock instead of relying on autospec.
    """

    def _settings_with_token(self, token):
        return self.env["res.config.settings"].new({"map_box_token": token})

    def _request_mock(self, referer):
        request_mock = Mock()
        request_mock.httprequest.headers.environ.get.return_value = referer
        return request_mock

    def test_valid_token_is_kept_with_no_warning(self):
        settings = self._settings_with_token("good-token")

        with (
            patch(REQUEST_MODULE, new=self._request_mock("https://example.com")),
            patch.object(type(settings), "_check_map_box_token", return_value=200),
        ):
            result = settings._onchange_map_box_token()

        self.assertIsNone(result)
        self.assertEqual(settings.map_box_token, "good-token")

    def test_invalid_token_is_reset_with_a_warning(self):
        settings = self._settings_with_token("bad-token")

        with (
            patch(REQUEST_MODULE, new=self._request_mock("https://example.com")),
            patch.object(type(settings), "_check_map_box_token", return_value=401),
        ):
            result = settings._onchange_map_box_token()

        self.assertEqual(settings.map_box_token, "")
        self.assertEqual(result["warning"]["message"], "The token input is not valid")

    def test_unauthorized_referer_is_reset_with_a_warning(self):
        settings = self._settings_with_token("restricted-token")

        with (
            patch(REQUEST_MODULE, new=self._request_mock("https://example.com")),
            patch.object(type(settings), "_check_map_box_token", return_value=403),
        ):
            result = settings._onchange_map_box_token()

        self.assertEqual(settings.map_box_token, "")
        self.assertEqual(result["warning"]["message"], "This referer is not authorized")

    def test_unreachable_server_is_reset_with_a_warning(self):
        settings = self._settings_with_token("token")

        with (
            patch(REQUEST_MODULE, new=self._request_mock("https://example.com")),
            patch.object(type(settings), "_check_map_box_token", return_value=500),
        ):
            result = settings._onchange_map_box_token()

        self.assertEqual(settings.map_box_token, "")
        self.assertEqual(
            result["warning"]["message"], "The MapBox server is unreachable"
        )

    def test_present_referer_header_is_forwarded(self):
        settings = self._settings_with_token("token")

        with (
            patch(REQUEST_MODULE, new=self._request_mock("https://example.com")),
            patch.object(
                type(settings), "_check_map_box_token", return_value=200
            ) as check_mock,
        ):
            settings._onchange_map_box_token()

        headers = check_mock.call_args.args[1]
        self.assertEqual(headers.get("referer"), "https://example.com")

    def test_missing_referer_header_is_not_sent(self):
        settings = self._settings_with_token("token")

        with (
            patch(REQUEST_MODULE, new=self._request_mock(None)),
            patch.object(
                type(settings), "_check_map_box_token", return_value=200
            ) as check_mock,
        ):
            settings._onchange_map_box_token()

        headers = check_mock.call_args.args[1]
        self.assertNotIn("referer", headers)
