from odoo.exceptions import UserError
from odoo.libs.documents import CUES
from odoo.tests import tagged

from .common import SpeechCase, StubTranscription
from odoo.addons.speech.tools.hear import hear


@tagged("post_install", "-at_install")
class TestFileMedia(SpeechCase):
    def _job(self, attachment):
        return self.env["ir.job"].search(
            [("identity_key", "=", f"reading.{CUES}.{attachment.id}")]
        )

    def test_a_recording_follows_what_the_timeline_holds(self):
        self._register(StubTranscription())
        recording = self._recording()
        first = recording._file_media(self._audio("a.mp3"), 0, 2000)
        second = recording._file_media(self._audio("b.mp3"), end_ms=None)
        self.assertEqual((first.start_ms, first.end_ms), (0, 2000))
        self.assertEqual(second.start_ms, 2000)
        self.assertEqual(second.end_ms, 2001, "unreadable length: one millisecond")

    def test_a_filed_recording_is_queued_to_be_heard(self):
        self._register(StubTranscription())
        recording = self._recording()
        attachment = self._audio()
        recording._file_media(attachment, 0, 1000)
        self.assertEqual(attachment.transcript_state, "queued")
        self.assertEqual(self._job(attachment).channel, "speech")

    def test_without_an_engine_it_is_filed_and_not_queued(self):
        recording = self._recording()
        attachment = self._audio()
        segment = recording._file_media(attachment, 0, 1000)
        self.assertTrue(segment)
        self.assertEqual(attachment.transcript_state, "none")
        self.assertFalse(self._job(attachment))

    def test_the_timeline_reads_as_one_document(self):
        self._register(StubTranscription())
        recording = self._recording()
        attachment = self._audio()
        recording._file_media(attachment, 0, 3000)
        attachment._transcribe()
        document = recording._as_timeline_document("Agenda: invoices")
        self.assertTrue(document.text.startswith("Agenda: invoices\n\n"))
        self.assertIn("the invoice went out", document.text)
        self.assertIn("Alice: on Tuesday", document.text)


@tagged("post_install", "-at_install")
class TestHear(SpeechCase):
    def test_what_is_heard_is_kept_nowhere(self):
        engine = self._register(StubTranscription())
        attachments = self.env["ir.attachment"].search_count([])
        cues = hear(self.env, b"voice-note", mimetype="audio/mpeg", language="es")
        self.assertEqual(cues[0].text, "the invoice went out")
        self.assertEqual(engine.calls[-1].options["language"], "es")
        self.assertEqual(self.env["ir.attachment"].search_count([]), attachments)

    def test_an_engine_failure_is_said(self):
        self._register(StubTranscription(error=RuntimeError("vendor down")))
        with self.assertRaisesRegex(UserError, "vendor down"):
            hear(self.env, b"voice-note", mimetype="audio/mpeg")

    def test_nothing_to_hear_without_an_engine(self):
        with self.assertRaisesRegex(UserError, "No speech engine may hear"):
            hear(self.env, b"voice-note", mimetype="audio/mpeg")
