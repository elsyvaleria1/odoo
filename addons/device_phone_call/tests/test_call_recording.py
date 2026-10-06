import base64
from datetime import datetime, timedelta

from odoo import fields
from odoo.libs.documents import (
    CUES,
    METERED,
    BaseReader,
    Cue,
    register_reader,
    unregister_reader,
)
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceHttpCase
from odoo.addons.device_phone_call.models.phone_call import CALL_LOG_GRACE

_AUDIO = base64.b64encode(b"FAKE-M4A-AUDIO-BYTES").decode()


class _Hears(BaseReader):
    name = "device_phone_call_stub"
    mimetypes = frozenset({"audio/mp4"})
    yields = (CUES,)
    cost = METERED

    def read(self, document):
        return [Cue(0.0, 2.0, "le mando la cotización", "SPEAKER_0")]


@tagged("post_install", "-at_install")
class TestDeviceCallRecording(DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.config = cls.env["device.profile"].create(
            {
                "name": "Recording Config",
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
            }
        )
        cls.token = cls.device.credential_id.credential_value
        cls.calls = cls.env["phone.call"]
        cls.call = cls.calls.ingest_from_device(
            cls.device,
            [
                {
                    "number": "5512345678",
                    "direction": "incoming",
                    "timestamp": "2026-07-28T15:30:00",
                }
            ],
        ).created

    def setUp(self):
        super().setUp()
        engine = register_reader(_Hears())
        self.addCleanup(unregister_reader, engine)

    def _push(self, body, token=None):
        return self.url_open(
            "/remote/device/PHONE-REC-001/recording",
            data=json_dumps_bytes(body),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token or self.token}",
            },
        )

    def _recording(self, call):
        return self.env["ir.attachment"].search(
            [("res_model", "=", "phone.call"), ("res_id", "=", call.id)]
        )

    def _job(self, attachment):
        return self.env["ir.job"].search(
            [("identity_key", "=", f"reading.cues.{attachment.id}")]
        )

    def _awaiting(self):
        return self.calls.search(
            [("device_id", "=", self.device.id), ("awaits_call_log", "=", True)]
        )

    def test_a_recording_is_filed_on_its_call(self):
        resp = self._push(
            {
                "audio_b64": _AUDIO,
                "number": "5512345678",
                "recorded_at": "2026-07-28T15:30:20Z",
                "duration": 42,
                "file_name": "call.m4a",
            }
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["matched"])
        self.assertEqual(body["call_id"], self.call.id)
        recording = self._recording(self.call)
        self.assertEqual(recording.name, "call.m4a")
        self.assertEqual(recording.raw, b"FAKE-M4A-AUDIO-BYTES")
        self.assertEqual(self.call._recording_timeline().media_duration_ms, 42000)
        self.assertEqual(self._job(recording).state, "pending")

    def test_a_numbered_recording_matches_a_call_longer_than_the_window(self):
        # The dialer stamps the file when the call ends, which for any call over
        # a minute is outside a window drawn around the call's start.
        self.call.sudo().end_date = datetime(2026, 7, 28, 15, 35, 0)
        resp = self._push(
            {
                "audio_b64": _AUDIO,
                "number": "5512345678",
                "recorded_at": "2026-07-28T15:35:00Z",
                "file_name": "call_5512345678.m4a",
            }
        )
        self.assertEqual(resp.json()["call_id"], self.call.id)

    def test_a_recording_without_number_matches_the_call_by_time(self):
        # Samsung names the file after the contact, so the app sends no number;
        # the stamp falls at the end of the 42 s call.
        self.call.sudo().end_date = datetime(2026, 7, 28, 15, 30, 42)
        resp = self._push(
            {
                "audio_b64": _AUDIO,
                "recorded_at": "2026-07-28T15:30:45Z",
                "file_name": "Llamada Cliente Prueba_260728_153045.m4a",
            }
        )
        self.assertTrue(resp.json()["matched"])
        self.assertEqual(resp.json()["call_id"], self.call.id)

    def test_a_recording_ahead_of_its_call_log_waits_for_it(self):
        resp = self._push(
            {
                "audio_b64": _AUDIO,
                "number": "5566666666",
                "recorded_at": "2026-07-28T18:00:40Z",
                "duration": 35,
                "file_name": "call.m4a",
            }
        )
        self.assertFalse(resp.json()["matched"])
        waiting = self._awaiting()
        self.assertEqual(waiting.id, resp.json()["call_id"])
        self.assertEqual(waiting.phone_number, "5566666666")
        recording = self._recording(waiting)
        job = self._job(recording)
        self.assertEqual(job.state, "scheduled")
        self.assertGreater(
            job.eta, fields.Datetime.now() + CALL_LOG_GRACE - timedelta(minutes=2)
        )

        ingest = self.calls.ingest_from_device(
            self.device,
            [
                {
                    "number": "5566666666",
                    "direction": "outgoing",
                    "timestamp": "2026-07-28T18:00:00Z",
                    "duration": 35,
                    "contact_name": "Don Chuy",
                }
            ],
        )

        self.assertEqual(ingest.created, waiting, "the entry completed the call")
        self.assertFalse(waiting.awaits_call_log)
        self.assertEqual((waiting.direction, waiting.state), ("outgoing", "terminated"))
        self.assertEqual(waiting.contact_name, "Don Chuy")
        self.assertEqual(waiting.start_date, datetime(2026, 7, 28, 18, 0, 0))
        self.assertEqual(self._job(recording).state, "pending")

    def test_a_numberless_recording_is_adopted_by_the_call_that_spans_it(self):
        resp = self._push(
            {
                "audio_b64": _AUDIO,
                "recorded_at": "2026-07-28T17:10:00",
                "file_name": "Llamada Otro Cliente_260728_171000.m4a",
            }
        )
        waiting = self.calls.browse(resp.json()["call_id"])
        self.assertTrue(waiting.awaits_call_log)
        self.assertFalse(waiting.phone_number)

        self.calls.ingest_from_device(
            self.device,
            [
                {
                    "number": "5588888888",
                    "direction": "outgoing",
                    "timestamp": "2026-07-28T17:08:30",
                    "duration": 80,
                }
            ],
        )

        self.assertFalse(waiting.awaits_call_log)
        self.assertEqual(waiting.phone_number, "5588888888")

    def test_an_entry_far_from_any_waiting_recording_is_a_call_of_its_own(self):
        self._push(
            {
                "audio_b64": _AUDIO,
                "number": "5577777777",
                "recorded_at": "2026-07-28T19:00:00",
            }
        )
        ingest = self.calls.ingest_from_device(
            self.device,
            [
                {
                    "number": "5577777777",
                    "direction": "incoming",
                    "timestamp": "2026-07-28T21:00:00",
                    "duration": 10,
                }
            ],
        )
        self.assertTrue(ingest.created)
        self.assertTrue(self._awaiting(), "the recording still waits for its entry")

    def test_no_audio_rejected(self):
        resp = self._push({"number": "5512345678"})
        self.assertEqual(resp.status_code, 400)

    def test_bad_token_rejected(self):
        resp = self._push({"audio_b64": _AUDIO, "number": "5512345678"}, token="nope")
        self.assertEqual(resp.status_code, 401)
