import tempfile
from pathlib import Path

from odoo.libs.documents import (
    CUES,
    METERED,
    BaseReader,
    Cue,
    register_reader,
    unregister_reader,
)
from odoo.tests import TransactionCase, tagged

from odoo.addons.speech.tools.measure import (
    CORPUS_FILE,
    Score,
    measure,
    read_corpus,
    report,
    word_errors,
    words,
)


class Hears(BaseReader):
    mimetypes = frozenset({"audio/wav"})
    yields = (CUES,)
    cost = METERED

    def __init__(self, name, answers, log, usable=True, error=None):
        self.name = name
        self.answers = answers
        self.log = log
        self.usable = usable
        self.error = error

    def available(self, options):
        return self.usable

    def read(self, document):
        self.log.append((self.name, document.name, document.options["purpose"]))
        if self.error:
            raise self.error
        return [Cue(0.0, 1.0, self.answers[document.name], "")]


@tagged("post_install", "-at_install")
class TestMeasure(TransactionCase):
    def setUp(self):
        super().setUp()
        self.corpus = Path(tempfile.mkdtemp())
        (self.corpus / CORPUS_FILE).write_text(
            "# file\ttext\none.wav\tAbre contabilidad\n\ntwo.wav\tfacturas sin pagar\n",
            encoding="utf-8",
        )
        for name in ("one.wav", "two.wav"):
            (self.corpus / name).write_bytes(b"RIFF")
        self.log = []

    def _engine(self, name, answers, **kwargs):
        engine = Hears(name, answers, self.log, **kwargs)
        register_reader(engine)
        self.addCleanup(unregister_reader, engine)
        return engine

    def test_words_are_compared_without_case_accents_or_punctuation(self):
        self.assertEqual(
            words("¡Abre Contabilidad, ya!"), ["abre", "contabilidad", "ya"]
        )
        self.assertEqual(words("Número"), ["numero"])

    def test_a_spoken_number_is_compared_as_the_number_it_names(self):
        self.assertEqual(words("treinta y ocho"), ["38"])
        self.assertEqual(words("Cantidad 12.5."), ["cantidad", "12.5"])
        self.assertEqual(words("cantidad doce punto cinco"), ["cantidad", "12.5"])
        self.assertEqual(words("cantidad tres mil doscientos"), ["cantidad", "3200"])
        self.assertEqual(words("siete punto veinticinco"), words("7,25"))
        self.assertEqual(words("cero cero cuarenta y dos"), ["0042"])
        self.assertEqual(words("one hundred and five"), ["105"])
        self.assertEqual(
            words("abre ventas y agrupa"), ["abre", "ventas", "y", "agrupa"]
        )
        self.assertEqual(word_errors(words("son sesenta y cuatro"), words("Son 64")), 0)

    def test_word_errors_count_substitutions_insertions_and_deletions(self):
        reference = ["facturas", "sin", "pagar"]
        self.assertEqual(word_errors(reference, reference), 0)
        self.assertEqual(word_errors(reference, ["facturas", "sin", "pago"]), 1)
        self.assertEqual(word_errors(reference, ["facturas", "pagar"]), 1)
        self.assertEqual(word_errors(reference, ["las", *reference]), 1)
        self.assertEqual(word_errors(reference, []), 3)

    def test_the_corpus_skips_comments_and_blank_lines(self):
        clips = read_corpus(self.corpus)
        self.assertEqual([clip.path.name for clip in clips], ["one.wav", "two.wav"])
        self.assertEqual(clips[0].text, "Abre contabilidad")
        self.assertEqual(clips[0].mimetype, "audio/wav")

    def test_every_usable_engine_is_scored_and_they_take_turns_clip_by_clip(self):
        self._engine(
            "exact",
            {"one.wav": "abre contabilidad.", "two.wav": "Facturas sin pagar"},
        )
        self._engine(
            "sloppy",
            {"one.wav": "abre contabilidad", "two.wav": "facturas sin pago"},
        )
        self._engine("closed", {}, usable=False)
        self._engine("broken", {}, error=RuntimeError("down"))
        scores = {
            score.engine: score
            for score in measure(
                self.env, read_corpus(self.corpus), "speech.transcription.command"
            )
        }
        self.assertNotIn("closed", scores)
        self.assertEqual((scores["exact"].wer, scores["exact"].exact_rate), (0.0, 1.0))
        self.assertEqual(scores["sloppy"].errors, 1)
        self.assertEqual(scores["sloppy"].words, 5)
        self.assertEqual(scores["sloppy"].exact_rate, 0.5)
        self.assertEqual((scores["broken"].failed, scores["broken"].clips), (2, 0))
        mine = [entry for entry in self.log if entry[0] in ("exact", "sloppy")]
        self.assertEqual(
            [(engine, clip) for engine, clip, _ in mine],
            [
                ("exact", "one.wav"),
                ("sloppy", "one.wav"),
                ("exact", "two.wav"),
                ("sloppy", "two.wav"),
            ],
        )
        self.assertEqual(
            {purpose for *_, purpose in self.log}, {"speech.transcription.command"}
        )

    def test_what_each_engine_heard_can_be_kept_per_clip(self):
        self._engine("exact", {"one.wav": "Abre contabilidad.", "two.wav": "facturas"})
        transcripts = []
        measure(
            self.env,
            read_corpus(self.corpus),
            "speech.transcription.command",
            transcripts=transcripts,
        )
        self.assertEqual(
            [line for line in transcripts if line["engine"] == "exact"],
            [
                {
                    "file": "one.wav",
                    "engine": "exact",
                    "purpose": "speech.transcription.command",
                    "said": "Abre contabilidad",
                    "heard": "Abre contabilidad.",
                },
                {
                    "file": "two.wav",
                    "engine": "exact",
                    "purpose": "speech.transcription.command",
                    "said": "facturas sin pagar",
                    "heard": "facturas",
                },
            ],
        )

    def test_one_engine_can_be_measured_alone(self):
        self._engine("exact", {"one.wav": "x", "two.wav": "y"})
        self._engine("other", {"one.wav": "x", "two.wav": "y"})
        scores = measure(
            self.env,
            read_corpus(self.corpus),
            "speech.transcription.command",
            only={"other"},
        )
        self.assertEqual([score.engine for score in scores], ["other"])

    def test_the_report_ranks_the_most_accurate_first(self):
        good, bad = Score("good"), Score("bad")
        good.add("abre ventas", "abre ventas", 0.2)
        bad.add("abre ventas", "abre", 0.4)
        lines = report([bad, good]).splitlines()
        self.assertTrue(lines[1].startswith("good"))
        self.assertIn("50.0%", lines[2])
