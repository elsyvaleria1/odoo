from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.approval.tests.common import ApprovalCommon

TOOL_LOGGER = "odoo.addons.ai.models.ir_actions_server"


@tagged("post_install", "-at_install")
class TestAiToolCall(ApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent_user = new_test_user(
            cls.env,
            "ai_tool_agent_user",
            "base.group_user,base.group_partner_manager",
        )
        cls.partner = cls.env["res.partner"].create({"name": "Cliente"})
        cls.tool = cls.env["ir.actions.server"].create(
            {
                "name": "Rename contact",
                "model_id": cls.env["ir.model"]._get_id("res.partner"),
                "state": "code",
                "use_in_ai": True,
                "ai_tool_schema": (
                    '{"type": "object", "properties": {"name": {"type": "string"}},'
                    ' "required": ["name"]}'
                ),
                "code": (
                    "record.write({'name': name})\n"
                    "ai['result'] = {'model': record._name, 'id': record.id}"
                ),
            }
        )

    def setUp(self):
        super().setUp()
        self.category = self._make_category(
            name=f"AI tools {self.id()}", approvers=[self.approver_1]
        )

    def _call(self, arguments, user=None):
        user = user or self.agent_user
        tools = (
            self.tool.with_user(user).sudo()._get_ai_tools(self.partner.with_user(user))
        )
        (_description, _end, call, _schema) = tools[f"action_{self.tool.id}"]
        return call(arguments=arguments)

    def _held(self):
        self.tool.ai_approval_category_id = self.category
        return self.env["ai.tool.call"].search([("tool_id", "=", self.tool.id)])

    def _last_call(self):
        return self.env["ai.tool.call"].search(
            [("tool_id", "=", self.tool.id)], limit=1
        )

    def test_a_tool_without_approval_runs_at_once(self):
        _result, error = self._call({"name": "Cliente Uno"})
        self.assertIsNone(error)
        self.assertEqual(self.partner.name, "Cliente Uno")
        self.assertFalse(self._last_call())

    def test_a_held_tool_is_proposed_instead_of_run(self):
        self._held()
        answer, error = self._call({"name": "Cliente Dos"})
        self.assertIsNone(error)
        self.assertEqual(self.partner.name, "Cliente")
        call = self._last_call()
        self.assertEqual(call.state, "proposed")
        self.assertEqual(call.approval_state, "pending")
        self.assertEqual(call.requester_id, self.agent_user)
        self.assertEqual(
            (call.res_model, call.res_id), ("res.partner", self.partner.id)
        )
        self.assertIn("waits for a person", answer)

    def test_the_grant_applies_it_as_the_user_the_agent_worked_for(self):
        self._held()
        self._call({"name": "Cliente Tres"})
        call = self._last_call()
        call.approval_request_id.with_user(self.approver_1).action_approve()
        self.assertEqual(call.state, "applied")
        self.assertEqual(self.partner.name, "Cliente Tres")
        self.assertEqual(self.partner.write_uid, self.agent_user)
        self.assertEqual(
            (call.applied_res_model, call.applied_res_id),
            ("res.partner", self.partner.id),
        )

    def test_the_grant_runs_in_the_assignees_own_companies(self):
        self.agent_user.company_ids |= self.env["res.company"].create(
            {"name": "Otra empresa"}
        )
        assignee = new_test_user(
            self.env,
            "ai_tool_assignee",
            "base.group_user,base.group_partner_manager",
        )
        self._held()
        call = (
            self.env["ai.tool.call"]
            .with_user(self.agent_user)
            ._propose(
                self.tool, self.partner, {"name": "Cliente Cuatro"}, assignee=assignee
            )
        )
        call.approval_request_id.with_user(self.approver_1).action_approve()
        self.assertEqual(call.state, "applied", call.error)
        self.assertEqual(self.partner.name, "Cliente Cuatro")
        self.assertEqual(self.partner.write_uid, assignee)

    def test_a_refusal_rejects_it(self):
        self._held()
        self._call({"name": "Nunca"})
        call = self._last_call()
        call.approval_request_id.with_user(self.approver_1).with_context(
            skip_wizard=True
        ).action_refuse()
        self.assertEqual(call.state, "rejected")
        self.assertEqual(self.partner.name, "Cliente")

    def test_changing_the_arguments_after_the_grant_voids_it(self):
        self._held()
        self._call({"name": "Aprobado"})
        call = self._last_call()
        call.with_user(self.agent_user).arguments_text = '{"name": "Otro"}'
        call.approval_request_id.with_user(self.approver_1).action_approve()
        self.assertNotEqual(call.state, "applied")
        self.assertEqual(self.partner.name, "Cliente")
        request = call.approval_request_id
        self.assertEqual(request.state, "approved", "left as decided")
        call.action_apply()
        self.assertEqual(self.partner.name, "Cliente")
        self.assertEqual(request.state, "pending", "asked again for what is there")
        self.assertEqual(request.operation_snapshot["arguments"], {"name": "Otro"})

    def test_a_failure_is_kept_on_the_call(self):
        self.tool.code = "raise UserError('the tool broke')"
        self._held()
        self._call({"name": "x"})
        call = self._last_call()
        call.approval_request_id.with_user(self.approver_1).action_approve()
        self.assertEqual(call.state, "failed")
        self.assertIn("the tool broke", call.error)

    def test_the_decided_fields_are_not_edited_by_hand(self):
        self._held()
        self._call({"name": "x"})
        call = self._last_call().with_user(self.agent_user)
        with self.assertRaises(AccessError):
            call.state = "applied"

    def test_whoever_cannot_read_the_subject_cannot_read_the_call(self):
        self._held()
        self._call({"name": "x"})
        call = self._last_call()
        stranger = new_test_user(self.env, "ai_tool_stranger", "base.group_portal")
        with self.assertRaises(AccessError):
            call.with_user(stranger).read(["name"])

    def test_the_model_access_list_decides_generic_writes(self):
        Access = self.env["ai.tool.model.access"]
        with self.assertRaises(UserError):
            Access._check("res.bank", "create")
        Access.create(
            {
                "model_id": self.env["ir.model"]._get_id("res.bank"),
                "allow_create": True,
            }
        )
        Access._check("res.bank", "create")
        with self.assertRaises(UserError):
            Access._check("res.bank", "write")

    def test_a_request_binding_refuses_a_call_it_could_not_replay(self):
        self.env["approval.binding"].create(
            {
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "action_id": self.tool.id,
                "mode": "request",
                "category_id": self.category.id,
            }
        )
        with mute_logger(TOOL_LOGGER):
            _result, error = self._call({"name": "x"})
        self.assertIsInstance(error, UserError)
        self.assertIn("cannot be replayed", str(error))
        self.assertEqual(self.partner.name, "Cliente")

    def test_a_proposal_says_what_it_does_and_for_whom(self):
        self.tool.ai_approval_category_id = self.category
        call = self.env["ai.tool.call"]._propose(
            self.tool,
            self.partner,
            {"name": "x"},
            summary="Rename the customer",
            assignee=self.approver_1,
        )
        self.assertEqual(call.name, "Rename the customer: Cliente")
        self.assertEqual(call.assignee_id, self.approver_1)

    def test_a_proposal_nobody_can_approve_is_kept(self):
        self.tool.ai_approval_category_id = self.category
        with patch.object(
            type(self.env["ai.tool.call"]),
            "action_apply",
            side_effect=UserError("no approver"),
        ):
            call = self.env["ai.tool.call"]._propose(
                self.tool, self.partner, {"name": "x"}
            )
        self.assertTrue(call.exists())
        self.assertEqual(call.state, "proposed")
        self.assertIn("no approver", call.message_ids[:1].body)
