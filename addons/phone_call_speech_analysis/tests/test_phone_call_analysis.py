from unittest.mock import patch

from odoo.libs.documents import register_reader, unregister_reader
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.phone_call.tests.test_phone_call_recording import StubTranscription


@tagged("post_install", "-at_install")
class TestPhoneCallAnalysis(TransactionCase):
    def setUp(self):
        super().setUp()
        engine = register_reader(StubTranscription())
        self.addCleanup(unregister_reader, engine)
        self.call = self.env["phone.call"].create(
            {"phone_number": "+525512345678", "user_id": self.env.user.id}
        )

    def _transcribe_a_recording(self):
        recording = self.env["ir.attachment"].create(
            {"name": "call.mp3", "mimetype": "audio/mpeg", "raw": b"audio"}
        )
        self.call._add_media_segment(recording, 0, 3000)
        with patch.object(type(self.call), "_extract_later", autospec=True) as queued:
            recording._transcribe()
        return queued

    def test_an_ended_call_is_analysed_once_transcribed(self):
        self.call.sudo().end_date = "2026-09-21 10:00:00"
        self.assertTrue(self._transcribe_a_recording().called)

    def test_a_call_still_going_waits(self):
        self._transcribe_a_recording().assert_not_called()

    def test_the_call_reads_as_a_speech_analysis_document(self):
        self.assertEqual(self.call._extract_document_type, "speech_analysis")
        self.assertIn("analysis_summary", self.call._fields)

    def test_the_call_reads_as_its_spoken_lines(self):
        self.call.sudo().end_date = "2026-09-21 10:00:00"
        self._transcribe_a_recording()
        self.assertIn("thanks for calling", self.call._get_extract_source().text)
