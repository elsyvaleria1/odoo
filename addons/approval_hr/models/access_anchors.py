from odoo import models
from odoo.tools import frozendict


class ApprovalApprover(models.Model):
    _inherit = "approval.approver"

    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
            "delegate": models.Anchor("delegate_id", kind="owner"),
            "owner": "user_id",
            "request_approver_delegate": models.Anchor(
                "request_id.approver_ids.delegate_id", kind="owner"
            ),
            "request_approver_user": models.Anchor(
                "request_id.approver_ids.user_id", kind="owner"
            ),
            "request_category_allowed_group_all_user": models.Anchor(
                "request_id.category_id.allowed_group_ids.all_user_ids", kind="owner"
            ),
            "request_category_allowed_user": models.Anchor(
                "request_id.category_id.allowed_user_ids", kind="owner"
            ),
            "request_request_owner": models.Anchor(
                "request_id.request_owner_id", kind="owner"
            ),
        }
    )
