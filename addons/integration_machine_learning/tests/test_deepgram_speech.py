from unittest.mock import Mock, patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.integration.tools.exceptions import CommError
from odoo.addons.integration_machine_learning.tests.common import credential_for
from odoo.addons.integration_machine_learning.tools.ai_clients import (
    BaseAIClient,
    DeepgramClient,
    get_client_class,
)

_UTTERANCES = {
    "results": {
        "utterances": [
            {"transcript": "hola", "start": 0.0, "end": 0.8, "speaker": 0},
            {"transcript": "  ", "start": 0.8, "end": 0.9, "speaker": 1},
            {"transcript": "adiós", "start": 1.0, "end": 1.5, "speaker": 1},
        ]
    }
}


@tagged("post_install", "-at_install")
class TestDeepgramSpeech(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        credential_for(cls.env, "deepgram", api_key="K")

    def setUp(self):
        super().setUp()
        self.client = DeepgramClient(self.env)

    def test_transcribe_cues_reads_utterances_with_their_speaker(self):
        with patch.object(
            self.client._client,
            "post",
            return_value={"status_code": 200, "body": _UTTERANCES},
        ) as post:
            cues = self.client.transcribe_cues(
                b"AUDIO", mimetype="audio/ogg", language="es", model="nova-3"
            )

        self.assertEqual(
            cues,
            [
                {
                    "start": 0.0,
                    "end": 0.8,
                    "text": "hola",
                    "speaker": "Speaker 0",
                    "speaker_index": 0,
                    "confidence": 0.0,
                },
                {
                    "start": 1.0,
                    "end": 1.5,
                    "text": "adiós",
                    "speaker": "Speaker 1",
                    "speaker_index": 1,
                    "confidence": 0.0,
                },
            ],
        )
        self.assertEqual(post.call_args.args[0], "/listen")
        params = post.call_args.kwargs["params"]
        self.assertEqual(params["utterances"], "true")
        self.assertEqual(params["language"], "es")
        self.assertEqual(params["model"], "nova-3")
        self.assertEqual(post.call_args.kwargs["headers"]["Content-Type"], "audio/ogg")

    def test_transcribe_cues_refuses_an_empty_transcript(self):
        with patch.object(
            self.client._client,
            "post",
            return_value={"status_code": 200, "body": {"results": {}}},
        ):
            with self.assertRaises(CommError):
                self.client.transcribe_cues(b"AUDIO", mimetype="audio/ogg")

    def test_synthesize_posts_speak_and_returns_the_bytes(self):
        with patch.object(
            self.client._client, "post", return_value=Mock(content=b"ID3")
        ) as post:
            audio = self.client.synthesize(
                "hola", mimetype="audio/wav", model="aura-2-celeste-es"
            )

        self.assertEqual(audio, b"ID3")
        self.assertEqual(post.call_args.args[0], "/speak")
        self.assertTrue(post.call_args.kwargs["raw"])
        self.assertEqual(post.call_args.kwargs["json"], {"text": "hola"})
        self.assertEqual(
            post.call_args.kwargs["params"],
            {"model": "aura-2-celeste-es", "encoding": "linear16", "container": "wav"},
        )

    def test_synthesize_refuses_a_format_it_does_not_write(self):
        with patch.object(self.client._client, "post") as post:
            with self.assertRaises(CommError) as caught:
                self.client.synthesize("hola", mimetype="audio/x-nope")
        self.assertIn("audio/x-nope", str(caught.exception))
        post.assert_not_called()

    def test_a_voice_of_another_vendor_falls_back_to_the_model(self):
        with patch.object(
            self.client._client, "post", return_value=Mock(content=b"ID3")
        ) as post:
            self.client.synthesize("hola", voice="alloy", model="aura-2-luna-en")
        self.assertEqual(post.call_args.kwargs["params"]["model"], "aura-2-luna-en")


@tagged("post_install", "-at_install")
class TestEveryModelKindHasItsMethod(TransactionCase):
    METHOD_OF_KIND = {
        "audio": "transcribe_cues",
        "speech": "synthesize",
        "chat": "complete",
        "vision": "complete",
    }

    def test_a_seeded_model_is_served_by_a_client_that_answers_its_kind(self):
        for model in self.env["integration.ml.model"].search([]):
            method = self.METHOD_OF_KIND.get(model.kind)
            if not method:
                continue
            client_cls = get_client_class(model.provider_id)
            with self.subTest(model=model.code, kind=model.kind):
                self.assertIsNotNone(client_cls)
                implementation = getattr(client_cls, method, None)
                self.assertTrue(
                    callable(implementation)
                    and implementation is not getattr(BaseAIClient, method, None),
                    f"{model.code} is a {model.kind} model, so the router "
                    f"can select it for a {method} call, and "
                    f"{client_cls.__name__} has no {method}",
                )


def _word(word, start, end, confidence=0.9):
    return {
        "word": word.strip("¿?.,").lower(),
        "punctuated_word": word,
        "start": start,
        "end": end,
        "confidence": confidence,
        "speaker": 0,
    }


@tagged("post_install", "-at_install")
class TestDeepgramSentences(TransactionCase):
    ANSWERED = {
        "transcript": "¿Bueno? Hola, Jaz.",
        "start": 0.4,
        "end": 2.6,
        "speaker": 0,
        "confidence": 0.92,
        "words": [
            _word("¿Bueno?", 0.4, 1.1, 0.8),
            _word("Hola,", 1.4, 1.9, 1.0),
            _word("Jaz.", 2.0, 2.6, 0.9),
        ],
    }

    def _cues(self, *utterances):
        return DeepgramClient._read_cues({"results": {"utterances": list(utterances)}})

    def test_an_utterance_is_split_at_each_sentence_its_words_end(self):
        first, second = self._cues(self.ANSWERED)
        self.assertEqual(
            (first["start"], first["end"], first["text"]), (0.4, 1.1, "¿Bueno?")
        )
        self.assertEqual(
            (second["start"], second["end"], second["text"]), (1.4, 2.6, "Hola, Jaz.")
        )
        self.assertAlmostEqual(second["confidence"], 0.95)
        self.assertEqual({first["speaker"], second["speaker"]}, {"Speaker 0"})

    def test_a_single_sentence_stays_as_deepgram_timed_it(self):
        one = {**self.ANSWERED, "words": self.ANSWERED["words"][1:]}
        (cue,) = self._cues(one)
        self.assertEqual(
            (cue["start"], cue["end"], cue["text"], cue["confidence"]),
            (0.4, 2.6, "¿Bueno? Hola, Jaz.", 0.92),
        )

    def test_words_without_punctuation_leave_the_utterance_whole(self):
        bare = {
            **self.ANSWERED,
            "words": [
                {**word, "punctuated_word": ""} for word in self.ANSWERED["words"]
            ],
        }
        self.assertEqual(len(self._cues(bare)), 1)

    def test_a_trailing_fragment_without_a_stop_is_its_own_sentence(self):
        cut = {
            **self.ANSWERED,
            "words": [*self.ANSWERED["words"], _word("este", 2.8, 3.0)],
        }
        self.assertEqual(
            [cue["text"] for cue in self._cues(cut)], ["¿Bueno?", "Hola, Jaz.", "este"]
        )
