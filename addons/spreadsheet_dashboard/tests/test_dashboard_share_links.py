from datetime import timedelta

from odoo import fields
from odoo.tests.common import HttpCase, tagged
from odoo.tools import mute_logger

from .common import DashboardTestCommon
from odoo.addons.base.models.access_link import hash_token


@tagged("post_install", "-at_install", "access_link")
class TestDashboardShareLinks(DashboardTestCommon, HttpCase):
    def _link(self, share):
        return (
            self.env["access.link"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "spreadsheet.dashboard.share"),
                    ("res_id", "=", share.id),
                ]
            )
        )

    def test_a_share_is_a_link_for_a_manual_shares_time(self):
        share = self.share_dashboard(self.create_dashboard())
        link = self._link(share)
        self.assertEqual((len(link), link.role, link.cause), (1, "view", "share"))
        self.assertAlmostEqual(
            link.date_to,
            fields.Datetime.now() + timedelta(days=30),
            delta=timedelta(minutes=5),
        )
        self.assertEqual(link.token_hash, hash_token(share.access_token))
        self.assertIn(share.access_token, share.full_url)

    @mute_logger("odoo.http")
    def test_a_token_opens_its_own_share_only(self):
        dashboard = self.create_dashboard()
        share, other = self.share_dashboard(dashboard), self.share_dashboard(dashboard)
        url = f"/dashboard/share/{other.id}/{share.access_token}"
        self.assertEqual(self.url_open(url).status_code, 403)
        self._link(share).sudo().date_to = fields.Datetime.now() - timedelta(seconds=1)
        url = f"/dashboard/share/{share.id}/{share.access_token}"
        self.assertEqual(self.url_open(url).status_code, 403, "an expired link")
