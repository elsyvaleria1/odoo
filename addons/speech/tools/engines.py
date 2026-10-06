from __future__ import annotations

from typing import Any

from odoo.libs.documents import (
    ANY,
    CUES,
    RECORDING_MIMETYPES,
    TEXT,
    get_readers,
    get_writers,
)
from odoo.libs.filesystem import get_essential_mimetype

DEFAULT_SPEECH_MIMETYPE = "audio/mpeg"


def is_recording(mimetype: str) -> bool:
    return get_essential_mimetype(mimetype or "") in RECORDING_MIMETYPES


def _options(env: Any, purpose: str | None, company: Any) -> dict[str, Any] | None:
    if env is None:
        return None
    return {"env": env, "purpose": purpose, "company": company or env.company}


def transcription_engines(
    mimetype: str, env: Any = None, purpose: str | None = None, company: Any = None
) -> tuple[Any, ...]:
    return tuple(
        reader
        for reader in get_readers(
            get_essential_mimetype(mimetype or ""),
            CUES,
            options=_options(env, purpose, company),
        )
        if ANY not in reader.mimetypes and not reader.carried
    )


def synthesis_engines(
    mimetype: str, env: Any = None, purpose: str | None = None, company: Any = None
) -> tuple[Any, ...]:
    return tuple(
        writer
        for writer in get_writers(
            get_essential_mimetype(mimetype or ""),
            TEXT,
            options=_options(env, purpose, company),
        )
        if writer.mimetype != ANY
    )


def can_transcribe(
    mimetype: str, env: Any = None, purpose: str | None = None, company: Any = None
) -> bool:
    return is_recording(mimetype) and bool(
        transcription_engines(mimetype, env, purpose, company)
    )


def can_synthesize(
    mimetype: str = DEFAULT_SPEECH_MIMETYPE,
    env: Any = None,
    purpose: str | None = None,
    company: Any = None,
) -> bool:
    return bool(synthesis_engines(mimetype, env, purpose, company))
