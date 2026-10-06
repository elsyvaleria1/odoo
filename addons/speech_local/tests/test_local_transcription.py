import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from odoo.libs.documents import (
    CUES,
    METERED,
    BaseReader,
    Cue,
    Document,
    get_readers,
    register_reader,
    unregister_reader,
)
from odoo.tests import TransactionCase, tagged

from odoo.addons.speech.tools.engines import (
    transcription_engines,
)
from odoo.addons.speech_local.tools import reader as local
from odoo.addons.speech_local.tools.engine import (
    DECODER,
    ENCODER,
    REQUIRED,
    TOKENS,
    WHISPER_TAIL_PADDINGS,
    LocalEngine,
    Utterance,
    model_files,
    speaker_of,
    whisper_language,
)

READER = local.__name__
COMMAND = "speech.transcription.command"
DICTATION = "speech.transcription.dictation"


class FakeEngine:
    def __init__(self, cues):
        self.cues = cues
        self.calls = []

    def transcribe(self, samples, language=None):
        self.calls.append((samples, language))
        return list(self.cues)


class VendorStub(BaseReader):
    name = "vendor_stub"
    mimetypes = frozenset({"audio/mpeg"})
    yields = (CUES,)
    cost = METERED

    def __init__(self, usable, cues=None, error=None):
        self.usable = usable
        self.cues = cues
        self.error = error

    def available(self, options):
        return self.usable

    def read(self, document):
        if self.error:
            raise self.error
        return self.cues


def _utterance(start, end):
    return Utterance(start, end, np.zeros(0, dtype=np.float32))


