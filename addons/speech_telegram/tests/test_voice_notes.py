from unittest.mock import patch

from odoo.libs.documents import (
    CUES,
    METERED,
    BaseReader,
    Cue,
    register_reader,
    unregister_reader,
)
from odoo.tests import tagged

from odoo.addons.speech_telegram.tools.voice import Heard, VoicePayload
from odoo.addons.telegram.models.telegram_bot import TelegramBot
from odoo.addons.telegram.tests.common import TelegramBotTestCase


class _Hears(BaseReader):
    name = "telegram_voice_note_stub"
    mimetypes = frozenset({"audio/ogg", "audio/webm"})
    yields = (CUES,)
    cost = METERED

    def __init__(self, error=None):
        self.error = error
        self.heard = []

    def read(self, document):
        self.heard.append(dict(document.options))
        if self.error:
            raise self.error
        return [Cue(0.0, 1.0, "falta el CFDI", ""), Cue(1.0, 2.0, "del lote 42", "")]


@tagged("post_install", "-at_install")
class TestVoiceNotes(TelegramBotTestCase):
    def _hears(self, **kwargs):
        engine = register_reader(_Hears(**kwargs))
        self.addCleanup(unregister_reader, engine)
        return engine

    def test_a_voice_note_is_heard_and_kept_nowhere(self):
        engine = self._hears()
        attachments = self.env["ir.attachment"].sudo().search_count([])
        text = self.test_bot._hear_voice_note(
            b"OggS-voice", filename="voice.oga", context="Una solicitud."
        )
        self.assertEqual(text, "falta el CFDI\ndel lote 42")
        self.assertEqual(engine.heard[0]["language"], "es")
        self.assertEqual(engine.heard[0]["prompt"], "Una solicitud.")
        self.assertEqual(
            self.env["ir.attachment"].sudo().search_count([]),
            attachments,
            "a voice note leaves no attachment behind",
        )

    def test_a_note_nobody_could_hear_is_none(self):
        self._hears(error=RuntimeError("vendor down"))
        self.assertIsNone(self.test_bot._hear_voice_note(b"OggS-voice"))

    def test_a_dictation_is_heard_as_what_it_is(self):
        engine = self._hears()
        self.test_bot._hear_voice_note(b"webm-bytes", filename="dictation.webm")
        self.assertTrue(engine.heard)

    def test_the_bot_says_whether_voice_notes_are_heard(self):
        self.assertFalse(self.test_bot.voice_notes_heard)
        self._hears()
        self.test_bot.invalidate_recordset(["voice_notes_heard"])
        self.assertTrue(self.test_bot.voice_notes_heard)

    def test_the_bots_business_words_reach_the_engines(self):
        terms = self.env["speech.vocabulary"]._keyterms()
        self.assertIn("CFDI", terms)
        self.assertIn("estado de cuenta", terms)

    def _hear(self, message, **options):
        with (
            patch.object(TelegramBot, "get_file_content", return_value=b"OggS") as got,
            patch.object(TelegramBot, "send_chat_action") as typing,
        ):
            heard = self.test_bot._hear_message(self.test_chat, message, **options)
        return heard, got, typing

    def test_what_a_message_carries_as_a_recording(self):
        payload = self.test_bot._voice_payload
        self.assertEqual(
            payload({"voice": {"file_id": "v", "duration": 7}}),
            VoicePayload("v", "voice.ogg", 7),
        )
        self.assertEqual(
            payload({"audio": {"file_id": "a", "file_name": "pedido.MP3"}}),
            VoicePayload("a", "pedido.MP3", 0),
        )
        self.assertEqual(
            payload({"audio": {"file_id": "a", "mime_type": "audio/mpeg"}}),
            VoicePayload("a", "audio.mp3", 0),
        )
        self.assertEqual(
            payload({"document": {"file_id": "d", "mime_type": "audio/x-wav"}}),
            VoicePayload("d", "audio.wav", 0),
        )
        self.assertEqual(
            payload({"document": {"file_id": "d", "file_name": "nota.m4a"}}),
            VoicePayload("d", "nota.m4a", 0),
        )
        for message in (
            {"text": "hola"},
            {"document": {"file_id": "d", "file_name": "factura.pdf"}},
            {"document": {"file_id": "d", "file_name": "ogg"}},
            {"voice": {"duration": 3}},
        ):
            self.assertIsNone(payload(message), message)

    def test_a_voice_message_is_heard_while_the_chat_sees_the_bot_typing(self):
        engine = self._hears()
        heard, got, typing = self._hear(
            {"voice": {"file_id": "v", "duration": 3}}, context="Una solicitud."
        )
        self.assertEqual(heard, Heard("falta el CFDI\ndel lote 42", None, 3))
        got.assert_called_once_with("v")
        typing.assert_called_once_with(self.test_chat, "typing")
        self.assertEqual(engine.heard[0]["prompt"], "Una solicitud.")

    def test_a_note_over_the_limit_is_not_downloaded(self):
        self._hears()
        heard, got, typing = self._hear(
            {"voice": {"file_id": "v", "duration": 301}}, max_seconds=300
        )
        self.assertEqual(heard, Heard(None, "too_long", 301))
        got.assert_not_called()
        typing.assert_not_called()

    def test_without_an_engine_a_note_is_unheard(self):
        heard, got, _typing = self._hear({"voice": {"file_id": "v", "duration": 3}})
        self.assertEqual(heard.failure, "unheard")
        got.assert_not_called()

    def test_a_message_without_a_recording(self):
        heard, _got, _typing = self._hear({"text": "hola"})
        self.assertEqual(heard.failure, "no_audio")

    def test_a_note_the_engine_could_not_hear_failed(self):
        self._hears(error=RuntimeError("vendor down"))
        heard, _got, _typing = self._hear({"voice": {"file_id": "v", "duration": 3}})
        self.assertEqual(heard, Heard(None, "failed", 3))

    def test_a_note_is_heard_as_the_requester_never_the_superuser(self):
        engine = self._hears()
        public = self.env.ref("base.public_user")
        bot = self.test_bot.with_user(public)
        with (
            patch.object(TelegramBot, "get_file_content", return_value=b"OggS"),
            patch.object(TelegramBot, "send_chat_action"),
        ):
            heard = bot._hear_message(
                self.test_chat, {"voice": {"file_id": "v", "duration": 3}}
            )
        self.assertEqual(heard.text, "falta el CFDI\ndel lote 42")
        hearing = engine.heard[0]["env"]
        self.assertEqual((hearing.uid, hearing.su), (public.id, False))
