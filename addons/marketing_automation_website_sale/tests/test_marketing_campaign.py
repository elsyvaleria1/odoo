from odoo.tests import tagged

from odoo.addons.marketing_automation.tests.common import MarketingAutomationCommon


@tagged("-at_install", "post_install")
class TestCampaignTemplate(MarketingAutomationCommon):
    def test_anniversary_template(self):
        anniversary = self.campaign._create_campaign_from_template_anniversary()
        self.assertTrue(anniversary)
