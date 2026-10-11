import logging

from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.ai.utils.llm_providers import Provider

_logger = logging.getLogger(__name__)


class AiAgent(models.Model):
    _inherit = "ai.agent"

    @api.model
    def _get_llm_providers(self):
        providers = super()._get_llm_providers()
        rows = (
            self.env["integration.ml.model"]
            .sudo()
            .search(
                [
                    ("provider_id.endpoint_id.code", "=", "claude"),
                    ("kind", "=", "chat"),
                ],
                order="sequence, name",
            )
        )
        if rows:
            providers.append(
                Provider(
                    "claude",
                    "Anthropic",
                    None,
                    {},
                    [(row.code, row.name) for row in rows],
                )
            )
        return providers

    def _get_embedding_provider(self):
        self.check_singleton()
        provider = self._get_provider()
        if provider != "claude":
            return super()._get_embedding_provider()

        for candidate in self._embedding_capable_providers():
            if self._has_usable_credentials(candidate):
                _logger.debug(
                    "Agent %s is on Claude; embedding its RAG query with %s",
                    self.display_name,
                    candidate,
                )
                return candidate

        raise UserError(
            self.env._(
                "This agent uses Claude, which has no embeddings API, so its "
                "sources need another provider to search them. Configure an "
                "OpenAI or Google key and try again."
            )
        )

    def _embedding_capable_providers(self):
        endpoint_codes = self.env["ai.llm.credential"]._PROVIDER_ENDPOINT_CODES
        registry = self.env["integration.ml.provider"].sudo()
        capable = []
        for provider in self._get_llm_providers():
            code = endpoint_codes.get(provider.name, provider.name)
            record = registry.search(
                [("endpoint_id.code", "=", code), ("has_embeddings", "=", True)],
                limit=1,
            )
            if record:
                capable.append(provider.name)
        return capable

    def _has_usable_credentials(self, provider) -> bool:
        try:
            return bool(self.env["ai.llm.credential"]._get_api_token(provider))
        except UserError:
            return False
