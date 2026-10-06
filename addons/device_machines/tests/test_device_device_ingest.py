from datetime import UTC

from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests import tagged

from .common import DeviceMachinesCommon


@tagged("post_install", "-at_install")
class TestRemoteDeviceIngest(DeviceMachinesCommon):
    def _payload(self, machine="Llenadora", count=100, frac="000000000"):
        return {
            machine: {
                "Time Stamp": f"2026-06-18-14:00:05.{frac}",
                "Maquina": machine,
                "Conteo": count,
            }
        }

    def test_plc_clock_default_does_not_follow_the_creator_timezone(self):
        self.env.user.tz = "Asia/Tokyo"
        device = self._make_counter_device("Neutral clock", "neutral-clock")
        self.assertEqual(device.counter_timezone, "UTC")

    def test_is_counter_device(self):
        self.assertTrue(self.device.is_counter_device)

    def test_parse_plc_timestamp_truncates_ns_to_us(self):
        ts = self.device._parse_plc_timestamp("2026-06-18-14:00:05.123456789")

        self.assertEqual(ts.microsecond, 123456)
        self.assertEqual(ts.tzinfo, UTC)

    def test_parse_plc_timestamp_converts_from_plc_clock(self):
        self.device.counter_timezone = "America/Mexico_City"

        ts = self.device._parse_plc_timestamp("2026-06-18-14:00:05")

        self.assertEqual((ts.year, ts.month, ts.day), (2026, 6, 18))
        self.assertEqual((ts.hour, ts.minute, ts.second), (20, 0, 5))
        self.assertEqual(ts.tzinfo, UTC)

    def test_parse_plc_timestamp_utc_clock_is_not_shifted(self):
        self.device.counter_timezone = "UTC"

        ts = self.device._parse_plc_timestamp("2026-06-18-14:00:05")

        self.assertEqual((ts.hour, ts.minute, ts.second), (14, 0, 5))

    def test_parse_plc_timestamp_honours_zone_dst(self):
        self.device.counter_timezone = "America/Chicago"

        summer = self.device._parse_plc_timestamp("2026-06-18-14:00:00")
        winter = self.device._parse_plc_timestamp("2026-01-18-14:00:00")

        self.assertEqual(summer.hour, 19)
        self.assertEqual(winter.hour, 20)

    def test_parse_plc_timestamp_invalid_raises(self):
        with self.assertRaises(ValueError):
            self.device._parse_plc_timestamp("not-a-timestamp")

    def test_first_payload_records_a_reading_without_a_bucket(self):
        bucket = self.device._ingest_counter_payload(self._payload(count=100))

        self.assertFalse(bucket)
        self.assertEqual(self.device.last_count, 100)
        self.assertEqual(
            self.env["device.machine.reading"].search_count(
                [("device_id", "=", self.device.id)]
            ),
            1,
        )

    def test_ingest_creates_bucket_and_reading(self):
        self.device._ingest_counter_payload(self._payload(count=100))

        bucket = self.device._ingest_counter_payload(
            self._payload(count=160, frac="500000000")
        )

        self.assertTrue(bucket)
        self.assertEqual(bucket.count_start, 100)
        self.assertEqual(bucket.count_end, 160)
        self.assertEqual(bucket.delta, 60)
        self.assertEqual(self.device.last_count, 160)
        self.assertEqual(
            self.env["device.machine.reading"].search_count(
                [("device_id", "=", self.device.id)]
            ),
            2,
        )

    def test_ingest_is_idempotent_on_duplicate_timestamp(self):
        self.device._ingest_counter_payload(self._payload(count=100))
        again = self.device._ingest_counter_payload(self._payload(count=100))

        self.assertFalse(again)
        self.assertEqual(
            self.env["device.machine.reading"].search_count(
                [("device_id", "=", self.device.id)]
            ),
            1,
        )

    def test_ingest_ignores_other_machine(self):
        bucket = self.device._ingest_counter_payload(
            self._payload(machine="Etiquetadora", count=50)
        )

        self.assertFalse(bucket)

    def test_ingest_drops_invalid_payload(self):
        self.assertFalse(self.device._ingest_counter_payload({}))
        self.assertFalse(self.device._ingest_counter_payload({"Llenadora": "nope"}))


@tagged("post_install", "-at_install")
class TestCounterStream(DeviceMachinesCommon):
    def _payload(self, count):
        return {
            "Llenadora": {
                "Time Stamp": f"2026-06-18-14:00:{count % 60:02d}.000000000",
                "Maquina": "Llenadora",
                "Conteo": count,
            }
        }

    def test_the_counter_s_stream_subscribes_at_qos_one(self):
        self.assertEqual(self.device.stream_id.options["qos"], 1)

    def test_the_certificate_and_the_authority_ride_the_stream(self):
        certificate = self.env["certificate.certificate"].create({"name": "plc client"})
        authority = self.env["certificate.certificate"].create({"name": "root ca"})
        self.device.certificate_id = certificate
        self.config.ca_certificate_id = authority
        stream = self.device.stream_id
        self.assertEqual(
            (stream.certificate_id, stream.ca_certificate_id), (certificate, authority)
        )

    def test_a_counter_frame_feeds_the_aggregator_not_the_raw_log(self):
        stream = self.device.stream_id
        self.device._on_stream_frame(
            stream, json_dumps_bytes(self._payload(100)), {"topic": "plc/llenadora"}
        )
        self.device._on_stream_frame(
            stream, json_dumps_bytes(self._payload(130)), {"topic": "plc/llenadora"}
        )
        self.assertEqual(self.device.last_count, 130)
        self.assertEqual(
            self.env["device.machine.reading"].search_count(
                [("device_id", "=", self.device.id)]
            ),
            2,
        )
        self.assertFalse(
            self.env["device.data.log"].search([("device_id", "=", self.device.id)])
        )

    def test_an_undecodable_frame_is_dropped(self):
        self.device._on_stream_frame(self.device.stream_id, b"\xff{", {})
        self.assertEqual(self.device.last_count, 0)

    def test_a_plain_mqtt_device_keeps_the_raw_log(self):
        device = self._make_counter_device("Scale", "SCALE-1", device_category_id=False)
        device._on_stream_frame(device.stream_id, b'{"kg": 1}', {"topic": "s"})
        self.assertTrue(
            self.env["device.data.log"].search([("device_id", "=", device.id)])
        )
