import base64
import os
from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests
from requests.auth import HTTPDigestAuth

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.libs import sealing
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests.common import TransactionCase, tagged


def _response(status_code=200, body=b"<DeviceInfo/>", content_type="application/xml"):
    response = MagicMock()
    response.status_code = status_code
    response.headers = {"Content-Type": content_type}
    response.content = body
    response.text = body.decode()
    response.raise_for_status.return_value = None
    return response


@tagged("post_install", "-at_install")
class DeviceTransportCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        key_patcher = patch.dict(
            os.environ,
            sealing.rotated_environ("7ftr9ALjwK7f4IqWwnpFxWx4Wn8vetsznoGT3Oh46eU="),
        )
        key_patcher.start()
        cls.addClassCleanup(key_patcher.stop)

        cls.credential = cls.env["credential.credential"].create(
            {
                "name": "Panel operator",
                "category_id": cls.env.ref(
                    "credential.credential_category_basic_auth"
                ).id,
                "username": "admin",
                "password": "panel-pass",
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Door under test",
                "identifier": "TRANSPORT-DOOR",
                "config_id": cls.env.ref(
                    "device_access_control.device_profile_isapi_access"
                ).id,
                "is_demo": True,
                "access_connection_mode": "direct",
                "endpoint": "192.168.1.50",
                "dial_credential_id": cls.credential.id,
            }
        )


class TestDirectIsapiKeepsItsAuthAndCertificateExemption(DeviceTransportCommon):
    def test_the_panel_is_still_addressed_with_digest_auth(self):
        with patch.object(
            requests.Session, "request", return_value=_response()
        ) as mocked:
            self.device._isapi_direct("GET", "/ISAPI/System/deviceInfo")

        self.assertIsInstance(mocked.call_args.kwargs["auth"], HTTPDigestAuth)

    def test_the_self_signed_certificate_is_still_tolerated(self):
        with patch.object(
            requests.Session, "request", return_value=_response()
        ) as mocked:
            self.device._isapi_direct("GET", "/ISAPI/System/deviceInfo")

        self.assertFalse(mocked.call_args.kwargs["verify"])

    def test_the_device_body_and_status_survive_an_error(self):
        with patch.object(
            requests.Session,
            "request",
            return_value=_response(401, b"<Error>bad nonce</Error>"),
        ):
            with self.assertRaises(UserError) as caught:
                self.device._isapi_direct("GET", "/ISAPI/System/deviceInfo")

        self.assertIn("401", str(caught.exception))
        self.assertIn("bad nonce", str(caught.exception))


class TestTheCertificateExemptionIsBounded(DeviceTransportCommon):
    def test_a_device_on_a_public_address_is_refused(self):
        self.device.endpoint = "8.8.8.8"

        with patch.object(requests.Session, "request", return_value=_response()):
            with self.assertRaises(UserError) as caught:
                self.device._isapi_direct("GET", "/ISAPI/System/deviceInfo")
        message = str(caught.exception)
        self.assertIn("private-network", message)
        self.assertIn("8.8.8.8", message, "name the host that was refused")
        self.assertNotIn(
            "Cannot connect",
            message,
            "a refusal to send must not read as a network failure",
        )

    def test_the_service_record_cannot_be_repointed_at_a_public_host(self):
        service = self.env.ref("device_access_control.service_isapi_device")

        with self.assertRaises(ValidationError):
            service.endpoint_url = "https://panels.example.com"

    def test_a_private_address_still_works(self):
        with patch.object(requests.Session, "request", return_value=_response()):
            self.device._isapi_direct("GET", "/ISAPI/System/deviceInfo")


