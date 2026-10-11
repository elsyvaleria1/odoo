import copy
import json
import typing
from collections.abc import Callable
from itertools import starmap
from logging import getLogger
from typing import Any

from odoo.api import Environment
from odoo.libs.json import loads as json_loads

from .ai_logging import ai_response_logging, api_call_logging, get_ai_logging_session
from .llm_provider_handlers import get_provider_handler
from .llm_providers import check_model_depreciation

_logger = getLogger(__name__)


class Embedding(typing.TypedDict):
    index: int
    embedding: list[float]
    object: str


class EmbeddingResponse(typing.TypedDict):
    object: str
    data: list[Embedding]
    model: str
    usage: dict


class LLMApiService:
    def __init__(
        self, env: Environment, provider: str = "openai", *, purpose: str
    ) -> None:
        self.provider = provider
        self.purpose = purpose
        self.env = env
        self.handler = get_provider_handler(env, provider)
        self.base_url = self.handler.base_url

    def get_embedding(
        self,
        input: str | list[str] | list[int] | list[list[int]],
        dimensions: int,
        model: str = "text-embedding-3-small",
        encoding_format: str | None = None,
        user: str | None = None,
    ) -> EmbeddingResponse:
        check_model_depreciation(self.env, model)
        body = {"input": input, "model": model}
        self._add_if_set(body, "encoding_format", encoding_format)
        self._add_if_set(body, "dimensions", dimensions)
        self._add_if_set(body, "user", user)

        return self._request(
            method="post",
            endpoint="/embeddings",
            headers=self._get_base_headers(),
            body=body,
        )

    def _add_if_set(self, d: dict, key: str, value) -> None:
        if value is not None:
            d[key] = value

    def _get_base_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_api_token()}",
        }

    def _get_api_token(self):
        return self.env["ai.llm.credential"]._get_api_token(self.provider)

    def _request(
        self,
        method: str,
        endpoint: str,
        headers: dict[str, str],
        body: dict,
        data: dict | None = None,
        files: dict | None = None,
        params: dict | None = None,
        base_url: str | None = None,
        timeout: int = 30,
    ) -> dict:
        route = f"{base_url or self.base_url}/{endpoint.strip('/')}"
        return self.env["ai.llm.transport"]._request(
            self.provider,
            method,
            route,
            headers,
            body,
            data=data,
            files=files,
            params=params,
            timeout=timeout,
            purpose=self.purpose,
        )

    def _request_llm_openai(
        self,
        llm_model,
        system_prompts,
        user_prompts,
        tools=None,
        files=None,
        schema=None,
        temperature=0.2,
        inputs=(),
        web_grounding=False,
    ) -> tuple:
        user_content = [
            {"type": "input_text", "text": prompt} for prompt in user_prompts
        ]

        if files:

            def _get_file(idx, file):
                if file["mimetype"] == "text/plain":
                    return {"type": "input_text", "text": file["value"]}

                file_uri = f"data:{file['mimetype']};base64,{file['value']}"
                if file["mimetype"] == "application/pdf":
                    return {
                        "type": "input_file",
                        "filename": f"file_{idx}.pdf",
                        "file_data": file_uri,
                    }

                assert file["mimetype"].startswith("image/")
                return {"type": "input_image", "image_url": file_uri, "detail": "low"}

            user_content.extend(starmap(_get_file, enumerate(files, start=1)))

        body = {
            "model": llm_model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {"type": "input_text", "text": prompt}
                        for prompt in system_prompts
                    ],
                },
                {"role": "user", "content": user_content},
                *inputs,
            ],
            "store": False,
        }
        if llm_model not in ("gpt-5", "gpt-5-mini"):
            body["temperature"] = temperature

        if schema:
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "json_schema",
                    "schema": schema,
                    "strict": True,
                },
            }

        if tools:
            body["tools"] = self._to_open_ai_tool_schema(
                [
                    {
                        "description": tool_description,
                        "parameters": tool_parameter_schema,
                        "type": "function",
                        "name": tool_name,
                        "strict": True,
                    }
                    for tool_name, (
                        tool_description,
                        __,
                        __,
                        tool_parameter_schema,
                    ) in tools.items()
                ]
            )
            body["parallel_tool_calls"] = True

        if web_grounding:
            search_tool = {
                "type": "web_search_preview",
            }
            if country_code := self.env.company.country_id.code:
                search_tool["user_location"] = {
                    "type": "approximate",
                    "country": country_code,
                }
                if city := self.env.company.city:
                    search_tool["user_location"]["city"] = city
            body.setdefault("tools", []).append(search_tool)

        with api_call_logging(body["input"], tools) as record_response:
            response, to_call, next_inputs, request_token_usage = (
                self._request_llm_openai_helper(body, tools, inputs)
            )
            if record_response:
                record_response(to_call, response, request_token_usage)
            return response, to_call, next_inputs

    def _request_llm_openai_helper(self, body, tools=None, inputs=()) -> tuple:
        llm_response = self._request(
            method="post",
            endpoint="/responses",
            headers=self._get_base_headers(),
            body=body,
        )

        to_call = []
        response = []
        next_inputs = list(inputs or ())

        output_lines = llm_response.get("output") or []
        has_tool_calls = any(
            line.get("type") == "function_call" for line in output_lines
        )

        for line in output_lines:
            if line.get("type") == "function_call":
                tool_name = line.get("name", "")

                try:
                    arguments = json_loads(line.get("arguments") or "")
                except json.decoder.JSONDecodeError:
                    _logger.error("AI: Malformed arguments: %s", line)
                    continue

                to_call.append((tool_name, line.get("call_id"), arguments))
                next_inputs.append(line)

            elif not has_tool_calls:
                if text := line.get("text"):
                    response.append(text)
                elif line.get("type") == "message":
                    response.extend(
                        t for c in line.get("content", ()) if (t := c.get("text"))
                    )

        request_token_usage = {}
        if usage := llm_response.get("usage"):
            request_token_usage["input_tokens"] = usage.get("input_tokens", 0)
            request_token_usage["cached_tokens"] = usage.get(
                "input_tokens_details", {}
            ).get("cached_tokens", 0)
            request_token_usage["output_tokens"] = usage.get("output_tokens", 0)

        return response, to_call, next_inputs, request_token_usage

    def _request_llm_google(
        self,
        llm_model,
        system_prompts,
        user_prompts,
        tools=None,
        files=None,
        schema=None,
        temperature=0.2,
        inputs=(),
        web_grounding=False,
    ) -> tuple:
        if (tools or web_grounding) and schema:
            raise NotImplementedError(
                "Gemini does not support structured output with tools"
            )
        if web_grounding and tools:
            raise NotImplementedError(
                "Gemini does not support tools with web grounding"
            )
        body = {
            "contents": [],
            "generationConfig": {
                "temperature": temperature,
            },
        }
        if system_prompts:
            body["systemInstruction"] = {
                "parts": [{"text": prompt} for prompt in system_prompts],
            }
        if user_prompts:
            body["contents"].append(
                {
                    "role": "user",
                    "parts": [{"text": prompt} for prompt in user_prompts],
                }
            )

        body["contents"].extend(inputs)

        if files:

            def _get_file(idx, file):
                if file["mimetype"] == "text/plain":
                    return {"text": file["value"]}

                return {
                    "inline_data": {
                        "mime_type": file["mimetype"],
                        "data": file["value"],
                    }
                }

            body["contents"].append(
                {
                    "role": "user",
                    "parts": list(starmap(_get_file, enumerate(files, start=1))),
                }
            )

        if schema:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseJsonSchema"] = schema

        if tools:
            body["tools"] = {
                "functionDeclarations": [
                    {
                        "description": tool_description,
                        "parameters": tool_parameter_schema,
                        "name": tool_name,
                    }
                    for tool_name, (
                        tool_description,
                        __,
                        __,
                        tool_parameter_schema,
                    ) in tools.items()
                ]
            }
        if web_grounding:
            body["tools"] = {"google_search": {}}

        if llm_model == "gemini-2.5-flash":
            body["generationConfig"]["thinkingConfig"] = {
                "thinkingBudget": 512,
            }

        with api_call_logging(body["contents"], tools) as record_response:
            response = None
            to_call = []
            next_inputs = inputs
            request_token_usage = {}
            for _attempt in range(3):
                response, to_call, next_inputs, request_token_usage = (
                    self._request_llm_google_helper(body, llm_model, inputs)
                )
                if response or to_call:
                    break
                _logger.warning("Gemini failed to generate a response, retrying...")
            if not (response or to_call):
                response = "Error: failed to generate a response, try again later."
            if record_response:
                record_response(to_call, response, request_token_usage)
            return response, to_call, next_inputs

    def _request_llm_google_helper(self, body, llm_model, inputs=()) -> tuple:
        llm_response = self._request(
            method="post",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            headers={"x-goog-api-key": self._get_api_token()},
            endpoint=f"/models/{llm_model}:generateContent",
            params={},
            body=body,
        )

        to_call = []
        response = []
        next_inputs = list(inputs or ())

        candidates = llm_response.get("candidates") or []
        has_tool_calls = any(
            part.get("functionCall")
            for candidate in candidates
            for part in candidate.get("content", {}).get("parts") or []
        )

        for candidate in candidates:
            for line in candidate.get("content", {}).get("parts") or ():
                if f_info := line.get("functionCall"):
                    to_call.append((f_info["name"], f_info["name"], f_info["args"]))
                    next_inputs.append({"role": "model", "parts": [line]})
                elif not has_tool_calls:
                    if r := line.get("text"):
                        response.append(r)
                    else:
                        _logger.warning("Gemini: could not parse %s", line)

        request_token_usage = {}
        if usage := llm_response.get("usageMetadata"):
            request_token_usage["input_tokens"] = usage.get("promptTokenCount", 0)
            request_token_usage["cached_tokens"] = usage.get(
                "cachedContentTokenCount", 0
            )
            request_token_usage["output_tokens"] = usage.get("candidatesTokenCount", 0)

        return response, to_call, next_inputs, request_token_usage

    def _request_llm(self, *args, **kwargs):
        model = kwargs.get("llm_model") or args[0]
        check_model_depreciation(self.env, model)

        return self.handler.request_llm(self, *args, **kwargs)

    def request_llm(
        self,
        llm_model: str,
        system_prompts: list[str],
        user_prompts: list[str],
        tools: dict[str, tuple[str, bool, Callable[[dict[str, Any]], Any], dict]]
        | None = None,
        files: list[dict] | None = None,
        schema: dict | None = None,
        temperature: float = 0.2,
        inputs: list[dict] | None = None,
        web_grounding: bool = False,
    ) -> list[str]:
        check_model_depreciation(self.env, llm_model)
        with ai_response_logging(llm_model):
            return self._request_llm_silent(
                llm_model=llm_model,
                system_prompts=system_prompts,
                user_prompts=user_prompts,
                tools=tools,
                files=files,
                schema=schema,
                temperature=temperature,
                inputs=inputs,
                web_grounding=web_grounding,
            )

    def _request_llm_silent(
        self,
        llm_model: str,
        system_prompts: list[str],
        user_prompts: list[str],
        tools: dict[str, tuple[str, bool, Callable[[dict[str, Any]], Any], dict]]
        | None = None,
        files: list[dict] | None = None,
        schema: dict | None = None,
        temperature: float = 0.2,
        inputs: list[dict] | None = None,
        web_grounding: bool = False,
    ):
        AI_MAX_SUCCESSIVE_CALLS = int(
            self.env.registry.settings.get(self.env, "ai.max_successive_calls", "20")
        )

        AI_MAX_TOOL_CALLS_PER_CALL = int(
            self.env.registry.settings.get(self.env, "ai.max_tool_calls_per_call", "20")
        )

        if tools:
            tools = copy.deepcopy(tools)
            for __, allow_end_message, __, tool_parameter_schema in tools.values():
                if (
                    allow_end_message
                    and "__end_message" not in tool_parameter_schema["properties"]
                ):
                    tool_parameter_schema["properties"]["__end_message"] = {
                        "type": "string",
                        "description": "If you are not waiting a result and you are done, write here your last message (it must follow the instructions). If you will do an action after this one, leave it empty.",
                    }
                if (
                    "__end_message" in tool_parameter_schema["properties"]
                    and "__end_message" not in tool_parameter_schema["required"]
                ):
                    tool_parameter_schema["required"].append("__end_message")

        inputs = inputs or []

        inputs = self.handler.translate_inputs(inputs)

        all_responses = []
        for api_call in range(AI_MAX_SUCCESSIVE_CALLS):
            responses, next_actions, inputs = self._request_llm(
                llm_model,
                system_prompts,
                user_prompts,
                files=files,
                inputs=inputs,
                schema=schema,
                tools=tools,
                temperature=temperature,
                web_grounding=web_grounding,
            )
            all_responses.extend(responses)

            if not next_actions:
                break

            done = False
            session = get_ai_logging_session()

            if session:
                session["tool_calls"] += min(
                    len(next_actions), AI_MAX_TOOL_CALLS_PER_CALL
                )

            for i, (tool_name, call_id, arguments) in enumerate(next_actions):
                if i >= AI_MAX_TOOL_CALLS_PER_CALL:
                    _logger.warning(
                        "AI: Tool call limit reached, stopping further tool calls"
                    )
                    inputs.append(
                        self._get_tool_call_response(
                            call_id,
                            "Error: This tool call isn't processed because of tool call limit, try again",
                        )
                    )
                    continue

                if tool_name not in tools:
                    _logger.error("AI: Try to call a forbidden action %s", tool_name)
                    inputs.append(
                        self._get_tool_call_response(
                            call_id,
                            f"Error: unknown tool '{tool_name}'. Try again with the correct tool name.",
                        )
                    )
                    continue

                has_end_message = "__end_message" in arguments
                end_message = arguments.pop("__end_message", None)
                result, error = tools[tool_name][2](arguments=arguments)

                inputs.append(self._get_tool_call_response(call_id, result))

                if has_end_message and error is None:
                    done = True
                    if end_response := end_message and end_message.strip():
                        all_responses.append(end_response)
                        _logger.info("AI: action terminate early: %s", end_response)
                    else:
                        _logger.info("AI: action terminate early with empty message")

            if session and len(next_actions) > 1:
                _logger.debug(
                    "[AI Tool Summary] Batch #%d completed, %d tool calls",
                    session["current_batch_id"],
                    len(next_actions),
                )

            if done:
                break

        _logger.info("AI: API calls %s", api_call + 1)

        if not all_responses:
            error_msg = "Processing loop ended with no response."
            if api_call + 1 >= AI_MAX_SUCCESSIVE_CALLS:
                error_msg = "Number of successive API calls exceeded, please try again with a more precise request."
            raise ValueError(error_msg)

        return all_responses

    def _to_open_ai_tool_schema(self, schema):
        return self.handler.tool_schema(schema)

    def _get_tool_call_response(self, tool_call_id, return_value):
        return self.handler.tool_call_response(tool_call_id, return_value)
