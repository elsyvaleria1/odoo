"""Per-provider wire format, separated from the request loop.

``LLMApiService`` owns what is the same for every provider: the successive-call
loop, tool execution, the call limits, logging. What differs is the wire format
— base URL, how a request is built and its response parsed, how conversation
history is shaped, how a tool schema and a tool result are expressed. That was
six ``if self.provider ==`` branches scattered across the class, and adding a
provider meant finding all six.

A handler collects them in one object. Built-in handlers are registered below;
another module registers its own with :func:`register_provider_handler`, and
nothing in ``LLMApiService`` needs to know it exists.
"""

from odoo.exceptions import UserError


class LlmProviderHandler:
    """The provider-shaped half of an LLM call.

    Subclasses set :attr:`name` and :attr:`base_url` and implement
    :meth:`request_llm` and :meth:`tool_call_response`. The rest have defaults
    that suit a provider speaking OpenAI's dialect.
    """

    #: provider key, as stored on ``integration.ml.provider``/used by ``LLMApiService``
    name = None
    #: root URL requests are built against
    base_url = None

    def request_llm(self, service, *args, **kwargs):
        """Perform one LLM call.

        :param service: the calling ``LLMApiService``
        :return: ``(responses, next_actions, inputs)`` where ``responses`` is a
            list of text replies, ``next_actions`` a list of
            ``(tool_name, call_id, arguments)`` the caller must execute, and
            ``inputs`` the conversation state to pass to the next call
        :rtype: tuple
        """
        raise NotImplementedError

    def translate_inputs(self, inputs):
        """Convert OpenAI-shaped conversation inputs into this provider's shape.

        :param list inputs: ``[{'role': ..., 'content': ...}, ...]``
        :return: the same history in the provider's own encoding
        :rtype: list
        """
        return inputs

    def tool_schema(self, schema):
        """Adjust a JSON-schema tool declaration for this provider.

        :param list schema: tool declarations
        :return: the declarations this provider accepts
        :rtype: list
        """
        return schema

    def tool_call_response(self, tool_call_id, return_value):
        """Express a tool's result as a conversation input.

        :param tool_call_id: identifier the provider gave the call
        :param return_value: what the tool returned
        :return: an entry to append to ``inputs``
        :rtype: dict
        """
        raise NotImplementedError


class OpenAiProviderHandler(LlmProviderHandler):
    name = "openai"
    base_url = "https://api.openai.com/v1"

    def request_llm(self, service, *args, **kwargs):
        return service._request_llm_openai(*args, **kwargs)

    def tool_schema(self, schema):
        # The `responses` endpoint needs every parameter in "required", but
        # accepts `"type": ["string", "null"]`: convert to the array version.
        for tool in schema:
            required = tool["parameters"]["required"]
            non_required = set(tool["parameters"]["properties"]) - set(required)
            for name in non_required:
                tool["parameters"]["properties"][name]["type"] = [
                    tool["parameters"]["properties"][name]["type"],
                    "null",
                ]
            tool["parameters"]["required"].extend(non_required)
            tool["parameters"]["additionalProperties"] = False
        return schema

    def tool_call_response(self, tool_call_id, return_value):
        return {
            "type": "function_call_output",
            "call_id": tool_call_id,
            "output": str(return_value),
        }


class GoogleProviderHandler(LlmProviderHandler):
    name = "google"
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai"

    def request_llm(self, service, *args, **kwargs):
        return service._request_llm_google(*args, **kwargs)

    def translate_inputs(self, inputs):
        return [
            {
                "role": "user" if i["role"] == "user" else "model",
                "parts": [{"text": i["content"]}],
            }
            for i in inputs
        ]

    def tool_call_response(self, tool_call_id, return_value):
        return {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": tool_call_id,
                        "response": {"result": str(return_value)},
                    },
                }
            ],
        }


_PROVIDER_HANDLERS = {}


def register_provider_handler(handler) -> None:
    """Make a provider usable by ``LLMApiService``.

    Call at import time from a module's ``models``/``utils`` package: addons are
    imported in dependency order, so a module depending on ``ai`` registers
    after the built-ins.

    :param handler: a :class:`LlmProviderHandler` instance
    """
    if not handler.name:
        raise ValueError("A provider handler needs a name")
    _PROVIDER_HANDLERS[handler.name] = handler


def get_provider_handler(env, provider):
    """Return the handler for ``provider``.

    :param env: Odoo environment, for the error message
    :param str provider: provider key
    :return: the registered handler
    :rtype: LlmProviderHandler
    :raises UserError: no handler is registered for this provider
    """
    handler = _PROVIDER_HANDLERS.get(provider)
    if handler is None:
        raise UserError(env._("Unsupported provider '%s'", provider))
    return handler


def registered_providers():
    """Return every registered provider key.

    :rtype: list
    """
    return list(_PROVIDER_HANDLERS)


register_provider_handler(OpenAiProviderHandler())
register_provider_handler(GoogleProviderHandler())
