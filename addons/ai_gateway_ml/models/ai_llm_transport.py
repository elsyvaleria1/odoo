import logging

from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.integration.tools.api_client import OutboundAPIClient
from odoo.addons.integration.tools.exceptions import CommError

_logger = logging.getLogger(__name__)

DEFAULT_PURPOSE = "ai"


class AiLlmTransport(models.AbstractModel):
    _inherit = "ai.llm.transport"

    _PROVIDER_ENDPOINT_CODES = {"google": "gemini"}

    @api.model
    def _request(
        self,
        provider,
        method,
        url,
        headers,
        body,
        data=None,
        files=None,
        params=None,
        timeout=30,
        purpose=None,
    ):
        purpose = purpose or DEFAULT_PURPOSE
        self._check_purpose(provider, purpose)
        service = None if files or data else self._get_transport_service(provider)
        if not service:
            return super()._request(
                provider,
                method,
                url,
                headers,
                body,
                data=data,
                files=files,
                params=params,
                timeout=timeout,
                purpose=purpose,
            )

        from odoo.addons.integration.tools import get_api_client

        annotated = self.with_context(
            **{
                OutboundAPIClient.EVENT_LOG_ANNOTATIONS_KEY: {
                    "tags": f"ai_provider:{provider},purpose:{purpose}"
                }
            }
        )
        try:
            client = get_api_client(annotated.env, service.code)
            response = client.request(
                method,
                self._endpoint_for(url, service),
                json=body,
                params=params,
                headers=headers,
            )
        except CommError as e:
            _logger.warning(
                "LLM request to %s failed on the transport: %s", provider, e
            )
            raise UserError(str(e)) from None

        return response.get("body", response)

    @api.model
    def _check_purpose(self, provider, purpose) -> None:
        self.env["integration.ml.policy"]._check_allowed(
            self.env.company, purpose, self._get_gateway_provider(provider)
        )

    @api.model
    def _get_gateway_provider(self, provider):
        code = self._PROVIDER_ENDPOINT_CODES.get(provider, provider)
        return (
            self.env["integration.ml.provider"]
            .sudo()
            .search([("code", "=", code)], limit=1)
            or self.env["integration.ml.provider.service"]
            .sudo()
            .search([("service_id.code", "=", code)], limit=1)
            .provider_id
        )

    @api.model
    def _endpoint_for(self, url, service):
        base = (service.endpoint_url or "").rstrip("/")
        if base and url.startswith(base):
            return url[len(base) :] or "/"
        return url

    @api.model
    def _get_transport_service(self, provider):
        code = self._PROVIDER_ENDPOINT_CODES.get(provider, provider)
        service = (
            self.env["integration.service"]
            .sudo()
            .search([("code", "=", code), ("active", "=", True)], limit=1)
        )
        if not service:
            return service

        # The same "is this service usable here" question the credential model
        # answers; only the return differs, since the caller wants the service
        # and not the key.
        credential = self.env["credential.credential"]._get_for_endpoint(service)
        return service if credential else service.browse()
