import base64
import struct
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.libs.documents import (
    CUES,
    METERED,
    BaseReader,
    Cue,
    readers,
    register_reader,
    unregister_reader,
)
from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.voice.tools.utterance import (
    COMMAND_PURPOSE,
    ENGLISH_PASS_PARAMETER,
    MAX_UTTERANCE_BYTES,
    transcribe_utterance,
)


def wav(seconds=1.0, rate=16_000):
    samples = int(seconds * rate)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + samples * 2,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        rate,
        rate * 2,
        2,
        16,
        b"data",
        samples * 2,
    )
    return header + b"\x01\x00" * samples


class CommandEngine(BaseReader):
    name = "stub_command_engine"
    mimetypes = frozenset({"audio/wav", "audio/x-wav"})
    yields = (CUES,)
    cost = METERED

    def __init__(self, text="sin pagar", serves=(COMMAND_PURPOSE,)):
        self.text = text
        self.serves = set(serves)
        self.heard = []

    def available(self, options):
        return options.get("purpose") in self.serves

    def read(self, document):
        self.heard.append(dict(document.options))
        return [Cue(0.0, 1.0, f" {self.text} ", "")]


class CommandEngineMixin:
    def _engine(self, **kwargs):
        engine = CommandEngine(**kwargs)
        register_reader(engine)
        self.addCleanup(unregister_reader, engine)
        return engine


@tagged("post_install", "-at_install")
class TestTranscribeUtterance(CommandEngineMixin, TransactionCase):
    def test_words_come_back_and_nothing_is_kept(self):
        engine = self._engine()
        attachments = self.env["ir.attachment"].sudo().search_count([])
        text = transcribe_utterance(self.env, wav(), "es", "Sin pagar, Vendedor")
        self.assertEqual(text, "sin pagar")
        self.assertEqual(self.env["ir.attachment"].sudo().search_count([]), attachments)
        [options] = engine.heard
        self.assertEqual(options["purpose"], COMMAND_PURPOSE)
        self.assertEqual(options["language"], "es")
        self.assertEqual(options["prompt"], "Sin pagar, Vendedor")

    def test_an_engine_not_allowed_for_commands_is_not_asked(self):
        engine = self._engine(serves=("speech.transcription",))
        # whatever else this machine can hear with (its own models, say) is not
        # the subject: only the engine that may not hear commands is offered
        with (
            patch.dict(readers._READERS, {CUES: [engine]}),
            self.assertRaisesRegex(UserError, "No speech engine may hear"),
        ):
            transcribe_utterance(self.env, wav())
        self.assertEqual(engine.heard, [])

    def test_a_long_recording_is_refused_before_any_engine_hears_it(self):
        engine = self._engine()
        with self.assertRaisesRegex(UserError, "at most 15 seconds"):
            transcribe_utterance(self.env, b"\x00" * (MAX_UTTERANCE_BYTES + 1))
        self.assertEqual(engine.heard, [])

    def test_silence_is_no_words(self):
        self.assertEqual(transcribe_utterance(self.env, b""), "")


@tagged("post_install", "-at_install")
class TestUtteranceRoutes(CommandEngineMixin, HttpCase):
    def _call(self, route, **params):
        response = self.url_open(
            route,
            data=json_dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
            headers={"Content-Type": "application/json"},
        )
        body = response.json()
        if "error" in body:
            raise AssertionError(body["error"]["data"]["name"])
        return body["result"]

    def test_an_internal_user_is_heard(self):
        self._engine(text="abre ventas")
        new_test_user(self.env, login="voice_internal", groups="base.group_user")
        self.authenticate("voice_internal", "voice_internal")
        self.assertEqual(
            self._call("/voice/available"),
            {"available": True, "english_pass": False},
        )
        audio = base64.b64encode(wav()).decode()
        self.assertEqual(
            self._call("/voice/transcribe", audio=audio, language="es"),
            {"text": "abre ventas"},
        )

    def test_the_english_second_pass_is_read_by_an_internal_user(self):
        self._engine()
        self.env["ir.config_parameter"].set_param(ENGLISH_PASS_PARAMETER, "True")
        new_test_user(self.env, login="voice_english", groups="base.group_user")
        self.authenticate("voice_english", "voice_english")
        self.assertEqual(
            self._call("/voice/available"),
            {"available": True, "english_pass": True},
        )

    def test_a_portal_user_is_not(self):
        engine = self._engine()
        new_test_user(self.env, login="voice_portal", groups="base.group_portal")
        self.authenticate("voice_portal", "voice_portal")
        self.assertEqual(
            self._call("/voice/available"),
            {"available": False, "english_pass": False},
        )
        audio = base64.b64encode(wav()).decode()
        with self.assertRaisesRegex(AssertionError, "AccessError"):
            self._call("/voice/transcribe", audio=audio)
        self.assertEqual(engine.heard, [])
