from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.ai.utils.llm_provider_handlers import get_provider_handler
from odoo.addons.ai.utils.llm_providers import get_provider
from odoo.addons.ai_gateway_ml.utils.anthropic_handler import (
    AnthropicProviderHandler,
    _get_file_block,
)
from odoo.addons.integration_machine_learning.tools.ai_clients.claude import (
    ClaudeClient,
)


@tagged("post_install", "-at_install", "ai_gateway_ml")
class TestAnthropicRegistration(TransactionCase):
    def test_handler_is_registered(self):
        handler = get_provider_handler(self.env, "claude")
        self.assertIsInstance(handler, AnthropicProviderHandler)

    def test_models_resolve_to_the_provider(self):
        self.assertEqual(get_provider(self.env, "claude-sonnet-5"), "claude")

    def test_models_appear_in_the_agent_picker(self):
        selection = dict(self.env["ai.agent"]._get_llm_model_selection())
        self.assertIn("claude-sonnet-5", selection)
        self.assertIn("gpt-4o", selection)


@tagged("post_install", "-at_install", "ai_gateway_ml")
class TestAnthropicTranslation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = AnthropicProviderHandler()

    def test_text_file_becomes_a_text_block(self):
        block = _get_file_block({"mimetype": "text/plain", "value": "hello"})
        self.assertEqual(block, {"type": "text", "text": "hello"})

    def test_pdf_becomes_a_document_block(self):
        block = _get_file_block({"mimetype": "application/pdf", "value": "Zm9v"})
        self.assertEqual(block["type"], "document")
        self.assertEqual(block["source"]["media_type"], "application/pdf")
        self.assertEqual(block["source"]["data"], "Zm9v")

    def test_image_becomes_an_image_block(self):
        block = _get_file_block({"mimetype": "image/png", "value": "aW1n"})
        self.assertEqual(block["type"], "image")
        self.assertEqual(block["source"]["media_type"], "image/png")

    def test_tools_use_input_schema_not_parameters(self):
        schema = {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": [],
        }
        tools = {
            "do_thing": ("Does a thing", False, lambda arguments: (1, None), schema)
        }

        built = self.handler._get_tools(tools, None)

        self.assertEqual(len(built), 1)
        self.assertEqual(built[0]["name"], "do_thing")
        self.assertEqual(built[0]["input_schema"], schema)
        self.assertNotIn("parameters", built[0])

    def test_schema_request_adds_a_forced_tool(self):
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        built = self.handler._get_tools(None, schema)

        self.assertEqual([t["name"] for t in built], ["json_schema"])
        self.assertEqual(built[0]["input_schema"], schema)

    def test_text_response_is_returned(self):
        responses, actions, inputs = self.handler._parse(
            {"content": [{"type": "text", "text": "hello"}]}, [], False
        )
        self.assertEqual(responses, ["hello"])
        self.assertEqual(actions, [])
        self.assertEqual(inputs, [])

    def test_tool_use_becomes_a_next_action(self):
        response = {
            "content": [
                {"type": "text", "text": "let me check"},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "do_thing",
                    "input": {"a": 1},
                },
            ]
        }
        responses, actions, __ = self.handler._parse(response, [], False)

        self.assertEqual(actions, [("do_thing", "toolu_1", {"a": 1})])
        self.assertEqual(responses, [])

    def test_assistant_turn_is_appended_once_for_the_whole_turn(self):
        blocks = [
            {"type": "tool_use", "id": "toolu_1", "name": "a", "input": {}},
            {"type": "tool_use", "id": "toolu_2", "name": "b", "input": {}},
        ]
        __, actions, inputs = self.handler._parse({"content": blocks}, [], False)

        self.assertEqual(len(actions), 2)
        self.assertEqual(len(inputs), 1)
        self.assertEqual(inputs[0], {"role": "assistant", "content": blocks})

    def test_schema_tool_result_is_returned_as_json_text(self):
        response = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "t",
                    "name": "json_schema",
                    "input": {"answer": "42"},
                }
            ]
        }
        responses, actions, __ = self.handler._parse(response, [], True)

        self.assertEqual(responses, ['{"answer": "42"}'])
        self.assertEqual(actions, [])

    def test_tool_result_block_shape(self):
        entry = self.handler.tool_call_response("toolu_9", {"ok": True})
        self.assertEqual(entry["role"], "user")
        self.assertEqual(entry["content"][0]["type"], "tool_result")
        self.assertEqual(entry["content"][0]["tool_use_id"], "toolu_9")

    def test_request_builds_a_claude_payload(self):
        captured = {}

        class FakeClient(ClaudeClient):
            def __init__(self, env):
                self.env = env
                self.company_id = None

            def create_message(self, **payload):
                captured.update(payload)
                return {"content": [{"type": "text", "text": "ok"}]}

        with patch(
            "odoo.addons.integration_machine_learning.tools.get_claude_client",
            return_value=FakeClient(self.env),
        ):
            responses, __, __ = self.handler.request_llm(
                self.env["ai.llm.credential"],
                "claude-sonnet-5",
                ["be helpful"],
                ["what is 2+2"],
                files=[{"mimetype": "text/plain", "value": "context"}],
            )

        self.assertEqual(responses, ["ok"])
        self.assertEqual(captured["model"], "claude-sonnet-5")
        self.assertEqual(captured["system"], "be helpful")
        self.assertIn("max_tokens", captured, "Anthropic requires max_tokens")
        content = captured["messages"][0]["content"]
        self.assertEqual(content[0], {"type": "text", "text": "what is 2+2"})
        self.assertEqual(content[1], {"type": "text", "text": "context"})

    def test_a_schema_on_a_model_that_cannot_be_forced_asks_for_json(self):
        captured = {}

        class FakeClient(ClaudeClient):
            def __init__(self, env):
                self.env = env
                self.company_id = None

            def create_message(self, **payload):
                captured.update(payload)
                return {"content": [{"type": "text", "text": '{"answer": "4"}'}]}

        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        with patch(
            "odoo.addons.integration_machine_learning.tools.get_claude_client",
            return_value=FakeClient(self.env),
        ):
            responses, __, __ = self.handler.request_llm(
                self.env["ai.llm.credential"],
                "claude-fable-5-1",
                [],
                ["what is 2+2"],
                schema=schema,
            )

        self.assertEqual(responses, ['{"answer": "4"}'])
        self.assertNotIn("tool_choice", captured)
        self.assertNotIn("tools", captured)
        self.assertEqual(captured["output_config"]["format"]["type"], "json_schema")

    def test_flagship_models_are_offered(self):
        offered = dict(self.env["ai.agent"]._get_llm_model_selection())
        for model in ("claude-opus-5", "claude-sonnet-5", "claude-opus-4-8"):
            self.assertIn(model, offered)

    def test_every_offered_claude_model_is_a_row_that_says_what_it_refuses(self):
        offered = dict(self.env["ai.agent"]._get_llm_model_selection())
        client = ClaudeClient.__new__(ClaudeClient)
        client.env = self.env
        rows = client._get_model_rows()
        claude = [code for code in offered if code.startswith("claude-")]
        self.assertTrue(claude)
        for code in claude:
            self.assertIn(code, rows)
        self.assertFalse(rows["claude-opus-5"].sampling_params)
        self.assertFalse(rows["claude-fable-5-1"].forced_tool_choice)
