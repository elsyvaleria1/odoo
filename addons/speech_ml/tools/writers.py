from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from odoo.libs.documents import TEXT, BaseWriter, register_writer, remembered

from .purposes import SYNTHESIS_PURPOSE, company_id_of
from odoo.addons.integration_machine_learning.tools.router import MlRequest, get_router

_logger = logging.getLogger(__name__)


SPEECH_MIMETYPES = frozenset(
    {"audio/aac", "audio/flac", "audio/mpeg", "audio/ogg", "audio/wav"}
)


def _speech_operations(env: Any) -> Any:
    return (
        env["integration.ml.provider.service"]
        .sudo()
        .search([("operation", "=", "synthesize")])
    )


def written_by(env: Any, vendor: str) -> frozenset[str]:
    return frozenset(
        mimetype
        for operation in _speech_operations(env)
        if operation.service_id.code == vendor
        for mimetype in (operation.formats or {})
    )


def _vendors(env: Any) -> frozenset[str]:
    return frozenset(_speech_operations(env).mapped("service_id.code"))


class AiSpeech(BaseWriter):
    name = "ai_speech"
    mimetype = ""
    consumes = TEXT
    module = "speech_ml"

    def __init__(self, mimetype: str) -> None:
        self.name = f"ai_speech_{mimetype.rsplit('/', 1)[-1]}"
        self.mimetype = mimetype

    def available(self, options: Mapping[str, Any]) -> bool:
        env = options.get("env")
        if env is None:
            return False
        return bool(
            self._model(
                env, company_id_of(env, options), options.get("purpose"), options
            )
        )

    def _model(
        self,
        env: Any,
        company_id: int,
        purpose: str | None,
        options: Mapping[str, Any],
    ) -> Any:
        return remembered(
            options,
            (self.name, company_id, purpose or SYNTHESIS_PURPOSE),
            lambda: self._pick_model(env, company_id, purpose),
        )

    def _pick_model(self, env: Any, company_id: int, purpose: str | None = None) -> Any:
        writing = [
            vendor
            for vendor in _vendors(env)
            if self.mimetype in written_by(env, vendor)
        ]
        return get_router(env).model_for(
            "synthesize",
            company_id=company_id,
            purpose=purpose or SYNTHESIS_PURPOSE,
            provider_code=writing,
        )

    def write(self, value: Any, **options: Any) -> bytes:
        env = options.get("env")
        if env is None:
            raise ValueError(
                "Speech synthesis needs an environment: pass env= to write audio"
            )
        company_id = company_id_of(env, options)
        purpose = options.get("purpose") or SYNTHESIS_PURPOSE
        model = self._model(env, company_id, purpose, options)
        if not model:
            raise ValueError("No speech model is configured with a usable credential")
        return (
            get_router(env)
            .run(
                "synthesize",
                MlRequest(
                    purpose=purpose,
                    text=str(value),
                    voice=options.get("voice"),
                    mimetype=self.mimetype,
                ),
                model=model,
                company_id=company_id,
            )
            .audio
        )


for _mimetype in sorted(SPEECH_MIMETYPES):
    register_writer(AiSpeech(_mimetype))
