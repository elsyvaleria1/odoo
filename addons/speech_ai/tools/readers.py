from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from odoo.exceptions import UserError
from odoo.libs.documents import (
    AUDIO_TRACK_MIMETYPE,
    CUES,
    METERED,
    RECORDING_MIMETYPES,
    VIDEO_MIMETYPES,
    BaseReader,
    Cue,
    audio_track,
    register_reader,
    remembered,
)
from odoo.tools import human_size

from .purposes import TRANSCRIPTION_PURPOSE, company_id_of
from odoo.addons.integration_machine_learning.tools.router import MlRequest, get_router

_logger = logging.getLogger(__name__)


def _cue_of(span: dict) -> Cue:
    index = span.get("speaker_index")
    return Cue(
        start=float(span.get("start") or 0.0),
        end=float(span.get("end") or 0.0),
        text=(span.get("text") or "").strip(),
        speaker=f"SPEAKER_{index}" if index is not None else span.get("speaker") or "",
        confidence=float(span.get("confidence") or 0.0),
    )


class AiTranscription(BaseReader):
    """The words a recording holds, read by whichever engine a key is held for."""

    name = "ai_transcription"
    mimetypes = RECORDING_MIMETYPES
    yields = (CUES,)
    cost = METERED
    module = "speech_ai"
    async_only = True

    def available(self, options: Mapping[str, Any]) -> bool:
        env = options.get("env")
        if env is None:
            return False
        return bool(self._model(env, options))

    def _model(self, env: Any, options: Mapping[str, Any]) -> Any:
        company_id = company_id_of(env, options)
        purpose = options.get("purpose") or TRANSCRIPTION_PURPOSE
        return remembered(
            options,
            (self.name, company_id, purpose),
            lambda: _pick_timed_model(env, company_id, purpose),
        )

    def read(self, document: Any) -> list[Cue]:
        env = document.options.get("env")
        if env is None:
            _logger.info(
                "%r reached the transcription reader with no environment; "
                "a caller that wants a recording read passes env=",
                document.name,
            )
            return []
        company_id = company_id_of(env, document.options)
        purpose = document.options.get("purpose") or TRANSCRIPTION_PURPOSE
        model = self._model(env, document.options)
        if not model:
            return []
        language = document.options.get("language")
        prompt = document.options.get("prompt")
        company = env["res.company"].browse(company_id)
        audio, mimetype = _heard(document)
        _check_capacity(env, model, audio, company_id, purpose)
        spans = (
            get_router(env)
            .run(
                "transcribe_timed",
                MlRequest(
                    purpose=purpose,
                    audio=audio,
                    filename=document.name or "audio",
                    mimetype=mimetype,
                    language=language,
                    prompt=prompt or "",
                    vocabulary=tuple(env["speech.vocabulary"]._keyterms(company)),
                    speakers=True,
                ),
                model=model,
                company_id=company_id,
            )
            .cues
        )
        return [
            _cue_of(span) for span in spans or [] if (span.get("text") or "").strip()
        ]


def _pick_timed_model(env: Any, company_id: int, purpose: str) -> Any:
    return get_router(env).model_for(
        "transcribe_timed", company_id=company_id, purpose=purpose
    )


register_reader(AiTranscription())


def _heard(document: Any) -> tuple[bytes, str]:
    if document.mimetype in VIDEO_MIMETYPES:
        return audio_track(document.data), AUDIO_TRACK_MIMETYPE
    return document.data, document.mimetype or ""


def _check_capacity(
    env: Any, model: Any, audio: bytes, company_id: int, purpose: str
) -> None:
    capacity = get_router(env).audio_capacity(
        model, company_id=company_id, purpose=purpose
    )
    if capacity and len(audio) > capacity:
        raise UserError(
            env._(
                "The recording weighs %(size)s and %(vendor)s accepts at most "
                "%(capacity)s.",
                size=human_size(len(audio)),
                vendor=model.provider_id.name,
                capacity=human_size(capacity),
            )
        )
