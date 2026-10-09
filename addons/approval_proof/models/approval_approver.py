from typing import Any

from odoo import api, models
from odoo.exceptions import ValidationError


class ApprovalApprover(models.Model):
    _inherit = "approval.approver"

    def _may_delegate_to(self, delegate) -> bool:
        return (
            super()._may_delegate_to(delegate)
            and self.request_id.category_id.allow_delegation
        )

    @api.constrains("delegate_id")
    def _check_delegation_allowed(self) -> None:
        for approver in self.filtered("delegate_id"):
            category = approver.request_id.category_id
            if not category.allow_delegation:
                raise ValidationError(
                    self.env._(
                        "%(category)s is decided by the approvers themselves: "
                        "%(user)s cannot hand their approval to someone else.",
                        category=category.display_name,
                        user=approver.user_id.name,
                    )
                )

    def action_issue_decision_proof(self, decision: str) -> dict[str, Any] | None:
        self.check_singleton()
        return self.request_id.action_issue_decision_proof(decision)

    def action_approve_with_proof(self, proof: dict[str, Any]) -> dict[str, Any] | None:
        self.check_singleton()
        return self.with_context(approval_proof=proof).action_approve()
