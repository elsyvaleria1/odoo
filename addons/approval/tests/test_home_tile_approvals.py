from odoo.tests import tagged

from .common import ApprovalCommon


@tagged("post_install", "-at_install")
class TestHomeTileApprovals(ApprovalCommon):
    def _approvals(self, user):
        return (
            self.env["home.tile"]
            .with_user(user)
            .get_tiles([{"id": "approvals_1", "type": "approvals"}])["approvals_1"][
                "data"
            ]
        )

    def test_the_approvals_tile_lists_what_awaits_my_decision(self):
        category = self._make_category(approvers=[self.approver_1])
        request = self._prepare_request(category)
        mine = self._approvals(self.approver_1)
        self.assertEqual(mine["count"], 1)
        self.assertEqual(mine["requests"][0]["id"], request.id)
        self.assertEqual(mine["requests"][0]["owner"], self.owner_user.display_name)
        self.assertEqual(self._approvals(self.approver_2)["count"], 0)

    def test_the_approvals_tile_keeps_its_statement_count(self):
        request = [{"id": "approvals_1", "type": "approvals"}]
        self.env["home.tile"].with_user(self.approver_1).get_tiles(request)
        self.env.invalidate_all()
        with self.assertQueryCount(12):
            self.env["home.tile"].with_user(self.approver_1).get_tiles(request)
