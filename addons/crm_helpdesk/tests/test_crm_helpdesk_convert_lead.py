from odoo.exceptions import AccessError
from odoo.tests.common import tagged, users

from odoo.addons.helpdesk.tests import common as helpdesk_common
from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("lead_manage")
class TestTicketConvertToLead(helpdesk_common.HelpdeskCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.helpdesk_user.write({"login": "user_helpdesk_user"})
        cls.user_sales_leads = mail_new_test_user(
            cls.env,
            login="user_sales_leads",
            name="Laetitia Sales Leads",
            email="crm_leads@test.example.com",
            notification_type="inbox",
            groups="sale.group_sale_salesman_all_leads,base.group_partner_manager",
        )
        cls.test_team = cls.env["team.team"].create(
            {
                "use_sale": True,
                "name": "Test Crm Team",
                "member_ids": [(4, cls.user_sales_leads.id)],
            }
        )

        cls.test_campaign = cls.env["utm.campaign"].create(
            {
                "name": "A test UTM campaign",
            }
        )
        cls.test_medium = cls.env["utm.medium"].create({"name": "A test UTM medium"})
        cls.test_source = cls.env["utm.source"].create({"name": "A test UTM source"})

        cls.test_ticket = cls.env["helpdesk.ticket"].create(
            {
                "name": "Test Ticket",
                "user_id": cls.helpdesk_user.id,
                "partner_name": "My Test Customer",
                "partner_email": '"My Test Customer" <my.customer@example.com>',
                "email_cc": '"My Test Customer" <my.customer@example.com>',
                "campaign_id": cls.test_campaign.id,
                "team_id": False,
                "medium_id": cls.test_medium.id,
                "source_id": cls.test_source.id,
                "company_id": cls.main_company_id,
            }
        )

    def assertLeadTicketConvertData(self, lead, ticket, partner, crm_team, user_id):
        self.assertFalse(ticket.active)

        self.assertEqual(lead.name, ticket.name)
        self.assertEqual(lead.description, ticket.description)
        self.assertEqual(lead.partner_id, partner)
        self.assertEqual(lead.email_cc, ticket.email_cc)
        self.assertEqual(lead.email_from, partner.email)
        self.assertEqual(lead.phone_ids, partner.phone_ids)
        self.assertEqual(lead.team_id, crm_team)
        self.assertEqual(lead.user_id, user_id)
        self.assertEqual(lead.campaign_id, ticket.campaign_id)
        self.assertEqual(lead.medium_id, ticket.medium_id)
        self.assertEqual(lead.source_id, ticket.source_id)

    @users("user_helpdesk_user")
    def test_convert_to_lead_rights(self):
        self.helpdesk_user.write(
            {"group_ids": [(4, self.env.ref("sale.group_sale_salesman_all_leads").id)]}
        )
        ticket = self.env["helpdesk.ticket"].browse(self.test_ticket.ids)
        self.test_team.write({"member_ids": [(4, self.helpdesk_user.id)]})
        test_crm_team = self.env["team.team"].browse(self.test_team.ids)

        convert = (
            self.env["wizard.helpdesk.ticket.convert.lead"]
            .with_context(
                {
                    "active_model": ticket._name,
                    "active_id": ticket.id,
                }
            )
            .create(
                {
                    "team_id": test_crm_team.id,
                }
            )
        )
        self.assertEqual(convert.ticket_id, ticket)
        self.assertEqual(convert.user_id, self.helpdesk_user)

        convert.update({"user_id": self.user_sales_leads.id})
        action = convert.action_convert_to_lead()
        lead = self.env["crm.lead"].search([("name", "=", ticket.name)])
        self.assertEqual(action["res_model"], lead._name)
        self.assertLeadTicketConvertData(
            lead, ticket, ticket.partner_id, test_crm_team, self.user_sales_leads
        )

        ticket.write({"active": True})
        self.helpdesk_user.write(
            {"group_ids": [(3, self.env.ref("helpdesk.group_helpdesk_user").id)]}
        )

        with self.assertRaises(AccessError):
            convert = (
                self.env["wizard.helpdesk.ticket.convert.lead"]
                .with_context(
                    {
                        "active_model": ticket._name,
                        "active_id": ticket.id,
                    }
                )
                .create(
                    {
                        "team_id": test_crm_team.id,
                    }
                )
            )

    @users("user_helpdesk_user")
    def test_convert_to_lead_w_name_email(self):
        ticket = self.env["helpdesk.ticket"].browse(self.test_ticket.ids)

        self.assertEqual(ticket.partner_id.name, ticket.partner_name)
        self.assertEqual(ticket.partner_id.email, "my.customer@example.com")
        new_partner = self.env["res.partner"].search(
            [("email_normalized", "=", "my.customer@example.com")]
        )
        self.assertEqual(ticket.partner_id, new_partner)

        msg = ticket.message_post(
            body="Youplaboum", subtype_xmlid="mail.mt_comment", message_type="comment"
        )
        ticket_message_ids = ticket.message_ids

        test_crm_team = self.env["team.team"].browse(self.test_team.ids)

        convert = (
            self.env["wizard.helpdesk.ticket.convert.lead"]
            .with_context(
                {
                    "default_ticket_id": ticket.id,
                }
            )
            .create(
                {
                    "team_id": test_crm_team.id,
                }
            )
        )
        self.assertEqual(convert.action, "exist")
        self.assertEqual(convert.user_id, self.env["res.users"])

        action = convert.action_convert_to_lead()
        self.assertEqual(action["res_model"], ticket._name)

        lead = self.env["crm.lead"].sudo().search([("name", "=", ticket.name)])
        self.assertLeadTicketConvertData(
            lead, ticket, new_partner, test_crm_team, self.env["res.users"]
        )

        self.assertTrue(
            all(message in lead.message_ids for message in ticket_message_ids)
        )
        self.assertIn(msg, lead.message_ids)

    @users("user_helpdesk_user")
    def test_lead_convert_to_ticket_w_name(self):
        ticket = self.env["helpdesk.ticket"].browse(self.test_ticket.ids)
        ticket.update(
            {
                "partner_id": False,
                "partner_email": False,
            }
        )
        new_partner = self.env["res.partner"].search(
            [("email", "=", "my.customer@example.com")]
        )
        self.assertTrue(len(new_partner))

        test_crm_team = self.env["team.team"].browse(self.test_team.ids)

        convert = (
            self.env["wizard.helpdesk.ticket.convert.lead"]
            .with_context(
                {
                    "default_ticket_id": ticket.id,
                }
            )
            .create(
                {
                    "team_id": test_crm_team.id,
                }
            )
        )
        self.assertEqual(convert.action, "exist")
        self.assertEqual(convert.partner_id, new_partner)
        convert.action_convert_to_lead()

        lead = self.env["crm.lead"].sudo().search([("name", "=", ticket.name)])
        self.assertLeadTicketConvertData(
            lead, ticket, new_partner, test_crm_team, self.env["res.users"]
        )

    def test_helpdesk_ticket_to_lead(self):
        self.assertTrue(self.test_ticket.active)
        self.helpdesk_user.group_ids |= self.env.ref("crm.group_use_lead")
        action = self.test_ticket.with_user(
            self.helpdesk_user
        ).action_convert_ticket_to_lead_or_opportunity()
        self.assertEqual("Convert to Lead", action["name"])
        convert = self.env["wizard.helpdesk.ticket.convert.lead"].create(
            {"ticket_id": self.test_ticket.id}
        )
        convert.with_user(self.helpdesk_user).action_convert_to_lead()
        self.assertFalse(self.test_ticket.active)
        lead_count = self.env["crm.lead"].search_count(
            [("name", "=", self.test_ticket.name), ("type", "=", "lead")], limit=1
        )
        self.assertEqual(lead_count, 1)

    def test_helpdesk_ticket_to_opportunity(self):
        self.assertTrue(self.test_ticket.active)
        self.helpdesk_user.group_ids -= self.env.ref("crm.group_use_lead")
        action = self.test_ticket.with_user(
            self.helpdesk_user
        ).action_convert_ticket_to_lead_or_opportunity()
        self.assertEqual("Convert to Opportunity", action["name"])
        convert = self.env["wizard.helpdesk.ticket.convert.lead"].create(
            {"ticket_id": self.test_ticket.id}
        )
        convert.with_user(self.helpdesk_user).action_convert_to_lead()
        self.assertFalse(self.test_ticket.active)
        lead_count = self.env["crm.lead"].search_count(
            [("name", "=", self.test_ticket.name), ("type", "=", "opportunity")],
            limit=1,
        )
        self.assertEqual(lead_count, 1)
