import json
from logging import getLogger

import requests

from odoo import api, models
from odoo.exceptions import UserError

_logger = getLogger(__name__)


class AiLlmTransport(models.AbstractModel):
    """How ``LLMApiService`` puts a request on the wire.

    Split out of ``LLMApiService._request`` for the same reason as
    ``ai.llm.credential``: that class is instantiated directly and offers no
    extension point, so a deployment wanting its LLM traffic to go through a
    shared HTTP client -- for retry, rate limiting, response caching or an audit
    log -- has nothing to override. An AbstractModel does.

    The default is exactly what was inline before: one ``requests.request``, no
    retry, and the provider-shaped error unwrapping that turns a failure into a
    readable ``UserError``.
    """

    _name = "ai.llm.transport"
    _description = "AI Provider Transport"

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
        """Perform one request against a provider and return the decoded body.

        :param str provider: provider name, for overrides that route per provider
        :param str method: HTTP method
        :param str url: fully-built request URL
        :param dict headers: request headers
        :param dict body: JSON body
        :param dict data: form body, when not JSON
        :param dict files: multipart payload, e.g. audio for transcription
        :param dict params: query string parameters
        :param int timeout: seconds
        :return: the decoded JSON response
        :rtype: dict
        :raises UserError: the request failed, with the provider's message when
            one can be extracted
        """
        try:
            response = self.env["ir.egress"].request(
                method,
                url,
                purpose="ai_llm",
                policy="private",
                max_bytes=None,
                params=params,
                headers=headers,
                json=body,
                data=data,
                timeout=timeout,
                files=files,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise UserError(self._format_error(e)) from None

    @api.model
    def _format_error(self, exception):
        """Turn a failed request into the most readable message available.

        :param exception: the ``requests`` exception raised
        :return: a message safe to show the user
        :rtype: str
        """
        error = repr(exception)
        response = getattr(exception, "response", None)
        if response is not None:
            try:
                payload = response.json()
                if isinstance(payload, list) and payload:
                    # Gemini returns errors in a list
                    payload = payload[0]
                if isinstance(payload, dict) and (
                    json_error := payload.get("error", {}).get("message")
                ):
                    error = json_error
                else:
                    error = json.dumps(payload, indent=2)
            except ValueError:  # catch JSON decode errors
                error = response.text
            if not error:
                error = repr(exception)

        _logger.warning("LLM API request failed: %s", error)
        return error or self.env._("The AI provider rejected the request.")
