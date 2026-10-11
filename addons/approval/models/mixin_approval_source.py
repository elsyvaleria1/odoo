from odoo import models
from odoo.api import ValuesType

from . import approval_trace as trace


class MixinApprovalSource(models.AbstractModel):
    _name = "mixin.approval.source"
    _description = "Record an Approval Request Is Raised For"

    def _filter_approval_step_user_ids(self, step, user_ids: set[int]) -> set[int]:
        trace.STEPS.event(
            "document_policy_default",
            record=self,
            step=step.id,
            users=len(user_ids),
            narrowed=False,
        )
        return user_ids

    def _prepare_approval_activity_vals(self, approver) -> ValuesType:
        return {}

    def _get_approval_activity_type(self, approver, step_type):
        trace.ACTIVITY.event(
            "activity_type_default",
            record=self,
            approver=approver.id,
            step_type=step_type.id if step_type else None,
        )
        return step_type
