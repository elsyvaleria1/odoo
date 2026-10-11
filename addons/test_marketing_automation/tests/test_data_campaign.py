from odoo.exceptions import AccessError
from odoo.tests import tagged, users
from odoo.tools import mute_logger

from odoo.addons.test_marketing_automation.tests.common import TestMACommon


@tagged("marketing_automation")
class TestDataCampaign(TestMACommon):
    @users("user_marketing_automation")
    @mute_logger("odoo.addons.base.ir.ir_model", "odoo.models")
    def test_get_campaign_from_template(self):
        self.assertTrue(
            bool(
                self.env[
                    "marketing.campaign"
                ].get_action_marketing_campaign_from_template("double_opt_in")["res_id"]
            )
        )
        self.assertTrue(
            bool(
                self.env[
                    "marketing.campaign"
                ].get_action_marketing_campaign_from_template("welcome")["res_id"]
            )
        )
        self.assertTrue(
            bool(
                self.env[
                    "marketing.campaign"
                ].get_action_marketing_campaign_from_template("hot_contacts")["res_id"]
            )
        )

        campaign_action = self.env[
            "marketing.campaign"
        ].get_action_marketing_campaign_from_template("commercial_prospection")
        self.assertTrue(bool(campaign_action["res_id"]))
        campaign = self.env["marketing.campaign"].browse(campaign_action["res_id"])
        self.assertTrue(len(campaign.marketing_activity_ids) == 3)
        for activity in campaign.marketing_activity_ids:
            if activity.activity_type == "email":
                self.assertTrue(bool(activity.mass_mailing_id))
            elif activity.activity_type == "action":
                self.assertTrue(bool(activity.server_action_id))

    @users("employee")
    @mute_logger("odoo.addons.base.ir.ir_model", "odoo.models")
    def test_get_campaign_from_template_as_employee(self):
        with self.assertRaises(AccessError):
            self.env["marketing.campaign"].get_action_marketing_campaign_from_template(
                "commercial_prospection"
            )