@tagged("post_install", "-at_install")
class TestLocalTranscription(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reader = next(
            r
            for r in get_readers("audio/mpeg", CUES)
            if r.name == "local_transcription"
        )
        cls.cues = [Cue(0.0, 2.0, "buenos días", "SPEAKER_0")]

    def setUp(self):
        super().setUp()
        self.models = Path(tempfile.mkdtemp())
        self.addCleanup(local._ENGINES.pop, self.models, None)
        self.env["ir.config_parameter"].sudo().set_param(
            local.MODEL_DIR_PARAM, str(self.models)
        )

    def _complete_models(self, directory=None):
        directory = directory or self.models
        directory.mkdir(exist_ok=True)
        for name in REQUIRED:
            (directory / name).write_bytes(b"")
        self.addCleanup(local._ENGINES.pop, directory, None)
        return directory

    def _heard(self, purpose):
        return Document(
            b"fake-audio",
            "audio/mpeg",
            "clip.mp3",
            env=self.env,
            read_up_to=METERED,
            purpose=purpose,
        )

    def _vendor(self, usable, **answer):
        vendor = VendorStub(usable, **answer)
        register_reader(vendor)
        self.addCleanup(unregister_reader, vendor)
        return vendor

    def _usable_engines(self):
        return [e.name for e in transcription_engines("audio/mpeg", self.env)]

    def _audio(self):
        return self.env["ir.attachment"].create(
            {"name": "call.mp3", "mimetype": "audio/mpeg", "raw": b"fake-audio"}
        )

    def test_unavailable_until_every_required_model_is_there(self):
        self.assertFalse(self.reader.available({"env": self.env}))
        (self.models / REQUIRED[0]).write_bytes(b"")
        self.assertFalse(self.reader.available({"env": self.env}))
        self._complete_models()
        self.assertTrue(self.reader.available({"env": self.env}))

    def test_a_release_is_used_under_the_names_it_ships_with(self):
        for name in ("small-encoder.onnx", "small-decoder.onnx", "small-tokens.txt"):
            (self.models / name).write_bytes(b"")
        self.assertFalse(
            self.reader.available({"env": self.env}), "no voice detector yet"
        )
        (self.models / "silero_vad.onnx").write_bytes(b"")
        self.assertTrue(self.reader.available({"env": self.env}))
        (self.models / "small-encoder.int8.onnx").write_bytes(b"")
        self.assertEqual(
            model_files(self.models)[0][ENCODER].name,
            "small-encoder.onnx",
            "half an int8 pair is not a pair",
        )
        (self.models / "small-decoder.int8.onnx").write_bytes(b"")
        files = model_files(self.models)[0]
        self.assertEqual(
            (files[ENCODER].name, files[DECODER].name, files[TOKENS].name),
            ("small-encoder.int8.onnx", "small-decoder.int8.onnx", "small-tokens.txt"),
        )

    def test_two_releases_in_one_directory_are_not_guessed_between(self):
        for size in ("small", "turbo"):
            for part in ("encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt"):
                (self.models / f"{size}-{part}").write_bytes(b"")
        (self.models / "silero_vad.onnx").write_bytes(b"")
        self.assertEqual(model_files(self.models)[1], [ENCODER, DECODER, TOKENS])
        self.assertFalse(self.reader.available({"env": self.env}))

    def test_transcribes_where_no_vendor_serves(self):
        self._complete_models()
        self._vendor(usable=False)
        self.assertEqual(self._usable_engines(), ["local_transcription"])
        engine = FakeEngine(self.cues)
        attachment = self._audio()
        with (
            patch(f"{READER}.local_engine", return_value=engine),
            patch(f"{READER}.decode_audio", return_value=np.zeros(8)),
        ):
            cues = attachment._transcribe(language="es_MX")
        self.assertEqual(cues, self.cues)
        self.assertEqual(attachment.transcript_engine, "local_transcription")
        self.assertEqual(engine.calls[0][1], "es_MX")

    def test_a_vendor_that_answers_is_never_second_guessed(self):
        self._complete_models()
        vendor_cues = [Cue(0.0, 1.0, "from the vendor", "SPEAKER_0")]
        self._vendor(usable=True, cues=vendor_cues)
        engine = FakeEngine(self.cues)
        attachment = self._audio()
        with patch(f"{READER}.local_engine", return_value=engine):
            cues = attachment._transcribe()
        self.assertEqual(
            (cues, attachment.transcript_engine), (vendor_cues, "vendor_stub")
        )
        self.assertFalse(engine.calls)

    def test_a_vendor_that_fails_is_covered_by_the_local_engine(self):
        self._complete_models()
        self._vendor(usable=True, error=RuntimeError("vendor down"))
        attachment = self._audio()
        with (
            patch(f"{READER}.local_engine", return_value=FakeEngine(self.cues)),
            patch(f"{READER}.decode_audio", return_value=np.zeros(8)),
        ):
            attachment._transcribe()
        self.assertEqual(attachment.transcript_state, "done")
        self.assertEqual(attachment.transcript_engine, "local_transcription")
        self.assertFalse(attachment.transcript_error)

    def test_it_is_offered_after_its_peers_whenever_it_registered(self):
        vendor = self._vendor(usable=True)
        names = [r.name for r in get_readers("audio/mpeg", CUES)]
        self.assertGreater(names.index("local_transcription"), names.index(vendor.name))

    def test_a_purpose_with_its_own_models_is_heard_by_them(self):
        self._complete_models()
        command = self._complete_models(self.models / COMMAND)
        (self.models / DICTATION).mkdir()
        (self.models / DICTATION / REQUIRED[0]).write_bytes(b"")
        self.assertEqual(local.model_dir(self.env, COMMAND), command)
        self.assertEqual(
            local.model_dir(self.env, DICTATION),
            self.models,
            "a purpose directory missing a model is not used",
        )
        self.assertEqual(local.model_dir(self.env), self.models)
        self.assertIsNot(
            local.local_engine(self.env, COMMAND), local.local_engine(self.env)
        )

    def test_a_purpose_with_its_own_models_is_heard_here_before_its_vendors(self):
        self._complete_models()
        self._complete_models(self.models / COMMAND)
        vendor_cues = [Cue(0.0, 1.0, "from the vendor", "SPEAKER_0")]
        vendor = self._vendor(usable=True, cues=vendor_cues)
        heard_by = []

        class Recording(FakeEngine):
            def __init__(self, directory, cues):
                super().__init__(cues)
                self.directory = directory

            def transcribe(self, samples, language=None):
                heard_by.append(self.directory)
                return super().transcribe(samples, language)

        def engine_for(env, purpose=None):
            return Recording(local.model_dir(env, purpose), self.cues)

        with (
            patch(f"{READER}.local_engine", side_effect=engine_for),
            patch(f"{READER}.decode_audio", return_value=np.zeros(8)),
        ):
            command = self._heard(COMMAND)
            dictation = self._heard(DICTATION)
            self.assertEqual(
                [r.name for r in get_readers("audio/mpeg", CUES, command)][:2],
                ["local_transcription", vendor.name],
            )
            self.assertEqual(command.cues, self.cues)
            self.assertEqual(dictation.cues, vendor_cues)
        self.assertEqual(heard_by, [self.models / COMMAND])

    def test_a_vendor_backs_up_a_purpose_heard_here_first(self):
        self._complete_models()
        self._complete_models(self.models / COMMAND)
        vendor_cues = [Cue(0.0, 1.0, "from the vendor", "SPEAKER_0")]
        self._vendor(usable=True, cues=vendor_cues)

        class Broken(FakeEngine):
            def transcribe(self, samples, language=None):
                raise RuntimeError("model crashed")

        with (
            patch(f"{READER}.local_engine", return_value=Broken([])),
            patch(f"{READER}.decode_audio", return_value=np.zeros(8)),
        ):
            self.assertEqual(self._heard(COMMAND).cues, vendor_cues)

    def test_an_engine_failure_is_reported_on_the_document(self):
        self._complete_models()

        class Broken(FakeEngine):
            def transcribe(self, samples, language=None):
                raise RuntimeError("model crashed")

        attachment = self._audio()
        with (
            patch(f"{READER}.local_engine", return_value=Broken([])),
            patch(f"{READER}.decode_audio", return_value=np.zeros(8)),
        ):
            attachment._transcribe()
        self.assertEqual(attachment.transcript_state, "failed")
        self.assertIn("model crashed", attachment.transcript_error)

    def test_the_voice_heard_longest_names_the_utterance(self):
        turns = [(0.0, 1.0, 0), (1.0, 4.0, 1), (4.0, 5.0, 0)]
        self.assertEqual(speaker_of(_utterance(0.5, 4.5), turns), "SPEAKER_1")
        self.assertEqual(speaker_of(_utterance(6.0, 7.0), turns), "")
        self.assertEqual(speaker_of(_utterance(0.0, 1.0), []), "")

    def test_only_the_large_whisper_family_hears_a_short_utterance_in_its_full_window(
        self,
    ):
        paddings = {}
        for size in ("turbo", "large-v3", "small"):
            models = Path(tempfile.mkdtemp())
            for part in ("encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt"):
                (models / f"{size}-{part}").write_bytes(b"")
            (models / "silero_vad.onnx").write_bytes(b"")
            with patch(
                "odoo.addons.speech_local.tools.engine.sherpa_onnx.OfflineRecognizer.from_whisper"
            ) as build:
                LocalEngine(models)._recognizer("es")
            paddings[size] = build.call_args.kwargs.get("tail_paddings")
        self.assertEqual(
            paddings,
            {
                "turbo": WHISPER_TAIL_PADDINGS,
                "large-v3": WHISPER_TAIL_PADDINGS,
                "small": None,
            },
        )

    def test_whisper_takes_the_bare_language_code(self):
        self.assertEqual(whisper_language("es_MX"), "es")
        self.assertEqual(whisper_language("en-US"), "en")
        self.assertEqual(whisper_language(None), "")
