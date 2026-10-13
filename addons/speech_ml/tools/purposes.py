from __future__ import annotations

from typing import Any

TRANSCRIPTION_PURPOSE = "speech.transcription"
SYNTHESIS_PURPOSE = "speech.synthesis"


def company_id_of(env: Any, options: Any) -> int:
    return (options.get("company") or env.company).id
