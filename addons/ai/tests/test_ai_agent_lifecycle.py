from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAiAgentLifecycle(TransactionCase):
    def _agent(self, **extra):
        return self.env["ai.agent"].create(
            {"name": "Lifecycle Agent", "llm_model": "gpt-4", **extra}
        )

    def test_create_builds_archived_partner_and_placeholder_image(self):
        agent = self._agent()
        self.assertTrue(agent.partner_id)
        self.assertFalse(agent.partner_id.active)
        self.assertEqual(agent.partner_id.name, "Lifecycle Agent")
        self.assertTrue(agent.image_128)

    def test_partner_cannot_be_reassigned(self):
        agent = self._agent()
        other_partner = self.env["res.partner"].create({"name": "Impostor"})
        with self.assertRaises(ValidationError):
            agent.write({"partner_id": other_partner.id})

    def test_system_agent_cannot_be_deleted(self):
        agent = self._agent(is_system_agent=True)
        with self.assertRaises(UserError):
            agent.unlink()

    def test_regular_agent_can_be_deleted(self):
        agent = self._agent()
        agent.unlink()
        self.assertFalse(agent.exists())

    def test_copy_suffixes_name_unless_overridden(self):
        agent = self._agent()
        copy = agent.copy()
        self.assertEqual(copy.name, "Lifecycle Agent (copy)")
        named_copy = agent.copy(default={"name": "Exact Name"})
        self.assertEqual(named_copy.name, "Exact Name")
