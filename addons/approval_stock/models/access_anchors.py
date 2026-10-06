from odoo import models
from odoo.tools import frozendict


class ApprovalApprover(models.Model):
    _inherit = "approval.approver"

    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )
