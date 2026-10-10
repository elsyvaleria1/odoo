import contextlib
from unittest.mock import MagicMock, patch

import psycopg

from odoo.libs.json import dumps as json_dumps
from odoo.tests import JsonRpcException, common
from odoo.tools import mute_logger

from ..websocket import CloseCode, InvalidDatabaseError, WebsocketRequest
from .common import WebsocketCase
from odoo.addons.base.tests.common import HttpCaseWithUserDemo


class TestWebsocketController(HttpCaseWithUserDemo):
    def test_has_missed_notifications_rejects_non_integer(self):
        for bad_value in ("1", None, 1.5, [1], {"id": 1}, True):
            with (
                self.subTest(bad_value=bad_value),
                mute_logger("odoo.http"),
                self.assertRaises(JsonRpcException),
            ):
                self.call_jsonrpc(
                    "/bus/has_missed_notifications",
                    {"last_notification_id": bad_value},
                )

    def test_has_missed_notifications_with_integer(self):
        result = self.call_jsonrpc(
            "/bus/has_missed_notifications", {"last_notification_id": 0}
        )
        self.assertTrue(result)

    def test_has_missed_notifications_semantics(self):
        self.env["bus.bus"]._sendone("some_channel", "notif_type", "message")
        self.env.cr.precommit.run()
        notification = self.env["bus.bus"].sudo().search([], order="id desc", limit=1)
        self.assertTrue(notification)
        self.assertFalse(
            self.call_jsonrpc(
                "/bus/has_missed_notifications",
                {"last_notification_id": notification.id},
            ),
            "An existing watermark id must not be reported as missed",
        )
        notification_id = notification.id
        notification.unlink()
        self.assertTrue(
            self.call_jsonrpc(
                "/bus/has_missed_notifications",
                {"last_notification_id": notification_id},
            ),
            "A GC'd watermark id must be reported as missed",
        )


class TestWebsocketWorkerBundle(HttpCaseWithUserDemo):
    def _get_bundle(self, headers=None):
        return self.url_open(
            "/bus/websocket_worker_bundle", headers=headers, allow_redirects=False
        )

    def test_etag_revalidation(self):
        response = self._get_bundle()
        if response.status_code in (301, 302, 303, 307, 308):
            self.skipTest("esbuild unavailable: degraded raw-file path in use")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/javascript", response.headers["Content-Type"])
        etag = response.headers.get("ETag")
        self.assertTrue(etag, "The bundle response must carry an ETag")
        conditional = self._get_bundle(headers={"If-None-Match": etag})
        self.assertEqual(conditional.status_code, 304)
        self.assertFalse(conditional.content)

    def test_another_site_reads_the_same_bundle_without_credentials(self):
        own = self._get_bundle()
        if own.status_code in (301, 302, 303, 307, 308):
            self.skipTest("esbuild unavailable: degraded raw-file path in use")
        response = self.url_open(
            "/bus/websocket_worker_bundle/anonymous",
            headers={"Origin": "https://customer.example"},
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")
        self.assertNotIn("Access-Control-Allow-Credentials", response.headers)
        self.assertNotIn("Set-Cookie", response.headers)
        self.assertEqual(response.content, own.content)

    def test_the_bundle_of_the_page_origin_answers_no_other_origin(self):
        # a worker shared by the tabs is started from the page's own origin;
        # another site reads the anonymous bundle
        for origin in (
            self.base_url(),
            "http://127.0.0.1:8072",
            "https://evil.example",
        ):
            response = self._get_bundle(headers={"Origin": origin})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("Access-Control-Allow-Origin", response.headers)

        response = self._get_bundle()
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)
        self.assertNotIn("Access-Control-Allow-Credentials", response.headers)


@common.tagged("-at_install", "post_install")
class TestInvalidDatabase(WebsocketCase):
    def test_invalid_database_closes_with_try_later(self):
        ws = self.websocket_connect()
        with (
            patch.object(
                WebsocketRequest,
                "serve_websocket_message",
                side_effect=InvalidDatabaseError,
            ),
            mute_logger("odoo.addons.bus.websocket"),
        ):
            ws.send(json_dumps({"event_name": "noop", "data": {}}))
            self.assert_close_with_code(ws, CloseCode.TRY_LATER)

    def test_the_registry_kept_is_the_one_check_signaling_returned(self):
        req = WebsocketRequest.__new__(WebsocketRequest)
        req.db = self.env.registry.db_name
        req.ws = MagicMock()
        req.ws._session = MagicMock()
        req.ws.new_env.return_value.cr.closed = False
        req.ws.new_env.return_value.cr.commit_count = 0
        registry = self.env.registry
        reloaded = MagicMock(db_name=registry.db_name)

        with (
            patch.object(
                WebsocketRequest, "_acquire_session", return_value=MagicMock()
            ),
            patch.object(registry, "check_signaling", return_value=reloaded),
            patch.object(WebsocketRequest, "_serve_ir_websocket", return_value=None),
            contextlib.suppress(Exception),
        ):
            req.serve_websocket_message(json_dumps({"event_name": "noop"}))

        self.assertIs(
            req.registry,
            reloaded,
            "serve_websocket_message kept the registry it called "
            "check_signaling() ON instead of the one it returned",
        )

    def test_registry_failure_maps_to_invalid_database_error(self):
        req = WebsocketRequest.__new__(WebsocketRequest)
        req.db = self.env.registry.db_name
        req.ws = MagicMock()
        req.ws._session = MagicMock()
        registry = self.env.registry
        with (
            patch.object(
                WebsocketRequest, "_acquire_session", return_value=MagicMock()
            ),
            patch.object(
                registry, "check_signaling", side_effect=psycopg.ProgrammingError
            ),
            self.assertRaises(InvalidDatabaseError),
        ):
            req.serve_websocket_message(json_dumps({"event_name": "noop"}))
