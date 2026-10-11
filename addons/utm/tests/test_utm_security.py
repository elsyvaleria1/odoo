from odoo.exceptions import AccessError
from odoo.tests.common import tagged, users

from odoo.addons.utm.tests.common import TestUTMCommon


@tagged("post_install", "-at_install", "security", "utm")
class TestUTMSecurity(TestUTMCommon):
    @users("__system__")
    def test_utm_security_admin(self):
        UtmCampaign = self.env["utm.campaign"]
        UtmMedium = self.env["utm.medium"]
        UtmSource = self.env["utm.source"]

        test_utm_campaign = UtmCampaign.create({"name": "Campaign ACLs"})
        test_utm_medium = UtmMedium.create({"name": "Medium ACLs"})
        test_utm_source = UtmSource.create({"name": "Source ACLs"})

        self.assertEqual(
            UtmCampaign.search([("id", "=", test_utm_campaign.id)]), test_utm_campaign
        )
        self.assertEqual(
            UtmMedium.search([("id", "=", test_utm_medium.id)]), test_utm_medium
        )
        self.assertEqual(
            UtmSource.search([("id", "=", test_utm_source.id)]), test_utm_source
        )

        test_utm_campaign.write({"name": "Campaign EDITED"})
        test_utm_medium.write({"name": "Medium EDITED"})
        test_utm_source.write({"name": "Source EDITED"})

        test_utm_campaign.unlink()
        test_utm_medium.unlink()
        test_utm_source.unlink()

    @users("user_employee_utm")
    def test_utm_security_employee(self):
        UtmCampaign = self.env["utm.campaign"]
        UtmMedium = self.env["utm.medium"]
        UtmSource = self.env["utm.source"]

        test_utm_campaign = UtmCampaign.create({"name": "Campaign ACLs"})
        test_utm_medium = UtmMedium.create({"name": "Medium ACLs"})
        test_utm_source = UtmSource.create({"name": "Source ACLs"})

        self.assertEqual(
            UtmCampaign.search([("id", "=", test_utm_campaign.id)]), test_utm_campaign
        )
        self.assertEqual(
            UtmMedium.search([("id", "=", test_utm_medium.id)]), test_utm_medium
        )
        self.assertEqual(
            UtmSource.search([("id", "=", test_utm_source.id)]), test_utm_source
        )

        test_utm_campaign.write({"name": "Campaign EDITED"})
        test_utm_medium.write({"name": "Medium EDITED"})
        test_utm_source.write({"name": "Source EDITED"})

        with self.assertRaises(AccessError):
            test_utm_campaign.unlink()
        with self.assertRaises(AccessError):
            test_utm_medium.unlink()
        with self.assertRaises(AccessError):
            test_utm_source.unlink()
