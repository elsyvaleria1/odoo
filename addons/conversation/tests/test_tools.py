from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import ConversationCase


class ConversationToolCase(ConversationCase):
    @classmethod
    def _functional_groups(cls):
        groups = cls.env["res.groups"]
        for ref in (
            "project.group_project_user",
            "product.group_product_manager",
            "base.group_partner_manager",
        ):
            groups |= cls.env.ref(ref)
        return groups

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        staff = cls.rep | cls.other_rep | cls.leader | cls.manager
        cls.env["hr.employee"].create(
            [
                {"name": user.name, "user_id": user.id, "company_id": cls.company.id}
                for user in staff
            ]
        )
        cls.project = cls.env["project.project"].create(
            {"name": "Plan de trabajo comercial (test)"}
        )
        cls.hub = cls.env["project.task"].create(
            {"name": "Junta hub", "project_id": cls.project.id}
        )

    def _proposal(self, key, arguments, conversation=None, assignee=None):
        tool = self.env["ir.actions.server"].search(
            [("conversation_key", "=", key)], limit=1
        )
        return self._propose_tool(tool, arguments, conversation, assignee)

    def _propose_tool(self, tool, arguments, conversation=None, assignee=None):
        conversation = conversation or self._recorded(hub_task_id=self.hub.id)
        return self.env["ai.tool.call"]._propose(
            tool,
            conversation,
            arguments,
            summary="Prueba",
            assignee=assignee or conversation.user_id,
        )


@tagged("post_install", "-at_install")
class TestConversationTools(ConversationToolCase):
    def test_the_person_in_charge_approves_and_the_task_is_created_as_them(self):
        call = self._proposal(
            "create_task", {"name": "Visita a Víctor", "date_end": "2026-09-21"}
        )
        self.assertEqual(call.approval_state, "pending")
        self._approve(call, self.rep)
        self.assertEqual(call.state, "applied", call.error)
        task = self.env["project.task"].browse(call.applied_res_id)
        self.assertEqual(task.project_id, self.project)
        self.assertIn(self.hub, task.predecessor_ids)
        self.assertEqual(task.create_uid, self.rep)

    def test_someone_else_cannot_approve_even_the_person_in_charge_tier(self):
        call = self._proposal("create_task", {"name": "Visita"})
        with self.assertRaises((AccessError, UserError)):
            self._approve(call, self.other_rep)
        self.assertNotEqual(call.state, "applied")

    def test_a_manager_tier_tool_waits_for_a_manager(self):
        call = self._proposal("create_product", {"name": "Prueba XM 1L"})
        with self.assertRaises((AccessError, UserError)):
            self._approve(call, self.leader)
        self._approve(call, self.manager)
        self.assertEqual(call.state, "applied", call.error)
        template = (
            self.env["product.template"]
            .with_context(active_test=False)
            .browse(call.applied_res_id)
        )
        self.assertEqual(template.name, "Prueba XM 1L")
        self.assertFalse(template.active, "a proposed product is born archived")
        self.assertTrue(template.sale_ok, "it is proposed as something to sell")

    def test_the_generic_create_tool_writes_only_what_the_list_allows(self):
        call = self._proposal(
            "create_record",
            {
                "model_name": "res.partner",
                "values_json": '{"name": "Cliente nuevo de prueba"}',
                "reason": "test",
            },
        )
        self._approve(call, self.manager)
        self.assertEqual(call.state, "failed")
        self.assertIn("may not create", call.error)
        self.env.ref("conversation.model_access_res_partner").allow_create = True
        call.action_apply()
        self.assertEqual(call.state, "applied", call.error)
        self.assertEqual(
            self.env["res.partner"].browse(call.applied_res_id).name,
            "Cliente nuevo de prueba",
        )

    def test_the_customer_may_be_updated_and_the_change_is_logged(self):
        call = self._proposal(
            "update_record",
            {
                "model_name": "res.partner",
                "res_id": self.customer.id,
                "values_json": '{"comment": "Siembra 40 ha"}',
                "reason": "lo dijo",
            },
        )
        self._approve(call, self.manager)
        self.assertEqual(call.state, "applied", call.error)
        self.assertIn("Siembra 40 ha", self.customer.comment)

    def test_a_record_the_conversation_did_not_create_is_not_updated(self):
        stranger = self.env["res.partner"].create({"name": "Ajeno"})
        call = self._proposal(
            "update_record",
            {
                "model_name": "res.partner",
                "res_id": stranger.id,
                "values_json": '{"comment": "x"}',
                "reason": "x",
            },
        )
        self._approve(call, self.manager)
        self.assertEqual(call.state, "failed")

    def test_a_calendar_event_is_booked_in_the_responsibles_time(self):
        conversation = self._recorded()
        conversation.attendee_ids = self.leader.partner_id
        call = self._proposal(
            "create_calendar_event",
            {
                "name": "Visita",
                "start": "2026-09-21 8:00",
                "attendee_names": ["Leader", "Extraño Ajeno"],
            },
            conversation=conversation,
        )
        self._approve(call, self.rep)
        self.assertEqual(call.state, "applied", call.error)
        event = self.env["calendar.event"].browse(call.applied_res_id)
        self.assertEqual(str(event.start), "2026-09-21 14:00:00")
        self.assertIn(self.leader.partner_id, event.partner_ids)
        self.assertIn(self.customer, event.partner_ids)

    def test_the_assignee_reaches_the_tool(self):
        call = self._proposal("create_task", {"name": "Visita"}, assignee=self.leader)
        self._approve(call, self.leader)
        self.assertEqual(call.state, "applied", call.error)
        task = self.env["project.task"].browse(call.applied_res_id)
        self.assertIn(self.leader, task.user_ids)

    def test_an_ambiguous_lookup_fails_instead_of_guessing(self):
        self.env["project.project"].create(
            [{"name": "Plan comercial norte"}, {"name": "Plan comercial sur"}]
        )
        call = self._proposal(
            "create_task", {"name": "X", "project_name": "Plan comercial"}
        )
        self._approve(call, self.rep)
        self.assertEqual(call.state, "failed")
        self.assertIn("norte", call.error)

    def test_the_catalog_offers_the_enabled_conversation_tools_only(self):
        catalog = self.env["ir.actions.server"]._conversation_catalog()
        keys = {tool["key"] for tool in catalog}
        self.assertIn("create_task", keys)
        tool = self.env.ref("conversation.tool_create_task")
        tool.conversation_enabled = False
        self.assertNotIn(
            "create_task",
            {
                tool["key"]
                for tool in self.env["ir.actions.server"]._conversation_catalog()
            },
        )
