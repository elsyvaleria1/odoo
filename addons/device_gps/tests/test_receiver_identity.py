import runpy
from pathlib import Path
from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestTrackerReceiverIdentity(DeviceTransactionCase):
    def test_payload_cannot_change_the_admitted_subject(self):
        device = self._create_device_device(identifier="ADMITTED-SUBJECT")
        valid, _message, _device = self.env[
            "device.gps.data.validator"
        ]._check_prerequisites({"14": "another-source"}, device=device)
        self.assertFalse(valid)

    def test_receiver_key_is_independent_of_hardware_imei(self):
        device = self._create_device_device(
            identifier="DISTINCT-IDENTITIES",
            gps_receiver_key="0001234567",
            imei="356938035643809",
        )
        devices = self.env["device.device"]
        self.assertEqual(devices._get_tracker_by_receiver_key("0001234567"), device)
        self.assertFalse(devices._get_tracker_by_receiver_key(device.imei))
        self.assertFalse(devices._get_tracker_by_receiver_key(1234567))
        valid, _message, admitted = self.env[
            "device.gps.data.validator"
        ]._check_prerequisites({"14": "0001234567"}, device=device)
        self.assertTrue(valid)
        self.assertEqual(admitted, device)
        vals = self.env["device.gps.data.processor"]._prepare_log_vals(
            device,
            {"11": "8912345678", "14": "0001234567", "latlng": "19.4,-99.1"},
            history=self.env["device.data.log.gps"],
        )
        self.assertEqual(vals["iccid1"], "8912345678")
        self.assertEqual(vals["iccid2"], "0001234567")
        self.assertNotIn("imei", vals)
        log = self.env["device.data.log.gps"].create(vals)
        self.assertEqual(log.iccid2, "0001234567")
        self.assertEqual(device.imei, "356938035643809")

    def test_ambiguous_and_archived_sources_are_refused(self):
        first = self._create_device_device(
            identifier="KEY-FIRST", gps_receiver_key="1234567890"
        )
        second = self._create_device_device(
            identifier="KEY-SECOND", gps_receiver_key="1234567890"
        )
        devices = self.env["device.device"]
        self.assertFalse(devices._get_tracker_by_receiver_key("1234567890"))
        second.active = False
        self.assertFalse(devices._get_tracker_by_receiver_key("1234567890"))
        probe = devices._probe_integrity(limit=1)["duplicate_gps_receiver_keys"]
        self.assertEqual(probe["ids"], [first.id])
        self.assertTrue(probe["truncated"])
        second.gps_receiver_key = "other-key"
        self.assertEqual(devices._get_tracker_by_receiver_key("1234567890"), first)
        self.assertFalse(devices._get_tracker_by_receiver_key("other-key"))
        copied = first.copy({"identifier": "KEY-COPY"})
        self.assertFalse(copied.gps_receiver_key)

    def test_untrusted_json_key_types_cannot_select_a_subject(self):
        device = self._create_device_device(
            identifier="KEY-TYPES", gps_receiver_key="123"
        )
        devices = self.env["device.device"]
        self.assertEqual(devices._get_tracker_by_receiver_key(123), device)
        for value in (True, False, 123.0, -1, [], {}, None, "", " " * 10, "1" * 129):
            with self.subTest(value=value):
                self.assertFalse(devices._get_tracker_by_receiver_key(value))

    def test_simulator_matches_the_deployed_webhook_and_ack(self):
        simulator_type = runpy.run_path(
            str(Path(__file__).parents[1] / "tools/dev/gps_simulator.py")
        )["GPSSimulator"]
        simulator = simulator_type(
            base_url="https://tracker.invalid",
            receiver_key="0012345678",
            token="test-bearer-token",
        )
        point = simulator.generate_gps_data("2026-09-27T12:30:00+00:00")
        payload = simulator._prepare_webhook_payload(point)["state"]["reported"]
        self.assertEqual(payload["14"], "0012345678")
        self.assertEqual(payload["ts"], 1790512200000)
        self.assertNotIn("imei", payload)
        with patch("requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.content = b"\x01"
            self.assertTrue(simulator.send_data(point))
            self.assertEqual(
                post.call_args.kwargs["json"]["state"]["reported"], payload
            )
            self.assertEqual(
                post.call_args.kwargs["headers"]["Authorization"],
                "Bearer test-bearer-token",
            )
            post.return_value.content = b"\x00"
            self.assertFalse(simulator.send_data(point))
            post.return_value.content = b'{"status": "success"}'
            self.assertFalse(simulator.send_data(point))
