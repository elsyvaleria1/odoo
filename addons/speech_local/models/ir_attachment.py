import dataclasses
import logging

from odoo import models
from odoo.libs.documents import CUES, decode_audio

from ..tools.engine import speaker_of
from ..tools.reader import LocalTranscription, local_diarizer
from odoo.addons.speech.tools.engines import is_recording

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _on_read(self, representation, reading):
        # before the speakers are made from the cues, so they are made from
        # the voices this server told apart
        if representation == CUES and reading.state == "done":
            self._separate_voices(reading)
        super()._on_read(representation, reading)

    def _separate_voices(self, reading) -> None:
        """Label the cues by voice when the transcriber heard fewer than two:
        a vendor asked to tell speakers apart can return one for a phone call
        recorded in mono. The text and its timing stay the transcriber's."""
        self.check_singleton()
        if reading.read_by == LocalTranscription.name:
            return
        if not is_recording(self.mimetype or ""):
            return
        cues = reading._decoded()
        if len({cue.speaker for cue in cues if cue.speaker}) > 1:
            return
        diarizer = local_diarizer(self.env, reading.purpose or None)
        if diarizer is None:
            return
        try:
            turns = diarizer.turns(decode_audio(self.raw))
        except (ValueError, RuntimeError, OSError) as error:
            _logger.warning(
                "Could not tell the voices of attachment %s apart: %s", self.id, error
            )
            return
        if len({speaker for _start, _end, speaker in turns}) < 2:
            return
        voiced = [
            dataclasses.replace(cue, speaker=speaker_of(cue, turns)) for cue in cues
        ]
        reading.write({"value": reading._encoded(CUES, voiced)})
