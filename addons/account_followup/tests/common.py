from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account_followup.models.followup_request import FollowupRequest


class TestAccountFollowupCommon(AccountTestInvoicingCommon):
    def followup_request(self, partner, **values):
        return FollowupRequest.prepare(partner, **values).with_channel(
            "snailmail", False
        )

    def assertPartnerFollowup(self, partner, status, line):
        partner.invalidate_recordset(["followup_status", "followup_line_id"])
        res = partner._query_followup_data()
        self.assertEqual(res.get(partner.id, {}).get("followup_status"), status)
        self.assertEqual(
            res.get(partner.id, {}).get("followup_line_id"), line.id if line else None
        )
        self.assertEqual(partner.followup_status, status or "no_action_needed")
        self.assertEqual(
            partner.followup_line_id.id if partner.followup_line_id else None,
            line.id if line else None,
        )
