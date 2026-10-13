import contextlib
import unittest

from odoo.libs.documents import (
    CUES,
    METERED,
    TEXT,
    BaseReader,
    Cue,
    can_decode_media,
    register_reader,
    unregister_reader,
)
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.extract.tools import FREE, GENERATIVE, BaseExtractor
from odoo.addons.extract.tools import extractors as registry
from odoo.addons.extract.tools.schema import FieldSpec, register_schema

AUDIO = "audio/mpeg"
SCAN = "application/x-extract-scan"


class _Hears(BaseReader):
    name = "extract_test_hears"
    mimetypes = frozenset({AUDIO})
    yields = (CUES,)
    cost = METERED
    async_only = True

    def __init__(self, error=None):
        self.reads = 0
        self.error = error

    def read(self, document):
        self.reads += 1
        if self.error:
            raise self.error
        return [Cue(0.0, 2.0, "invoice A7 for 116 pesos", "SPEAKER_0")]


class _Recognises(BaseReader):
    name = "extract_test_recognises"
    mimetypes = frozenset({SCAN})
    yields = (TEXT,)
    cost = METERED

    def __init__(self):
        self.reads = 0

    def read(self, document):
        self.reads += 1
        return "invoice A7 for 116 pesos"


class _Words(BaseExtractor):
    name = "every_binary_words"
    doc_types = ("every_binary",)
    needs = ("text",)
    cost = FREE
    confidence = 0.9

    def extract(self, source, doc_type, wanted, env=None):
        if "A7" not in source.text:
            return None
        return {"reference": "A7", "total": 116.0}


class _Looks(BaseExtractor):
    name = "every_binary_looks"
    doc_types = ("every_binary",)
    needs = ("images",)
    cost = GENERATIVE
    confidence = 0.8

    def __init__(self):
        self.pages = 0

    def extract(self, source, doc_type, wanted, env=None):
        self.pages = len(source.images)
        return {"reference": "FRAME", "total": 1.0}


@contextlib.contextmanager
def _only(*extractors):
    saved = dict(registry._EXTRACTORS)
    registry._EXTRACTORS.clear()
    try:
        for extractor in extractors:
            registry.register_extractor(extractor)
        yield
    finally:
        registry._EXTRACTORS.clear()
        registry._EXTRACTORS.update(saved)


@tagged("post_install", "-at_install")
class TestEveryBinary(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.extract.tools import schema as schema_mod

        if "every_binary" not in schema_mod._SCHEMAS:
            register_schema(
                "every_binary",
                {
                    "reference": FieldSpec("str", required=True),
                    "total": FieldSpec("float", required=True),
                },
            )

    def _reader(self, reader):
        register_reader(reader)
        self.addCleanup(unregister_reader, reader)
        return reader

    def _file(self, raw, mimetype, name):
        return self.env["ir.attachment"].create(
            {
                "name": name,
                "raw": raw,
                "mimetype": mimetype,
                "extract_document_type": "every_binary",
            }
        )

    def _jobs(self, key):
        return self.env["ir.job"].sudo().search([("identity_key", "=", key)])

    def test_a_recording_waits_for_its_transcript_then_is_read_from_it(self):
        hears = self._reader(_Hears())
        recording = self._file(b"ID3-a-call", AUDIO, "call.mp3")
        with _only(_Words()):
            recording.action_extract()
            self.assertEqual(recording.extract_state, "waiting")
            self.assertEqual(hears.reads, 0, "nothing is transcribed inline")
            self.assertEqual(recording.extract_pending["readings"], [CUES])
            reading_job = self._jobs(f"reading.{CUES}.{recording.id}")
            follow_up = self._jobs(
                f"extract.ir.attachment.{recording.id}.after_readings"
            )
            self.assertEqual(follow_up.state, "wait_deps")
            self.assertIn(reading_job, follow_up.depends_on_ids)

            recording._read(CUES)
            recording._extract_document(allow_pending=True)

        self.assertEqual(recording.extract_state, "done")
        self.assertEqual(recording.extract_result["reference"]["value"], "A7")
        self.assertEqual(hears.reads, 1, "the transcript was paid for once")
        self.assertFalse(recording.extract_pending)

    def test_a_reading_that_failed_is_not_waited_on_forever(self):
        self._reader(_Hears(error=RuntimeError("vendor down")))
        recording = self._file(b"ID3-a-call", AUDIO, "call.mp3")
        recording._read(CUES)
        with _only(_Words()):
            recording._extract_document(allow_pending=True)
        self.assertEqual(recording.extract_state, "partial")

    def test_recognised_text_is_kept_for_the_next_reader(self):
        recognises = self._reader(_Recognises())
        scan = self._file(b"%scan-bytes", SCAN, "scan.bin")
        with _only(_Words()):
            scan._extract_document(allow_pending=True)
            self.assertEqual(scan.extract_state, "done")
            self.assertEqual(scan._reading(TEXT).read_by, "extract_test_recognises")
            self.assertIn("A7", scan.index_content)
            scan._extract_document(allow_pending=True)
        self.assertEqual(recognises.reads, 1)

    @unittest.skipUnless(can_decode_media(), "PyAV is not installed")
    def test_a_video_is_looked_at_through_its_frames(self):
        from odoo.tests.media_recordings import prepare_recording_bytes

        video = self._file(prepare_recording_bytes(), "video/x-matroska", "clip.mkv")
        looks = _Looks()
        with _only(looks):
            video.action_extract()
        self.assertEqual(video.extract_state, "done")
        self.assertGreater(looks.pages, 0)
