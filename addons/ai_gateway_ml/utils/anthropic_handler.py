import logging

from odoo.libs.json import dumps as json_dumps

from odoo.addons.integration_machine_learning.tools.ai_clients import claude as _claude

_logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 8192

_SCHEMA_TOOL = "json_schema"


def _get_file_block(file) -> dict:
    mimetype = file["mimetype"]
    if mimetype == "text/plain":
        return {"type": "text", "text": file["value"]}

    block_type = "document" if mimetype == "application/pdf" else "image"
    return {
        "type": block_type,
        "source": {
            "type": "base64",
            "media_type": mimetype,
            "data": file["value"],
        },
    }


class AnthropicProviderHandler:
    name = "claude"
    base_url = None

    def request_llm(
        self,
        service,
        llm_model,
        system_prompts,
        user_prompts,
        tools=None,
        files=None,
        schema=None,
        temperature=0.2,
        inputs=(),
        web_grounding=False,
    ):
        from odoo.addons.integration_machine_learning.tools import get_claude_client

        content = [{"type": "text", "text": prompt} for prompt in user_prompts]
        content.extend(_get_file_block(f) for f in files or ())

        messages = [{"role": "user", "content": content}, *(inputs or ())]
        payload = {
            "messages": messages,
            "model": llm_model,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "temperature": temperature,
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)

        client = get_claude_client(service.env)
        schema_as_tool = schema and client._accepts_forced_tool(llm_model)
        claude_tools = self._get_tools(tools, schema if schema_as_tool else None)
        if claude_tools:
            payload["tools"] = claude_tools
        if schema_as_tool:
            payload["tool_choice"] = {"type": "tool", "name": _SCHEMA_TOOL}
        elif schema:
            payload["output_config"] = _claude.get_json_output_config(schema)

        response = client.create_message(**payload)
        return self._parse(response, inputs, bool(schema))

    def _get_tools(self, tools, schema):
        claude_tools = [
            {
                "name": name,
                "description": description,
                "input_schema": parameter_schema,
            }
            for name, (description, __, __, parameter_schema) in (tools or {}).items()
        ]
        if schema:
            claude_tools.append(
                {
                    "name": _SCHEMA_TOOL,
                    "description": "Return the answer in this exact structure.",
                    "input_schema": schema,
                }
            )
        return claude_tools

    def _parse(self, response, inputs, wants_schema):
        blocks = response.get("content") or []
        next_inputs = list(inputs or ())

        responses = []
        next_actions = []
        for block in blocks:
            if block.get("type") != "tool_use":
                continue
            if wants_schema and block.get("name") == _SCHEMA_TOOL:
                responses.append(json_dumps(block.get("input") or {}))
                continue
            next_actions.append(
                (block.get("name", ""), block.get("id"), block.get("input") or {})
            )

        if not next_actions:
            responses.extend(
                text
                for block in blocks
                if block.get("type") == "text" and (text := block.get("text"))
            )
        else:
            next_inputs.append({"role": "assistant", "content": blocks})

        return responses, next_actions, next_inputs

    def translate_inputs(self, inputs):
        return inputs

    def tool_schema(self, schema):
        return schema

    def tool_call_response(self, tool_call_id, return_value):
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": str(return_value),
                }
            ],
        }
