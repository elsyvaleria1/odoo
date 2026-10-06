from typing import Any

from odoo import models


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    def action_approve(
        self,
        approver: models.BaseModel | None = None,
        steps: models.BaseModel | None = None,
    ) -> dict[str, Any] | None:
        super().action_approve(approver, steps)
        if self.res_model != "sale.order" or not self.res_id:
            return None
        order = self.env["sale.order"].browse(self.res_id).exists()
        if not order or order.state != "draft":
            return None
        return order._get_credit_authorization_action()
