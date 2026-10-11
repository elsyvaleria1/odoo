from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from odoo.libs.documents import (
    CUES,
    METERED,
    RECORDING_MIMETYPES,
    BaseReader,
    Cue,
    decode_audio,
    register_reader,
)
from odoo.tools import config

from .engine import LocalDiarizer, LocalEngine

_logger = logging.getLogger(__name__)

MODEL_DIR_PARAM = "speech_local.model_dir"

_ENGINES: dict[Path, LocalEngine] = {}
_DIARIZERS: dict[Path, LocalDiarizer] = {}
_REPORTED: set[Path] = set()


def shared_model_dir(env: Any) -> Path:
    configured = env.registry.settings.get(env, MODEL_DIR_PARAM, False)
    if configured:
        return Path(configured)
    return Path(config["data_dir"]) / "models" / "speech_local"


def purpose_model_dir(env: Any, purpose: str | None) -> Path | None:
    if not purpose:
        return None
    directory = shared_model_dir(env) / purpose
    return None if LocalEngine.missing_files(directory) else directory


def model_dir(env: Any, purpose: str | None = None) -> Path:
    return purpose_model_dir(env, purpose) or shared_model_dir(env)


def local_engine(env: Any, purpose: str | None = None) -> LocalEngine | None:
    directory = model_dir(env, purpose)
    if directory in _ENGINES:
        return _ENGINES[directory]
    missing = LocalEngine.missing_files(directory)
    if missing:
        if directory not in _REPORTED:
            _REPORTED.add(directory)
            _logger.info(
                "No local transcription: %s lacks %s",
                directory,
                ", ".join(missing),
            )
        return None
    return _ENGINES.setdefault(directory, LocalEngine(directory))


def local_diarizer(env: Any, purpose: str | None = None) -> LocalDiarizer | None:
    directory = model_dir(env, purpose)
    if directory in _DIARIZERS:
        return _DIARIZERS[directory]
    if not LocalDiarizer.available(directory):
        return None
    return _DIARIZERS.setdefault(directory, LocalDiarizer(directory))


class LocalTranscription(BaseReader):
    name = "local_transcription"
    mimetypes = RECORDING_MIMETYPES
    yields = (CUES,)
    cost = METERED
    defers = True
    module = "speech_local"
    async_only = True

    def available(self, options: Mapping[str, Any]) -> bool:
        env = options.get("env")
        return env is not None and local_engine(env, options.get("purpose")) is not None

    def defers_on(self, document: Any) -> bool:
        env = document.options.get("env")
        purpose = document.options.get("purpose")
        return env is None or purpose_model_dir(env, purpose) is None

    def read(self, document: Any) -> list[Cue] | None:
        env = document.options.get("env")
        if env is None:
            return None
        engine = local_engine(env, document.options.get("purpose"))
        if engine is None:
            return None
        return engine.transcribe(
            decode_audio(document.data), document.options.get("language")
        )


register_reader(LocalTranscription())
