from .voice import Heard
from odoo.addons.integration_machine_learning.tools import get_router


class BotAssistant:

    PURPOSE = None
    TRANSCRIBE_CONTEXT = ""
    TRANSCRIPTION_PURPOSE = None
    SETTINGS = (None, None, None)

    def __init__(self, bot) -> None:
        enabled, provider, preferred = self.SETTINGS
        self._bot = bot
        self._env = bot.env
        self._company = bot._acting_company()
        settings = bot.with_privilege(
            "integration_machine_learning.privilege_route_ml",
            reason="the bot's settings name the provider and model it routes to",
        )
        self._enabled = bool(settings[enabled])
        self._provider = settings[provider]
        self._preferred = settings[preferred]

    def _chat_model(self, images=False):
        return get_router(self._env).model_for(
            "chat",
            company_id=self._company.id,
            purpose=self.PURPOSE,
            images=images,
            provider_code=self._provider.code or None,
            preferred=self._preferred or None,
        )

    @property
    def _label(self):
        return self._chat_model().display_name or "unset"

    @property
    def available(self):
        return bool(self._enabled and self._chat_model())

    @property
    def _transcription(self):
        purpose = self.TRANSCRIPTION_PURPOSE
        return {"purpose": purpose} if purpose else {}

    @property
    def supports_audio(self):
        return self.available and self._bot._hears_voice_notes(
            **self._transcription, company=self._company
        )

    def hear(self, chat, message, **options):
        if not self.supports_audio:
            return Heard(failure="unheard")
        return self._bot._hear_message(
            chat,
            message,
            context=self.TRANSCRIBE_CONTEXT,
            company=self._company,
            **{**self._transcription, **options},
        )
