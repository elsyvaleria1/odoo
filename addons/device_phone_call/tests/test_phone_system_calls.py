import base64
import logging
from datetime import datetime, timedelta

from odoo import Command, fields
from odoo.tests import counting_statements
from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase
from odoo.addons.device_phone_call.models.phone_call import CALL_LOG_GRACE

_logger = logging.getLogger(__name__)

_AUDIO = base64.b64encode(b"FAKE-OGG-AUDIO-BYTES").decode()
_START = datetime(2026, 10, 5, 10, 0, 0)


def _iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


@tagged("post_install", "-at_install")
class TestPhoneSystemCalls(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls._create_device_profile(name="Phone System Config")
        cls.lmmr = cls.env["res.company"].create(
            {
                "name": "LMMR",
                "phone_ids": [Command.create({"number": "+52 722 555 0101"})],
            }
        )
        cls.xiuman = cls.env["res.company"].create(
            {
                "name": "Xiuman",
                "phone_ids": [Command.create({"number": "+52 722 555 0202"})],
            }
        )
        cls.pbx = cls._create_device_device(
            config=cls.config,
            name="Phone system",
            identifier="PBX-CALLS",
            company_id=cls.lmmr.id,
            device_category_id=cls.env.ref("device_phone_call.device_category_pbx").id,
        )
        cls.calls = cls.env["phone.call"]

    def _entry(self, uid, number, start, seconds=0, direction="incoming", **extra):
        return {
            "uid": uid,
            "number": number,
            "direction": direction,
            "timestamp": _iso(start),
            "duration": seconds,
            **extra,
        }

    def _recording(self, uid, number, recorded_at, seconds=0):
        return {
            "uid": uid,
            "number": number,
            "recorded_at": _iso(recorded_at),
            "duration": seconds,
            "file_name": f"{uid}.ogg",
            "mimetype": "audio/ogg",
            "audio_b64": _AUDIO,
        }

    def _attachments(self, call):
        return self.env["ir.attachment"].search(
            [("res_model", "=", "phone.call"), ("res_id", "=", call.id)]
        )

    def test_a_withheld_callers_recording_stays_on_its_own_call(self):
        created = self.calls.ingest_from_device(
            self.pbx,
            [
                self._entry("1.1", "anonymous", _START, 60),
                self._entry("1.2", "+527221234567", _START + timedelta(seconds=20), 55),
            ],
        ).created
        withheld = created.filtered(lambda call: call.device_call_uid == "1.1")
        ingest = self.calls.store_device_recording(
            self.pbx,
            self._recording("1.1", "anonymous", _START + timedelta(seconds=85), 60),
        )
        self.assertEqual(ingest.call, withheld)
        self.assertTrue(ingest.matched)

    def test_a_voicemail_finds_its_call_however_long_the_message(self):
        voicemail = self.calls.ingest_from_device(
            self.pbx, [self._entry("2.1", "+527221234567", _START, 0, "voicemail")]
        ).created
        ingest = self.calls.store_device_recording(
            self.pbx,
            self._recording("2.1", "+527221234567", _START + timedelta(seconds=131)),
        )
        self.assertEqual(ingest.call, voicemail)
        self.assertFalse(
            self.calls.search(
                [("device_id", "=", self.pbx.id), ("awaits_call_log", "=", True)]
            )
        )

    def test_a_resent_recording_is_stored_once(self):
        self.calls.ingest_from_device(
            self.pbx, [self._entry("3.1", "+527221234567", _START, 30)]
        )
        payload = self._recording(
            "3.1", "+527221234567", _START + timedelta(seconds=40)
        )
        first = self.calls.store_device_recording(self.pbx, payload)
        second = self.calls.store_device_recording(self.pbx, payload)
        self.assertTrue(second.duplicate)
        self.assertEqual(second.attachment, first.attachment)

    def test_a_recording_ahead_of_its_entry_is_completed_by_the_entry_naming_it(self):
        ahead = self.calls.store_device_recording(
            self.pbx,
            self._recording("4.1", "+527221234567", _START + timedelta(seconds=40)),
        )
        self.assertTrue(ahead.call.awaits_call_log)
        entry = self.calls.ingest_from_device(
            self.pbx,
            [self._entry("4.1", "+527221234567", _START, 30, line="+527225550202")],
        ).created
        self.assertEqual(entry, ahead.call)
        self.assertFalse(entry.awaits_call_log)
        self.assertEqual(entry.company_id, self.xiuman)
        self.assertEqual(
            self._attachments(entry).company_id,
            self.xiuman,
            "the recording follows its call to the company whose line it reached",
        )

    def test_two_withheld_callers_in_the_same_second_are_two_calls(self):
        same_second = [
            {
                "number": "anonymous",
                "direction": "missed",
                "timestamp": _iso(_START),
                "line": line,
            }
            for line in ("+527225550101", "+527225550202")
        ]
        ingest = self.calls.ingest_from_device(self.pbx, same_second)
        self.assertEqual(len(ingest.created), 2)
        self.assertEqual(ingest.duplicates, 0)

    def test_a_call_resent_under_its_uid_is_a_duplicate(self):
        entry = self._entry("5.1", "+527221234567", _START, 30)
        self.calls.ingest_from_device(self.pbx, [entry])
        again = self.calls.ingest_from_device(
            self.pbx, [{**entry, "timestamp": _iso(_START + timedelta(seconds=1))}]
        )
        self.assertFalse(again.created)
        self.assertEqual(again.duplicates, 1)

    def test_a_phone_system_never_matches_a_numberless_recording_by_time(self):
        self.calls.ingest_from_device(
            self.pbx,
            [
                {
                    "number": "+527221234567",
                    "direction": "incoming",
                    "timestamp": _iso(_START),
                    "duration": 60,
                }
            ],
        )
        payload = self._recording("", "", _START + timedelta(seconds=60))
        ingest = self.calls.store_device_recording(self.pbx, payload)
        self.assertFalse(ingest.matched)
        self.assertTrue(ingest.call.awaits_call_log)

    def test_a_line_two_companies_share_stays_with_the_devices_company(self):
        self.xiuman.write(
            {"phone_ids": [Command.create({"number": "+52 722 555 0101"})]}
        )
        created = self.calls.ingest_from_device(
            self.pbx,
            [
                {
                    "number": "+527221234567",
                    "direction": "incoming",
                    "timestamp": _iso(_START),
                    "line": "+527225550101",
                }
            ],
        ).created
        self.assertEqual(created.company_id, self.lmmr)

    def test_a_handset_names_neither_a_line_nor_another_company(self):
        handset = self._create_device_device(
            config=self.config,
            name="Handset",
            identifier="HANDSET-CALLS",
            company_id=self.lmmr.id,
        )
        created = self.calls.ingest_from_device(
            handset,
            [
                {
                    "number": "+527221234567",
                    "direction": "incoming",
                    "timestamp": _iso(_START),
                    "line": "+527225550202",
                }
            ],
        ).created
        self.assertEqual(created.company_id, self.lmmr)

    def test_the_hourly_join_reads_each_devices_calls_once(self):
        handset = self._create_device_device(
            config=self.config,
            name="Handset",
            identifier="HANDSET-WAITING",
            company_id=self.lmmr.id,
        )
        waiting = self.calls.browse()
        for minute in range(30):
            waiting |= self.calls._create_awaiting_call(
                handset,
                f"+52722123{minute:04d}",
                _START + timedelta(minutes=minute),
                30,
            )
        self.env.cr.execute(
            "UPDATE phone_call SET create_date = %s WHERE id = ANY(%s)",
            (
                fields.Datetime.now() - CALL_LOG_GRACE - timedelta(minutes=1),
                waiting.ids,
            ),
        )
        self.env.flush_all()
        self.env.invalidate_all()

        with counting_statements(self.env.cr) as counted:
            self.calls._cron_complete_awaiting_calls()
            self.env.flush_all()
            statements = counted.count
        _logger.debug("joining 30 waiting calls took %d statements", statements)

        self.assertLessEqual(statements, 5)

    def test_a_recording_and_its_entry_crossing_are_joined_later(self):
        handset = self._create_device_device(
            config=self.config,
            name="Handset",
            identifier="HANDSET-CROSS",
            company_id=self.lmmr.id,
        )
        reported = self.calls.ingest_from_device(
            handset,
            [
                {
                    "number": "+527221234567",
                    "direction": "incoming",
                    "timestamp": _iso(_START),
                    "duration": 30,
                }
            ],
        ).created
        waiting = self.calls._create_awaiting_call(
            handset, "+527221234567", _START + timedelta(seconds=40), 30
        )
        attachment = self.env["ir.attachment"].create(
            {
                "name": "crossed.m4a",
                "mimetype": "audio/mp4",
                "datas": _AUDIO,
                "res_model": "phone.call",
                "res_id": waiting.id,
            }
        )
        waiting._file_recording(attachment, 0, 30000)
        self.env.cr.execute(
            "UPDATE phone_call SET create_date = %s WHERE id = %s",
            (fields.Datetime.now() - CALL_LOG_GRACE - timedelta(minutes=1), waiting.id),
        )
        self.env.invalidate_all()
        self.calls._cron_complete_awaiting_calls()
        self.assertFalse(waiting.exists())
        self.assertEqual(self._attachments(reported), attachment)
        segment = self.env["media.segment"].search(
            [("attachment_id", "=", attachment.id)]
        )
        timeline = reported._recording_timeline()
        self.assertEqual(
            (segment.res_model, segment.res_id), (timeline._name, timeline.id)
        )
