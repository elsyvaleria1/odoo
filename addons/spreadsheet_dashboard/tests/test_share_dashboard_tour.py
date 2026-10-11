from odoo.tests import tagged
from odoo.tests.common import HttpCase

from .common import DashboardTestCommon


@tagged("post_install", "-at_install")
class TestDashboardShareTour(DashboardTestCommon, HttpCase):
    def test_open_public_dashboard(self):
        dashboard = self.create_dashboard()
        share = self.share_dashboard(dashboard)
        self.browser_js(
            "/dashboard/share/%s/%s" % (share.id, share.access_token),
            "console.log('test successful');",
            ready="odoo.isReady",
        )
