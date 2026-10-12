import os

from odoo import api, models
from odoo.exceptions import UserError

PROVIDER_KEY_SOURCES = {
    "openai": {"config_key": "ai.openai_key", "env_var": "ODOO_AI_CHATGPT_TOKEN"},
    "google": {"config_key": "ai.google_key", "env_var": "ODOO_AI_GEMINI_TOKEN"},
}


class AiLlmCredential(models.AbstractModel):
    _name = "ai.llm.credential"
    _description = "AI Provider Credentials"

    @api.model
    def _get_api_token(self, provider):
        source = PROVIDER_KEY_SOURCES.get(provider)
        if source is None:
            raise UserError(self.env._("Unsupported provider '%s'", provider))

        api_key = self.env["credential.credential"]._get_system_secret(
            source["config_key"]
        ) or os.getenv(source["env_var"])
        if api_key:
            return api_key

        raise UserError(self.env._("No API key set for provider '%s'", provider))
