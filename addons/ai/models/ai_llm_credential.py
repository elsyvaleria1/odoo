import os

from odoo import api, models
from odoo.exceptions import UserError

# Where each built-in provider's key is read from when nothing overrides this.
PROVIDER_KEY_SOURCES = {
    "openai": {"config_key": "ai.openai_key", "env_var": "ODOO_AI_CHATGPT_TOKEN"},
    "google": {"config_key": "ai.google_key", "env_var": "ODOO_AI_GEMINI_TOKEN"},
}


class AiLlmCredential(models.AbstractModel):
    """Where ``LLMApiService`` gets an API key from.

    Split out of ``LLMApiService._get_api_token`` so that the lookup is an
    override point. ``LLMApiService`` is a plain class instantiated directly, so
    a module wanting to source keys differently -- from a credential vault, per
    company, per user -- has nothing to extend; an AbstractModel does, through
    the ordinary ``_inherit``.

    The default keeps the historical behaviour exactly: a system parameter, then
    an environment variable, for OpenAI and Google.
    """

    _name = "ai.llm.credential"
    _description = "AI Provider Credentials"

    @api.model
    def _get_api_token(self, provider):
        """Return the API key for ``provider``.

        Overrides should ``return super()._get_api_token(provider)`` when they
        have nothing for this provider, so the configured system parameter keeps
        working and the error message stays in one place.

        :param str provider: provider name, e.g. ``openai``
        :return: the API key
        :rtype: str
        :raises UserError: the provider is unknown, or has no key configured
        """
        source = PROVIDER_KEY_SOURCES.get(provider)
        if source is None:
            raise UserError(self.env._("Unsupported provider '%s'", provider))

        api_key = self.env["credential.credential"]._get_system_secret(
            source["config_key"]
        ) or os.getenv(source["env_var"])
        if api_key:
            return api_key

        raise UserError(self.env._("No API key set for provider '%s'", provider))
