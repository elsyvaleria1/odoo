import base64

from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceHttpCase

_AUDIO = base64.b64encode(b"FAKE-M4A-AUDIO-BYTES").decode()


@tagged("post_install", "-at_install")
class TestMobileRecordingWire(DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.config = cls.env["device.profile"].create(
            {
                "name": "Mobile Rec Config",
                "auth_type": "bearer",
                "auth_token": "rec_token_123",
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Test Phone",
                "identifier": "PHONE-REC-001",
                "config_id": cls.config.id,
                "comm_protocol": "https",
                "endpoint": "companion-app",
                "company_id": cls.company.id,
                "device_category_id": cls.env.ref(
                    "device_mobile.device_category_mobile_phone"
                ).id,
            }
        )
        cls.token = cls.device.credential_id.credential_value

    def _push(self, body, token=None):
        return self.url_open(
            "/remote/mobile/PHONE-REC-001/recording",
            data=json_dumps_bytes(body),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token or self.token}",
            },
        )

    def _recordings(self):
        return self.env["ir.attachment"].search(
            [
                ("res_model", "=", "phone.call"),
                (
                    "res_id",
                    "in",
                    self.env["phone.call"]
                    .search([("device_id", "=", self.device.id)])
                    .ids,
                ),
            ]
        )

    def test_audio_is_not_copied_into_the_event_log(self):
        audio = base64.b64encode(b"\x00" * 200_000).decode()

        response = self._push(
            {
                "number": "5512345678",
                "recorded_at": "2026-07-28T15:30:30",
                "file_name": "long.m4a",
                "mimetype": "audio/mp4",
                "audio_b64": audio,
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._recordings().raw, "the audio itself must be kept")

        event = self.env["integration.exchange"].search(
            [("channel_id", "=", f"device.device,{self.device.id}")],
            order="id desc",
            limit=1,
        )
        self.assertNotIn(audio, event.request_payload)
        self.assertLess(len(event.request_payload), 4096)
        self.assertGreater(event.request_payload_size, len(audio))
        self.assertIn("_omitted", event.request_payload)

    def test_a_capped_endpoint_still_refuses_a_duplicate(self):
        body = {
            "number": "5599998888",
            "recorded_at": "2026-07-28T16:00:00",
            "file_name": "dup.m4a",
            "mimetype": "audio/mp4",
            "audio_b64": base64.b64encode(b"\x01" * 100_000).decode(),
        }

        first = self._push(body)
        second = self._push(body)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(
            len(self._recordings().filtered(lambda r: r.name == "dup.m4a")), 1
        )

    def test_a_recording_resent_after_the_transport_window_is_stored_once(self):
        self.device.sudo().duplicate_detection_enabled = False
        body = {
            "number": "5512345678",
            "recorded_at": "2026-07-28T15:30:20Z",
            "file_name": "retried.m4a",
            "audio_b64": _AUDIO,
        }

        first = self._push(body)
        second = self._push(body)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["recording_id"], first.json()["recording_id"])
        self.assertEqual(second.json()["call_id"], first.json()["call_id"])
        self.assertEqual(first.json()["duplicates"], 0)
        self.assertEqual(second.json()["duplicates"], 1)
        self.assertEqual(
            len(self._recordings().filtered(lambda r: r.name == "retried.m4a")), 1
        )

    def test_another_file_at_the_same_instant_is_its_own_recording(self):
        self.device.sudo().duplicate_detection_enabled = False
        for name in ("left.m4a", "right.m4a"):
            response = self._push(
                {
                    "recorded_at": "2026-07-28T19:00:00Z",
                    "file_name": name,
                    "audio_b64": _AUDIO,
                }
            )
            self.assertEqual(response.json()["duplicates"], 0)
        self.assertEqual(
            len(
                self._recordings().filtered(
                    lambda r: r.name in ("left.m4a", "right.m4a")
                )
            ),
            2,
        )

    def test_a_small_payload_is_still_logged_whole(self):
        response = self.url_open(
            "/remote/mobile/PHONE-REC-001/location",
            data=json_dumps_bytes(
                {"points": [{"latitude": 19.4, "longitude": -99.1, "timestamp": 1}]}
            ),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )

        self.assertEqual(response.status_code, 200)
        event = self.env["integration.exchange"].search(
            [("channel_id", "=", f"device.device,{self.device.id}")],
            order="id desc",
            limit=1,
        )
        self.assertIn("latitude", event.request_payload)
        self.assertEqual(event.request_payload_omitted_bytes, 0)
