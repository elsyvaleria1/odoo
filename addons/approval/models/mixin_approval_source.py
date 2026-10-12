from typing import TYPE_CHECKING

from odoo import models
from odoo.api import ValuesType

from . import approval_trace as trace

if TYPE_CHECKING:
    from .approval_approver import ApprovalApprover
    from .approval_category_step import ApprovalCategoryStep
    from odoo.addons.mail.models.mail_activity_type import MailActivityType


class MixinApprovalSource(models.AbstractModel):
    _name = "mixin.approval.source"
    _description = "Record an Approval Request Is Raised For"

    def _filter_approval_step_user_ids(
        self, step: ApprovalCategoryStep, user_ids: set[int]
    ) -> set[int]:
        trace.STEPS.event(
            "document_policy_default",
            record=self,
            step=step.id,
            users=len(user_ids),
            narrowed=False,
        )
        return user_ids

    def _prepare_approval_activity_vals(self, approver: ApprovalApprover) -> ValuesType:
        return {}

    def _get_approval_activity_type(
        self, approver: ApprovalApprover, step_type: MailActivityType
    ) -> MailActivityType:
        trace.ACTIVITY.event(
            "activity_type_default",
            record=self,
            approver=approver.id,
            step_type=step_type.id if step_type else None,
        )
        return step_type