class TestEhomeExchangesAreAudited(DeviceTransportCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.device.write(
            {
                "access_connection_mode": "ehome",
                "ehome_bridge_url": "http://192.168.1.9:8085",
                "ehome_device_id": "EHOME-PANEL-1",
            }
        )

    def _rows(self):
        self.env.cr.precommit.run()
        return self.env["integration.exchange"].search(
            [("channel_id", "like", "integration.service")], order="id desc"
        )

    def test_a_door_command_is_recorded(self):
        before = len(self._rows())
        reply = _response(200, b'{"result": "ok"}', "application/json")
        reply.json.return_value = {"result": "ok"}

        with patch.object(requests.Session, "request", return_value=reply):
            self.device._door_command("open")

        self.assertGreater(len(self._rows()), before, "the exchange must be audited")

    def test_a_bridge_error_reaches_the_operator(self):
        reply = _response(500, b'{"error": "device offline"}', "application/json")
        reply.json.return_value = {"error": "device offline"}

        with patch.object(requests.Session, "request", return_value=reply):
            with self.assertRaises(UserError) as caught:
                self.device._door_command("open")

        self.assertIn("device offline", str(caught.exception))


class TestEhomeBridgeContract(DeviceTransportCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.device.write(
            {
                "access_connection_mode": "ehome",
                "ehome_bridge_url": "http://192.168.1.9:8085",
                "ehome_device_id": "EHOME-PANEL-1",
            }
        )

    def _call(self, action):
        envelope = {"result": "ok", "response": base64.b64encode(b"<ok/>").decode()}
        reply = _response(200, json_dumps(envelope).encode(), "application/json")
        reply.json.return_value = envelope
        with patch.object(requests.Session, "request", return_value=reply) as mocked:
            action()
        return mocked.call_args.kwargs

    def test_a_door_command_names_the_panel_and_bounds_its_wait(self):
        sent = self._call(lambda: self.device._door_command("open"))

        self.assertEqual(sent["url"], "http://192.168.1.9:8085/api/door/open")
        self.assertEqual(sent["headers"]["X-Device-ID"], "EHOME-PANEL-1")
        self.assertEqual(sent["headers"]["X-ISAPI-Timeout"], "10")
        self.assertEqual(sent["timeout"], 15)

    def test_an_isapi_call_hands_the_bridge_its_timeout_and_waits_longer(self):
        sent = self._call(
            lambda: self.device._isapi_request(
                "POST", "/ISAPI/x", data=b"{}", timeout=60
            )
        )

        self.assertEqual(sent["url"], "http://192.168.1.9:8085/api/isapi")
        self.assertEqual(sent["headers"]["X-ISAPI-Timeout"], "60")
        self.assertEqual(sent["headers"]["X-ISAPI-Method"], "POST")
        self.assertEqual(sent["timeout"], 65)

    def test_a_binary_body_is_sent_as_is(self):
        body = b"--B\r\n\xff\xd8\xff\xe0\x00\x10JFIF\r\n--B--\r\n"
        sent = self._call(
            lambda: self.device._isapi_request(
                "PUT",
                "/ISAPI/x",
                data=body,
                content_type="multipart/form-data; boundary=B",
            )
        )

        self.assertEqual(sent["data"], body)


class TestEhomeAnswersAreUnwrapped(DeviceTransportCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.device.write(
            {
                "access_connection_mode": "ehome",
                "ehome_bridge_url": "http://192.168.1.9:8085",
                "ehome_device_id": "EHOME-PANEL-1",
            }
        )

    def _answer(self, envelope):
        body = json_dumps(envelope).encode()
        reply = _response(200, body, "application/json")
        reply.json.return_value = json_loads(body)
        with patch.object(requests.Session, "request", return_value=reply):
            return self.device._isapi_request("GET", "/ISAPI/x")

    def _panel_says(self, content):
        return self._answer(
            {
                "result": "ok",
                "response": base64.b64encode(content).decode(),
                "encoding": "base64",
            }
        )

    def test_each_kind_of_answer_carries_its_type(self):
        cases = {
            b"<DeviceInfo/>": "application/xml",
            b'{"UserInfoSearch": {}}': "application/json",
            b"\xff\xd8\xff\xe0\x00\x10JFIF": "image/jpeg",
            b"--MIME\r\nContent-Type: image/jpeg\r\n\r\n\xff\xd8": (
                "multipart/form-data; boundary=MIME"
            ),
            b"\x00\x01": "application/octet-stream",
        }
        for content, content_type in cases.items():
            with self.subTest(content_type=content_type):
                answer = self._panel_says(content)
                self.assertEqual(answer.content, content)
                self.assertEqual(answer.headers["Content-Type"], content_type)

    def test_an_answer_without_the_panels_response_is_an_error(self):
        for envelope in ({"result": "ok"}, {"response": "not base64!"}, ["ok"]):
            with self.subTest(envelope=envelope):
                with self.assertRaises(UserError):
                    self._answer(envelope)


class TestEachPanelHasItsOwnConnection(DeviceTransportCommon):
    def test_a_direct_panel_is_connected_at_its_address_with_its_login(self):
        connection = self.device.sudo().connection_id

        self.assertEqual(
            connection.service_id,
            self.env.ref("device_access_control.service_isapi_device"),
        )
        self.assertEqual(connection.base_url, "https://192.168.1.50")
        self.assertEqual(connection.credential_id, self.credential)
        self.assertEqual(connection.name, "Door under test")

    def test_the_call_goes_to_the_panels_own_address(self):
        with patch.object(
            requests.Session, "request", return_value=_response()
        ) as mocked:
            self.device._isapi_direct("GET", "/ISAPI/System/deviceInfo")

        self.assertEqual(
            mocked.call_args.kwargs["url"],
            "https://192.168.1.50/ISAPI/System/deviceInfo",
        )

    def test_moving_the_panel_moves_its_connection(self):
        connection = self.device.sudo().connection_id

        self.device.endpoint = "192.168.1.60"

        self.assertEqual(self.device.sudo().connection_id, connection)
        self.assertEqual(connection.base_url, "https://192.168.1.60")

    def test_switching_to_ehome_connects_the_panel_through_its_bridge(self):
        direct = self.device.sudo().connection_id

        self.device.write(
            {
                "access_connection_mode": "ehome",
                "ehome_bridge_url": "http://192.168.1.9:8085",
                "ehome_device_id": "EHOME-PANEL-1",
            }
        )

        connection = self.device.sudo().connection_id
        self.assertEqual(connection, direct, "the panel's connection row is its own")
        self.assertEqual(
            connection.service_id,
            self.env.ref("device_access_control.service_ehome_bridge"),
        )
        self.assertEqual(connection.base_url, "http://192.168.1.9:8085")
        self.assertFalse(connection.credential_id)

    def test_a_login_bound_to_another_service_cannot_open_a_panel(self):
        other = self.env["integration.service"].create(
            {"name": "Elsewhere", "code": "elsewhere", "endpoint_url": "https://x.test"}
        )
        login = self.env["credential.credential"].create(
            {
                "name": "Bound login",
                "category_id": self.env.ref(
                    "credential.credential_category_basic_auth"
                ).id,
                "username": "admin",
                "password": "elsewhere-pass",
                "endpoint_id": other.id,
            }
        )

        with self.assertRaises(ValidationError):
            self.device.dial_credential_id = login

    def test_deleting_the_panel_deletes_its_connection(self):
        connection = self.device.sudo().connection_id

        self.device.unlink()

        self.assertFalse(connection.exists())


class TestEhomeStatusAsksEachBridge(DeviceTransportCommon):
    def test_panels_on_two_bridges_are_checked_on_their_own_bridge(self):
        self.device.write(
            {
                "device_category_id": self.env.ref(
                    "device_access_control.device_kind_access_control"
                ).id,
                "access_connection_mode": "ehome",
                "ehome_bridge_url": "http://192.168.1.9:8085",
                "ehome_device_id": "EHOME-PANEL-1",
            }
        )
        self.device.copy(
            {
                "identifier": "TRANSPORT-DOOR-2",
                "ehome_bridge_url": "http://192.168.2.9:8085",
                "ehome_device_id": "EHOME-PANEL-2",
            }
        )
        reply = _response(200, b'{"devices": {}}', "application/json")
        reply.json.return_value = {"devices": {}}

        with patch.object(requests.Session, "request", return_value=reply) as mocked:
            self.env["device.device"]._cron_check_ehome_status()

        called = {call.kwargs["url"] for call in mocked.call_args_list}
        self.assertIn("http://192.168.1.9:8085/api/devices", called)
        self.assertIn("http://192.168.2.9:8085/api/devices", called)


class TestEhomeStatusFollowsTheBridge(DeviceTransportCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.device.write(
            {
                "device_category_id": cls.env.ref(
                    "device_access_control.device_kind_access_control"
                ).id,
                "access_connection_mode": "ehome",
                "ehome_bridge_url": "http://192.168.1.9:8085",
                "ehome_device_id": "EHOME-PANEL-1",
            }
        )

    def _cron(self, connected=None, error=None):
        reply = _response(200, b"{}", "application/json")
        reply.json.return_value = {"devices": connected or {}}
        with patch.object(
            requests.Session, "request", return_value=reply, side_effect=error
        ):
            self.env["device.device"]._cron_check_ehome_status()

    def test_a_listed_panel_counts_as_heard_from(self):
        hour_ago = fields.Datetime.now() - timedelta(hours=1)
        self.device.write(
            {"connection_state": "connected", "date_last_data_received": hour_ago}
        )
        self._cron({"EHOME-PANEL-1": 0})

        self.assertEqual(self.device.connection_state, "connected")
        self.assertGreater(self.device.date_last_data_received, hour_ago)

    def test_a_panel_in_error_recovers_once_the_bridge_answers(self):
        self.device.connection_state = "error"
        self._cron({})
        self.assertEqual(self.device.connection_state, "disconnected")

        self.device.connection_state = "error"
        self._cron({"EHOME-PANEL-1": 0})
        self.assertEqual(self.device.connection_state, "connected")

    def test_an_unreachable_bridge_puts_its_panels_in_error(self):
        self.device.connection_state = "connected"
        self._cron(error=requests.ConnectionError("refused"))
        self.assertEqual(self.device.connection_state, "error")


class TestPollingAPanelChecksIt(DeviceTransportCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.device.write(
            {
                "device_category_id": cls.env.ref(
                    "device_access_control.device_kind_access_control"
                ).id,
                "access_connection_mode": "ehome",
                "ehome_bridge_url": "http://192.168.1.9:8085",
                "ehome_device_id": "EHOME-PANEL-1",
                "serial_number": "SN-1",
                "device_model": "DS-K1T341",
            }
        )

    def _poll(self, connected):
        reply = _response(200, b"{}", "application/json")
        reply.json.return_value = {"devices": connected}
        with patch.object(requests.Session, "request", return_value=reply) as mocked:
            self.device.action_read_data()
        return [call.kwargs["url"] for call in mocked.call_args_list]

    def test_polling_an_ehome_panel_asks_the_bridge_for_its_device_list(self):
        called = self._poll({"EHOME-PANEL-1": 0})

        self.assertEqual(called, ["http://192.168.1.9:8085/api/devices"])
        self.assertEqual(self.device.connection_state, "connected")

    def test_a_panel_the_bridge_does_not_list_is_polled_as_disconnected(self):
        called = self._poll({"EHOME-PANEL-2": 0})

        self.assertEqual(called, ["http://192.168.1.9:8085/api/devices"])
        self.assertEqual(self.device.connection_state, "disconnected")
