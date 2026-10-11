from odoo.exceptions import UserError
from odoo.tests.common import tagged, users

from odoo.addons.test_marketing_automation.tests.common import TestMACommon
from odoo.addons.utm.tests.common import TestUTMCommon


@tagged("post_install", "-at_install", "utm_consistency")
class TestUTMConsistencyMassMailing(TestUTMCommon, TestMACommon):
    @users("__system__")
    def test_utm_consistency(self):
        marketing_campaign = self.env["marketing.campaign"].create(
            {
                "name": "Test Campaign",
                "model_id": self.env["ir.model"]._get("marketing.test.sms").id,
            }
        )
        utm_campaign = marketing_campaign.utm_campaign_id

        with self.assertRaises(UserError):
            utm_campaign.unlink()

        marketing_activity = self._create_activity_mail(marketing_campaign)
        utm_source = marketing_activity.source_id

        with self.assertRaises(UserError):
            utm_source.unlink()
