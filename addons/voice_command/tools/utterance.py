from __future__ import annotations

from typing import Any

from odoo.exceptions import UserError

from odoo.addons.speech.tools.engines import can_transcribe
from odoo.addons.speech.tools.hear import hear

COMMAND_PURPOSE = "speech.transcription.command"
UTTERANCE_MIMETYPE = "audio/wav"
MAX_UTTERANCE_SECONDS = 15
MAX_UTTERANCE_BYTES = 16_000 * 2 * MAX_UTTERANCE_SECONDS + 44


ENGLISH_PASS_PARAMETER = "voice_command.english_second_pass"


def english_pass(env: Any) -> bool:
    return (
        env["ir.config_parameter"]
        .with_privilege(
            "voice_command.privilege_read_english_pass",
            reason="tell the voice client whether a command nothing understood "
            "may be heard again in English",
        )
        .get_param_bool(ENGLISH_PASS_PARAMETER)
    )


def can_hear_commands(env: Any) -> bool:
    return can_transcribe(UTTERANCE_MIMETYPE, env, COMMAND_PURPOSE)


def transcribe_utterance(
    env: Any, audio: bytes, language: str | None = None, prompt: str | None = None
) -> str:
    if not audio:
        return ""
    if len(audio) > MAX_UTTERANCE_BYTES:
        raise UserError(
            env._(
                "A voice command lasts at most %(seconds)s seconds.",
                seconds=MAX_UTTERANCE_SECONDS,
            )
        )
    if not can_hear_commands(env):
        raise UserError(env._("No speech engine may hear voice commands here."))
    cues = hear(
        env,
        audio,
        mimetype=UTTERANCE_MIMETYPE,
        name="utterance.wav",
        purpose=COMMAND_PURPOSE,
        language=language,
        prompt=prompt,
    )
    return " ".join(cue.text.strip() for cue in cues if cue.text.strip())
