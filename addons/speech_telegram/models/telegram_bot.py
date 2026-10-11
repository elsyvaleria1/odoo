import logging

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.documents import cues_as_text

from ..tools.voice import (
    VOICE_NOTE_MIMETYPE,
    VOICE_NOTE_NAME,
    Heard,
    mimetype_of,
    voice_payload,
)
from odoo.addons.speech.tools.engines import can_transcribe
from odoo.addons.speech.tools.hear import hear
from odoo.addons.telegram.tools.authority import operating

_logger = logging.getLogger(__name__)

TRANSCRIPTION_PURPOSE = "speech.transcription"


class TelegramBot(models.Model):
    _inherit = "telegram.bot"

    voice_notes_heard = fields.Boolean(
        compute="_compute_voice_notes_heard",
        help="Whether a voice note sent to this bot can be transcribed: some "
        "speech engine may hear it under the company's transcription policy.",
    )

    def _compute_voice_notes_heard(self) -> None:
        heard = self._hears_voice_notes()
        for bot in self:
            bot.voice_notes_heard = heard

    def _hears_voice_notes(
        self, purpose=TRANSCRIPTION_PURPOSE, filename=None, company=None
    ):
        mimetype = mimetype_of(filename) if filename else VOICE_NOTE_MIMETYPE
        return can_transcribe(mimetype, self.env, purpose, company)

    @staticmethod
    def _voice_payload(message):
        return voice_payload(message)

    def _hear_message(
        self,
        chat,
        message,
        *,
        context="",
        purpose=TRANSCRIPTION_PURPOSE,
        language=None,
        max_seconds=None,
        notice=None,
        company=None,
    ):
        self.check_singleton()
        payload = voice_payload(message)
        if not payload:
            return Heard(failure="no_audio")
        if max_seconds and payload.duration > max_seconds:
            return Heard(failure="too_long", duration=payload.duration)
        bot = operating(self)
        if not bot._hears_voice_notes(purpose, payload.filename, company):
            return Heard(failure="unheard", duration=payload.duration)
        if notice:
            bot.send_message(chat.chat_id, notice)
        bot.send_chat_action(chat, "typing")
        audio = bot.get_file_content(payload.file_id)
        text = audio and bot._hear_voice_note(
            audio,
            filename=payload.filename,
            context=context,
            language=language or "es",
            purpose=purpose,
            company=company,
        )
        if not text:
            return Heard(failure="failed", duration=payload.duration)
        return Heard(text=text, duration=payload.duration)

    def _hear_voice_note(
        self,
        audio: bytes,
        *,
        filename: str = VOICE_NOTE_NAME,
        context: str = "",
        language: str = "es",
        purpose: str = TRANSCRIPTION_PURPOSE,
        company=None,
    ) -> str | None:
        self.check_singleton()
        if not audio:
            return None
        try:
            cues = hear(
                self.env,
                audio,
                mimetype=mimetype_of(filename),
                name=filename,
                language=language,
                prompt=context,
                purpose=purpose,
                company=company,
            )
        except UserError as error:
            _logger.warning("%s could not be transcribed: %s", filename, error)
            return None
        return cues_as_text(cues) or None
