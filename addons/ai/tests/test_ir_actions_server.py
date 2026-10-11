from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.libs.json import dumps as json_dumps
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.ai.models.ir_actions_server import _logger as tool_logger
from odoo.addons.ai.utils.llm_api_service import LLMApiService


@tagged("post_install", "-at_install")
class TestAiServerActions(TransactionCase):
    def _mock_llm_api_get_token(self):
        def _mock_get_api_token(self):
            return "dummy"

        return patch.object(LLMApiService, "_get_api_token", _mock_get_api_token)

    def test_ai_server_action_access(self):
        user = new_test_user(
            self.env, "internal_user_ai", "base.group_user,base.group_partner_manager"
        )
        partner = self.env["res.partner"].create({"name": "Partner"})

        ir_action_tool = self.env["ir.actions.server"].create(
            {
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "code",
                "name": "Write Name",
                "use_in_ai": True,
                "code": "record.write({'name': 'Renamed'})",
                "group_ids": self.env.ref("base.group_system").ids,
            }
        )
        action = self.env["ir.actions.server"].create(
            {
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "ai",
                "name": "Test",
                "ai_tool_ids": ir_action_tool.ids,
                "ai_action_prompt": "Main Prompt",
            },
        )
        llm_calls = 0

        def _mocked_request_llm(
            service,
            llm_model,
            system_prompts,
            user_prompts,
            tools=None,
            files=None,
            schema=None,
            temperature=0.2,
            inputs=(),
            web_grounding=None,
        ):
            nonlocal llm_calls
            llm_calls += 1
            return ["Done"], [], []

        with patch.object(LLMApiService, "_request_llm", _mocked_request_llm):
            action.with_user(user).with_context(
                active_id=partner.id, active_model="res.partner"
            ).run()

        self.assertEqual(llm_calls, 1)

        tools = ir_action_tool.with_user(user).sudo()._get_ai_tools(partner)
        (_description, _end, call, _schema) = tools[f"action_{ir_action_tool.id}"]
        with mute_logger("odoo.addons.ai.models.ir_actions_server"):
            _result, error = call(arguments={})
        self.assertIsInstance(error, AccessError)
        self.assertEqual(partner.name, "Partner")

        _result, error = ir_action_tool._get_ai_tools(partner)[
            f"action_{ir_action_tool.id}"
        ][2](arguments={})
        self.assertIsNone(error)
        self.assertEqual(partner.name, "Renamed")

        action.group_ids = self.env.ref("base.group_system").ids
        llm_calls = 0

        with (
            patch.object(LLMApiService, "_request_llm", _mocked_request_llm),
            self.assertRaises(AccessError),
        ):
            action.with_user(user).with_context(
                active_id=partner.id, active_model="res.partner"
            ).run()

        self.assertEqual(llm_calls, 0)

    def test_ai_server_action_user_access(self):
        user = new_test_user(self.env, "internal_user_ai", "base.group_user")
        partner = self.env["res.partner"].create({"name": "Partner"})

        self.env["ir.access"].create(
            {
                "name": "no partner reads",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "group_id": self.env.ref("base.group_user").id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "r",
                "domain": "[(0, '=', 1)]",
            }
        )

        mock_request = self._create_mock_request(
            [
                {
                    "output": [
                        {
                            "type": "function_call",
                            "name": "ir_actions_server_search",
                            "call_id": "call_1",
                            "arguments": json_dumps(
                                {
                                    "model_name": "res.partner",
                                    "domain": json_dumps([["id", "=", partner.id]]),
                                    "fields": ["name"],
                                }
                            ),
                        },
                    ],
                },
                {
                    "output": [
                        {
                            "text": "Unable to fetch partner details due to access rights."
                        },
                    ],
                },
            ]
        )

        ask_ai_agent_sudo = (
            self.env["ai.agent"]._get_potential_ask_ai_agent().with_user(user).sudo()
        )

        ask_ai_agent_sudo.write({"llm_model": "gpt-4.1"})

        with (
            patch.object(LLMApiService, "_request", mock_request),
            patch.object(LLMApiService, "_get_api_token", return_value="dummy_token"),
            self.assertLogs(tool_logger, level="ERROR") as mock_tool_logger,
        ):
            ask_ai_agent_sudo._generate_response("test")

        (error_log_record,) = mock_tool_logger.records
        self.assertIn(
            "An error occurred while executing AI: Search: You are not allowed to access 'Contact' (res.partner) records.",
            error_log_record.msg,
        )

    @mute_logger("odoo.addons.ai.utils.llm_api_service")
    def test_ai_server_action_ai_tool(self):
        llm_calls = 0

        def _mocked_request_llm(
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
            nonlocal llm_calls
            llm_calls += 1
            tool_names = sorted(tools, key=lambda t: tools[t][0])
            self.assertEqual(len(tools or ()), 2)
            self.assertEqual(tool_names[0], f"action_{ir_action_tools[0].id}")
            self.assertEqual(tools[tool_names[0]][0], ir_action_tools[0].name)
            self.assertEqual(tool_names[1], f"action_{ir_action_tools[1].id}")
            self.assertEqual(tools[tool_names[1]][0], ir_action_tools[1].name)
            if llm_calls == 1:
                self.assertFalse(inputs)
                return self._ai_tool_call(tool_names[0], "call_123456", {})

            if llm_calls == 2:
                self.assertEqual(len(inputs), 2)
                self.assertEqual(inputs[0].get("call_id"), "call_123456")
                self.assertEqual(inputs[1].get("call_id"), "call_123456")
                self.assertEqual(inputs[1].get("output"), "133333337")
                self.assertEqual(inputs[1].get("type"), "function_call_output")
                return self._ai_tool_call(
                    tool_names[1],
                    "call_789123",
                    {"value": "new name", "__end_message": "Renamed!"},
                )

            return ["Done"], [], []

        partner = self.env["res.partner"].create({"name": "Partner"})

        ir_action_tools = self.env["ir.actions.server"].create(
            [
                {
                    "model_id": self.env["ir.model"]._get_id("res.partner"),
                    "state": "code",
                    "name": "Return Value",
                    "use_in_ai": True,
                    "code": "ai['result'] = 133333337",
                },
                {
                    "model_id": self.env["ir.model"]._get_id("res.partner"),
                    "state": "code",
                    "name": "Write Name",
                    "use_in_ai": True,
                    "code": "record.write({'name': value})",
                },
            ]
        )

        action = self.env["ir.actions.server"].create(
            {
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "ai",
                "name": "Test",
                "ai_tool_ids": ir_action_tools.ids,
                "ai_action_prompt": "Main Prompt",
            },
        )

        with patch.object(LLMApiService, "_request_llm", _mocked_request_llm):
            action.with_context(active_model=partner._name, active_id=partner.id).run()

        self.assertEqual(llm_calls, 2)
        self.assertEqual(partner.name, "new name")

        bad_action = self.env["ir.actions.server"].create(
            {
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "code",
                "name": "Bad Action",
                "use_in_ai": True,
                "code": "record.write({'name': 'bad'})",
            }
        )

        llm_calls = 0

        def _mocked_request_llm_bad_action(*args, **kwargs):
            nonlocal llm_calls
            llm_calls += 1
            if llm_calls == 1:
                return self._ai_tool_call(f"action_{bad_action.id}", "call_123456", {})
            return ["Done"], [], []

        with patch.object(
            LLMApiService, "_request_llm", _mocked_request_llm_bad_action
        ):
            action.with_context(active_model=partner._name, active_id=partner.id).run()

        self.assertEqual(llm_calls, 2)
        self.assertEqual(
            partner.name,
            "new name",
            "Should not execute the action because it's not listed in the tools",
        )

        def _patched_check_access_to_run(*__):
            raise AccessError("")

        with (
            patch.object(
                self.env.registry["ir.actions.server"],
                "_check_access_to_run",
                _patched_check_access_to_run,
            ),
            self.assertRaises(AccessError),
        ):
            action.with_context(active_model=partner._name, active_id=partner.id).run()

        ir_action_tools[1].use_in_ai = False
        partner.name = "name"
        llm_calls = 0

        def _mocked_request_llm_use_in_ai_false(
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
            nonlocal llm_calls
            llm_calls += 1
            self.assertEqual(len(tools), 1)
            if llm_calls == 1:
                return self._ai_tool_call(
                    f"action_{ir_action_tools[1].id}",
                    "call_789123",
                    {"value": "new name"},
                )
            return ["Done"], [], []

        with patch.object(
            LLMApiService, "_request_llm", _mocked_request_llm_use_in_ai_false
        ):
            action.with_context(active_model=partner._name, active_id=partner.id).run()

        self.assertEqual(llm_calls, 2)
        self.assertEqual(
            partner.name, "name", "The action is disabled and should not be executed"
        )

    @mute_logger("odoo.addons.ai.models.ir_actions_server")
    def test_ai_server_action_ai_interactive_tool(self):
        llm_calls = 0

        def _mocked_request_llm(
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
            nonlocal llm_calls
            llm_calls += 1
            if llm_calls == 1:
                self.assertFalse(inputs)
                return self._ai_tool_call(
                    f"action_{ir_action_tool.id}", "call_123456", {}
                )
            return ["Done"], [], []

        partner = self.env["res.partner"].create({"name": "Partner"})

        ir_action_tool = self.env["ir.actions.server"].create(
            {
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "code",
                "name": "Return Value",
                "use_in_ai": True,
                "code": """action = {
                "type": "ir.actions.act_window",
                "res_model": "res.partner",
                "target": "new",
            }
            """,
            }
        )

        action = self.env["ir.actions.server"].create(
            {
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "ai",
                "name": "Test",
                "ai_tool_ids": ir_action_tool.ids,
                "ai_action_prompt": "Main Prompt",
            },
        )

        with patch.object(LLMApiService, "_request_llm", _mocked_request_llm):
            action.with_context(active_model=partner._name, active_id=partner.id).run()

        self.assertEqual(llm_calls, 2)
        self.assertIn(
            "This action is interactive and cannot be executed by the agent.",
            "".join(partner.message_ids.mapped("body")),
            "Should log the error on the partner",
        )

    def _ai_tool_call(self, name, call_id, arguments):
        return (
            ["Done"],
            [(name, call_id, arguments)],
            [{"call_id": call_id, "name": name, "arguments": json_dumps(arguments)}],
        )

    def _create_mock_request(self, responses):
        call_count = 0

        def mock_request(*args, **kwargs):
            nonlocal call_count
            result = responses[call_count]
            call_count += 1
            return result

        return mock_request

    def test_ai_create_activity(self):
        create_activity_action = self.env["ir.actions.server"].create(
            {
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "next_activity",
                "name": "create activity",
                "use_in_ai": True,
                "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                "activity_note": "created by AI",
            }
        )
        ai_action = self.env["ir.actions.server"].create(
            {
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "ai",
                "name": "call create activity",
                "ai_action_prompt": "create an activity",
                "ai_tool_ids": create_activity_action.ids,
            }
        )

        def _mocked_request_llm(*args, **kwargs):
            return self._ai_tool_call(
                f"action_{create_activity_action.id}", "call_111111", {}
            )

        with patch.object(LLMApiService, "_request_llm", _mocked_request_llm):
            ai_action._ai_action_run(self.env.user.partner_id)
        self.assertIn("created by AI", self.env.user.partner_id.activity_ids[0].note)

    def test_ai_send_mail(self):
        partner_model_id = self.env["ir.model"]._get_id("res.partner")
        send_mail_action = self.env["ir.actions.server"].create(
            {
                "model_id": partner_model_id,
                "state": "mail_post",
                "name": "send mail",
                "use_in_ai": True,
                "template_id": self.env["mail.template"]
                .create(
                    {
                        "name": "Test template",
                        "model_id": partner_model_id,
                        "subject": "mail sent by AI",
                    }
                )
                .id,
            }
        )
        ai_action = self.env["ir.actions.server"].create(
            {
                "model_id": partner_model_id,
                "state": "ai",
                "name": "send mail",
                "ai_action_prompt": "send an email",
                "ai_tool_ids": send_mail_action.ids,
            }
        )

        def _mocked_request_llm(*args, **kwargs):
            return self._ai_tool_call(
                f"action_{send_mail_action.id}", "call_111111", {}
            )

        with patch.object(LLMApiService, "_request_llm", _mocked_request_llm):
            ai_action._ai_action_run(self.env.user.partner_id)

        self.assertTrue(
            any(
                msg.subject == "mail sent by AI"
                for msg in self.env.user.partner_id.message_ids
            )
        )
