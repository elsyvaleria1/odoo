from odoo.exceptions import UserError
from odoo.tests.common import tagged, users

from odoo.addons.mass_mailing.tests.common import MassMailCommon
from odoo.addons.utm.tests.common import TestUTMCommon


@tagged("post_install", "-at_install", "utm_consistency")
class TestUTMConsistencyMassMailing(TestUTMCommon, MassMailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._create_mailing_list()

    @users("__system__")
    def test_utm_consistency(self):
        mailing = self.env["mailing.mailing"].create(
            {
                "subject": "Newsletter",
                "mailing_model_id": self.env["ir.model"]._get("res.partner").id,
            }
        )
        utm_source = mailing.source_id

        with self.assertRaises(UserError):
            utm_source.unlink()

        utm_medium = mailing.medium_id

        with self.assertRaises(UserError):
            utm_medium.unlink()

    @users("user_marketing")
    def test_utm_consistency_mass_mailing_user(self):
        self.utm_campaign.unlink()
        self.utm_medium.unlink()
        self.utm_source.unlink()
