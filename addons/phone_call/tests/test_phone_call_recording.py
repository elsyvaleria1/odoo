from odoo.libs.documents import (
    CUES,
    METERED,
    RECORDING_MIMETYPES,
    BaseReader,
    Cue,
    register_reader,
    unregister_reader,
)
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


class StubTranscription(BaseReader):
    name = "stub_phone_call_transcription"
    mimetypes = RECORDING_MIMETYPES
    yields = (CUES,)
    cost = METERED

    def read(self, document):
        return [Cue(0.0, 3.0, "thanks for calling", "")]


@tagged("post_install", "-at_install")
class TestPhoneCallRecording(TransactionCase):
    def setUp(self):
        super().setUp()
        engine = register_reader(StubTranscription())
        self.addCleanup(unregister_reader, engine)
        self.call = self.env["phone.call"].create(
            {"phone_number": "+525512345678", "user_id": self.env.user.id}
        )

    def _recording(self):
        return self.env["ir.attachment"].create(
            {"name": "call.mp3", "mimetype": "audio/mpeg", "raw": b"audio"}
        )

    def test_a_phone_call_is_a_media_timeline(self):
        for field in (
            "segment_ids",
            "timeline_transcript",
            "media_duration_ms",
            "has_media",
        ):
            self.assertIn(field, self.env["phone.call"]._fields)

    def test_a_recording_becomes_a_segment_of_the_call(self):
        self.call._add_media_segment(self._recording(), 0, 30000)
        self.assertEqual(self.call.media_duration_ms, 30000)
        self.assertTrue(self.call.has_media)

    def test_a_transcribed_call_reads_back(self):
        segment = self.call._add_media_segment(self._recording(), 0, 30000)
        segment.attachment_id._transcribe()
        self.assertEqual(self.call.timeline_transcript, "thanks for calling")
        self.assertEqual(self.call.timeline_transcript_state, "done")

    def test_what_was_said_on_the_phone_is_searchable(self):
        segment = self.call._add_media_segment(self._recording(), 0, 30000)
        segment.attachment_id._transcribe()
        found = self.env["ir.attachment"].search(
            [
                ("id", "=", segment.attachment_id.id),
                ("index_content", "ilike", "calling"),
            ]
        )
        self.assertEqual(found, segment.attachment_id)

    def test_the_uploaded_span_is_the_length_of_the_recording(self):
        segment = self.call._file_recording(self._recording(), 0, 90500)
        self.assertEqual((segment.start_ms, segment.end_ms), (0, 90500))
        self.assertEqual(self.call._recording_timeline().media_duration_ms, 90500)

    def test_an_upload_without_a_span_still_files_a_segment(self):
        segment = self.call._file_recording(self._recording(), 0)
        self.assertEqual((segment.start_ms, segment.end_ms), (0, 1))
