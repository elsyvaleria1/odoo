from typing import Any

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

    def _get_ask_context(self) -> dict[str, Any]:
        context = super()._get_ask_context()
        notifier = self.env["telegram.approval.notifier"]
        if not notifier._feature_active():
            return context
        pushed = self.filtered(notifier._get_push_chat)
        if not pushed:
            return context
        skipped = set(self.env.context.get("mail_telegram_skip_partner_ids") or ())
        skipped |= set(context.get("mail_telegram_skip_partner_ids") or ())
        skipped |= {row._get_effective_approver().partner_id.id for row in pushed}
        return {**context, "mail_telegram_skip_partner_ids": sorted(skipped)}

    def _notify_asked(self) -> None:
        super()._notify_asked()
        if self.env.context.get("approval_telegram_hold_push"):
            return
        notifier = self.env["telegram.approval.notifier"]
        if not notifier._feature_active():
            return
        for approver in self:
            notifier._notify_approver(approver)
