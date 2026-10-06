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
        """Provider names that can embed, in upstream's own preference order.

        :return: names accepted by ``LLMApiService`` and by
            ``_get_embedding_model``
        :rtype: list

        This was the literal ``["openai", "google"]``, which restated two tables
        that already say it. ``_get_llm_providers()`` is the set of
        providers this fork can drive at all — every entry carries an
        ``embedding_model``, and a module registering a third through
        an ``_get_llm_providers`` override would have been invisible to a hardcoded pair.
        ``integration.ml.provider.has_embeddings`` is the per-vendor capability flag, and it
        already held the same answer: True for openai and gemini, False for
        claude, deepseek and deepgram.

        Deriving rather than restating is also what gives ``has_embeddings`` a
        reader. It had none, which is how the two could have drifted apart
        without anything failing.

        The name has to come from ``_get_llm_providers()`` rather than from the
        ``integration.ml.provider`` row: ``_get_embedding_model`` looks the return value up
        in that table and ``LLMApiService`` is constructed with it, so an
        ``integration_machine_learning`` service code — ``gemini`` where upstream says ``google`` — is
        not interchangeable here.
        """
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
