from odoo.exceptions import UserError


class LlmProviderHandler:
    name = None
    base_url = None

    def request_llm(self, service, *args, **kwargs):
        raise NotImplementedError

    def translate_inputs(self, inputs):
        return inputs

    def tool_schema(self, schema):
        return schema

    def tool_call_response(self, tool_call_id, return_value):
        raise NotImplementedError


class OpenAiProviderHandler(LlmProviderHandler):
    name = "openai"
    base_url = "https://api.openai.com/v1"

    def request_llm(self, service, *args, **kwargs):
        return service._request_llm_openai(*args, **kwargs)

    def tool_schema(self, schema):
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
    if not handler.name:
        raise ValueError("A provider handler needs a name")
    _PROVIDER_HANDLERS[handler.name] = handler


def get_provider_handler(env, provider):
    handler = _PROVIDER_HANDLERS.get(provider)
    if handler is None:
        raise UserError(env._("Unsupported provider '%s'", provider))
    return handler


def registered_providers():
    return list(_PROVIDER_HANDLERS)


register_provider_handler(OpenAiProviderHandler())
register_provider_handler(GoogleProviderHandler())
