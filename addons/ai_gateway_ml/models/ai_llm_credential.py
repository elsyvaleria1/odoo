import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class AiLlmCredential(models.AbstractModel):
    _inherit = "ai.llm.credential"

    _PROVIDER_ENDPOINT_CODES = {"google": "gemini"}

    @api.model
    def _get_api_token(self, provider):
        code = self._PROVIDER_ENDPOINT_CODES.get(provider, provider)
        credential = self._get_vault_credential(code)
        if credential:
            api_key = credential._use_secret_payload("ai_gateway_ml:api_key").get(
                "api_key"
            )
            if api_key:
                return api_key
            _logger.warning(
                "Credential %s is linked to AI service '%s' but carries no API "
                "key; falling back to the system parameter",
                credential.display_name,
                code,
            )

        _logger.debug(
            "No vault credential for AI provider '%s' (service '%s'); using the "
            "upstream system-parameter lookup",
            provider,
            code,
        )
        return super()._get_api_token(provider)

    @api.model
    def _get_vault_credential(self, endpoint_code):
        return self.env["credential.credential"]._get_for_endpoint_code(endpoint_code)
