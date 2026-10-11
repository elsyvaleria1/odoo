from odoo.exceptions import UserError
from odoo.tests.common import tagged, users

from odoo.addons.utm.tests.common import TestUTMCommon


@tagged("post_install", "-at_install", "utm", "utm_consistency")
class TestUTMConsistency(TestUTMCommon):
    @users("__system__")
    def test_utm_consistency(self):

        with self.assertRaises(UserError):
            self.env.ref("utm.utm_medium_email").unlink()
