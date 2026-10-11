from odoo import Command
from odoo.libs.json import dumps as json_dumps
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tests.common import users


@tagged("post_install", "-at_install")
class TestAiCrmTools(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public_user = new_test_user(
            cls.env, login="public_user", groups="base.group_public", name="Public"
        )
        cls.portal_user = new_test_user(
            cls.env,
            login="portal_user",
            groups="base.group_portal",
            name="Portal",
            email="portal@example.com",
        )
        cls.tag_ids = cls.env["crm.tag"].create(
            [
                {"name": "Team1"},
                {"name": "Team2"},
            ]
        )
        cls.team_ids = cls.env["team.team"].create(
            [
                {"use_sale": True, "name": "tag1"},
                {"use_sale": True, "name": "tag2"},
            ]
        )
        cls.agent = cls.env["ai.agent"].create({"name": "ai lead creation agent"})
        cls.channel = cls.env["discuss.channel"].create(
            {
                "name": "ai lead creation channel",
                "channel_type": "ai_chat",
                "ai_agent_id": cls.agent.id,
            }
        )

    def _use_create_lead_tool(self):
        tool = self.env.ref("ai_crm.ir_actions_server_ai_create_lead").sudo()
        tool.with_context({"discuss_channel": self.channel})._ai_tool_run(
            None,
            {
                "name": "AI Lead",
                "contact_name": "Frank",
                "description": '<p onclick="alert(1)">AI created lead</p>',
                "email": "mail@example.com",
                "phone": "+32123456789",
                "priority": "1",
                "team_id": self.team_ids[1].id,
                "tag_ids": self.tag_ids.ids,
                "country_id": self.env["res.country"]
                .search([("code", "=", "BE")], limit=1)
                .id,
                "state_id": self.env["res.country.state"]
                .search([("code", "=", "WLG")], limit=1)
                .id,
                "city": "Liège",
                "zip_code": "4000",
                "street": "Quai de Rome 1",
                "job_position": "Software Engineer",
            },
        )
        return self.env["crm.lead"].sudo().search([], order="id desc", limit=1)

    @users("public_user")
    def test_get_lead_create_available_params_tool(self):
        tool = self.env.ref(
            "ai_crm.ir_actions_server_ai_get_lead_create_available_params"
        ).sudo()
        prompt = tool._ai_tool_run(None, {})
        for rec in (*self.tag_ids, *self.team_ids):
            self.assertIn(
                json_dumps({"id": rec.id, "display_name": rec.display_name}), prompt
            )

    @users("public_user")
    def test_create_lead_tool_public(self):
        lead = self._use_create_lead_tool()
        self.assertEqual("AI Lead", lead.name)
        self.assertEqual("Frank", lead.contact_name)
        self.assertEqual("<p>AI created lead</p>", lead.description)
        self.assertEqual("mail@example.com", lead.email_from)
        self.assertEqual("+32123456789", lead._phone_get_number().number)
        self.assertEqual("1", lead.priority)
        self.assertEqual(self.team_ids[1], lead.team_id)
        self.assertEqual(self.tag_ids, lead.tag_ids)
        self.assertFalse(lead.user_id)
        self.assertEqual("Website", lead.medium_id.name)
        self.assertEqual(self.agent.name, lead.source_id.name)
        self.assertEqual("BE", lead.country_id.code)
        self.assertEqual("WLG", lead.state_id.code)
        self.assertEqual("Liège", lead.city)
        self.assertEqual("4000", lead.zip)
        self.assertEqual("Quai de Rome 1", lead.street)
        self.assertEqual("Software Engineer", lead.function)

    @users("portal_user")
    def test_create_lead_tool_portal(self):
        self.portal_user.email = ""
        lead = self._use_create_lead_tool()
        self.assertEqual("mail@example.com", lead.email_from)
        self.assertEqual("+32123456789", lead._phone_get_number().number)
        self.assertEqual("BE", lead.country_id.code)
        self.assertEqual("WLG", lead.state_id.code)
        self.assertEqual("Liège", lead.city)
        self.assertEqual("4000", lead.zip)
        self.assertEqual("Quai de Rome 1", lead.street)
        self.assertEqual("Software Engineer", lead.function)

    @users("portal_user")
    def test_create_lead_tool_portal_no_overwrite(self):
        self.portal_user.city = "Brussels"
        self.portal_user.phone_ids = [
            Command.create({"number": "+32987654321", "type": "landline"})
        ]
        self.portal_user.function = "Data Analyst"
        lead = self._use_create_lead_tool()
        self.assertEqual("Portal", lead.contact_name)
        self.assertEqual("portal@example.com", lead.email_from)
        self.assertEqual("+32987654321", lead._phone_get_number().number)
        self.assertEqual("Data Analyst", lead.function)
        self.assertEqual("Brussels", lead.city)
        self.assertFalse(lead.country_id)
        self.assertFalse(lead.state_id)
        self.assertFalse(lead.zip)
        self.assertFalse(lead.street)
