from __future__ import annotations

from typing import Any

from odoo.exceptions import UserError
from odoo.libs.documents import CUES, METERED, Cue, Document

from .engines import can_transcribe


def hear(
    env: Any,
    audio: bytes,
    *,
    mimetype: str,
    name: str = "recording",
    purpose: str | None = None,
    language: str | None = None,
    prompt: str | None = None,
    company: Any = None,
) -> list[Cue]:
    if not audio:
        return []
    company = company or env.company
    if not can_transcribe(mimetype, env, purpose, company):
        raise UserError(env._("No speech engine may hear this recording here."))
    document = Document(
        audio,
        mimetype,
        name,
        env=env,
        company=company,
        read_up_to=METERED,
        purpose=purpose,
        language=language or None,
        prompt=prompt or None,
    )
    cues = document.cues
    if not cues and CUES in document.errors:
        raise UserError(document.errors[CUES])
    return cues
