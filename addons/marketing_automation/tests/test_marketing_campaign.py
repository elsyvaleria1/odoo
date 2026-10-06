from odoo.exceptions import UserError
from odoo.tests import tagged, users

from odoo.addons.marketing_automation.tests.common import MarketingAutomationCommon


@tagged("marketing_automation", "utm")
class TestMarketingCampaign(MarketingAutomationCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.activity = cls._create_activity_mail(
            cls.campaign,
            user=cls.user_marketing_automation,
            act_values={
                "trigger_type": "begin",
                "interval_number": 0,
                "interval_type": "hour",
            },
        )

    def test_the_workflow_canvas_names_campaign_steps_and_events(self):
        opened = self._create_activity(
            self.campaign,
            action=self._create_server_action("mailing.contact", "pass", name="Tag"),
            parent_id=self.activity.id,
            trigger_type="mail_open",
            interval_number=1,
            interval_type="day",
        )
        not_opened = self._create_activity(
            self.campaign,
            action=self._create_server_action("mailing.contact", "pass", name="Remind"),
            parent_id=self.activity.id,
            trigger_type="mail_not_open",
            interval_number=2,
            interval_type="day",
        )

        graph = self.campaign.automation_rule_id.get_workflow_graph()

        edge_labels = {edge["target"]: edge["event_label"] for edge in graph["edges"]}
        self.assertEqual(edge_labels[opened.node_id.id], "Mail: opened")
        self.assertEqual(edge_labels[not_opened.node_id.id], "Mail: not opened")
        details = {node["id"]: node["detail"] for node in graph["nodes"]}
        self.assertEqual(details[opened.node_id.id], "Server Action: Tag")
        self.assertTrue(details[self.activity.node_id.id].startswith("Email"))

    def test_a_campaign_opens_its_workflow(self):
        action = self.campaign.action_view_workflow()

        self.assertEqual(
            (action["res_model"], action["res_id"]),
            ("automation.rule", self.campaign.automation_rule_id.id),
        )

    @users("user_marketing_automation")
    def test_create_records_with_xml_ids(self):
        # The function tests creation of records.
        # If record is deleted and then re-created it has to get same xmlid.
        email = "ma.test.new.1@example.com"
        name = "MATest_new_1"
        create_xmls = {
            "xml_id": "marketing_automation.mail_contact_temp",
            "values": {
                "email": email,
                "name": name,
            },
        }
        self.env["marketing.campaign"].sudo()._create_records_with_xml_ids(
            {"mailing.contact": [create_xmls]}
        )

        # Retrieve the records using the XML IDs and verify they exist
        record = self.env.ref(
            "marketing_automation.mail_contact_temp", raise_if_not_found=False
        )
        self.assertTrue(record, "Record should exist after creation.")
        self.assertEqual(record.name, name, f"The value should be {name}")
        self.assertEqual(record.email, email, f"The value should be {email}")

        # Now delete the record
        record.unlink()
        self.assertFalse(record.exists(), "Record should be deleted.")
        record = self.env.ref(
            "marketing_automation.mail_contact_temp", raise_if_not_found=False
        )
        self.assertFalse(
            record,
            "The record with XML ID 'marketing_automation.mail_contact_temp' should not exist.",
        )

        # Now re-create record and check values again
        self.env["marketing.campaign"].sudo()._create_records_with_xml_ids(
            {"mailing.contact": [create_xmls]}
        )
        record = self.env.ref(
            "marketing_automation.mail_contact_temp", raise_if_not_found=False
        )
        self.assertTrue(record, "Record should exist after being re-created.")
        self.assertEqual(record.name, name, f"The value should be {name}")
        self.assertEqual(record.email, email, f"The value should be {email}")

    @users("user_marketing_automation")
    def test_duplicate_campaign(self):
        """Test duplicating a campaign: should not duplicate traces
        and consider mailings as already sent through duplicates"""
        original_campaign = self.campaign.with_user(self.env.user)

        # Add server activity to campaign
        server_action = (
            self.env["ir.actions.server"]
            .sudo()
            .create(
                {
                    "name": "Test Server Action",
                    "model_id": self.env["ir.model"]._get_id("res.partner"),
                    "state": "code",
                    "code": "pass",
                }
            )
        )
        self._create_activity(self.campaign, mailing=None, action=server_action)

        duplicated_campaign = original_campaign.copy()
        for campaign in original_campaign + duplicated_campaign:
            campaign.sync_participants()
            with self.mock_mail_gateway(mail_unlink_sent=False):
                campaign.execute_activities()
            for activity in campaign.marketing_activity_ids:
                with self.subTest(
                    msg=f'campaign.name="{campaign.name}"', activity=activity
                ):
                    self.assertMarketAutoTraces(
                        [
                            {
                                "status": "processed",
                                "records": self.test_contacts,
                                "trace_status": "sent",
                            }
                        ],
                        activity,
                    )

    @users("user_marketing_automation")
    def test_utm_source(self):
        """Test source name modification and uniqueness check"""
        # Setup
        campaign = self.campaign.with_user(self.env.user)
        utm_source_name = "utm_source_without_mailing"
        campaign.marketing_activity_ids.mass_mailing_id.name = utm_source_name
        self.assertEqual(
            campaign.marketing_activity_ids.mass_mailing_id.name,
            utm_source_name,
        )

        # Try to remove template from campaign's activity
        with self.assertRaises(UserError):
            campaign.marketing_activity_ids.mass_mailing_id.unlink()

        campaign.marketing_activity_ids.mass_mailing_id = False
        self.assertTrue(
            self.env["utm.source"].search([("name", "=", utm_source_name)]),
            "Test prerequisite: UTM source should still exists, even though it's not related to any campaigns",
        )

        # Create new campaign with an activity
        new_campaign = self.env["marketing.campaign"].create(
            {
                "domain": [("name", "like", "MATest")],
                "model_id": self.env["ir.model"]._get_id("mailing.contact"),
                "name": "New Test Campaign",
            }
        )
        self._create_activity_mail(
            new_campaign,
            user=self.user_marketing_automation,
            act_values={
                "trigger_type": "begin",
                "interval_number": 0,
                "interval_type": "hour",
            },
        )
        # Reassign the original UTM source name to the new campaign (attempting to trigger unique name constraint)
        new_campaign.marketing_activity_ids.mass_mailing_id.name = utm_source_name
