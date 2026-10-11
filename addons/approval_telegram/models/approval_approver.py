from odoo import models


class ApprovalApprover(models.Model):
    _inherit = "approval.approver"

    def _telegram_notify_enabled(self) -> bool:
        self.check_singleton()
        return any(
            self.step_ids.member_ids.filtered(
                lambda member: member.user_id == self.user_id
            ).mapped("notify_telegram")
        )

    def _create_activity(self):
        result = super()._create_activity()
        notifier = self.env["telegram.approval.notifier"]
        if not notifier._feature_active():
            return result
        for approver in self:
            notifier._notify_approver(approver)
        return result
