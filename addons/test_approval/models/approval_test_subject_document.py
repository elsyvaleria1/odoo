from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.api import ValuesType

if TYPE_CHECKING:
    from odoo.addons.approval.models.approval_approver import ApprovalApprover
    from odoo.addons.approval.models.approval_category import ApprovalCategory
    from odoo.addons.approval.models.approval_category_step import (
        ApprovalCategoryStep,
    )
    from odoo.addons.approval.models.approval_request import ApprovalRequest
    from odoo.addons.mail.models.mail_activity_type import MailActivityType


class ApprovalTestSubjectDocument(models.Model):
    _name = "approval.test.subject.document"
    _description = "Test Record Holding One Approval Request per Subject"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity", "mixin.approval.subjects"]

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    test_category_id = fields.Many2one(comodel_name="approval.category")
    outcomes = fields.Char(
        default="",
        help="Each notification this record received, in order, as subject:state;",
    )
    blocked_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="approval_test_subject_document_blocked_user_rel",
        column1="document_id",
        column2="user_id",
        help="Users this record's own policy would refuse, kept off its steps",
    )
    asking_activity_type_id = fields.Many2one(
        comodel_name="mail.activity.type",
        help="When set, the activity type this record asks every approver with",
    )

    def _get_approval_subject_category(self, subject_key: str) -> ApprovalCategory:
        return self.test_category_id

    def _on_approval_subject_state_changed(
        self, request: ApprovalRequest, new_state: str
    ) -> None:
        self.sudo().outcomes = f"{self.outcomes}{request.subject_key}:{new_state};"

    def _on_approval_subject_progress(self, request: ApprovalRequest) -> None:
        self.sudo().outcomes = f"{self.outcomes}{request.subject_key}:progress;"

    def _filter_approval_step_user_ids(
        self, step: ApprovalCategoryStep, user_ids: set[int]
    ) -> set[int]:
        return user_ids - set(self.blocked_user_ids.ids)

    def _prepare_approval_activity_vals(self, approver: ApprovalApprover) -> ValuesType:
        return {"summary": f"Asked about {approver.request_id.subject_key}"}

    def _get_approval_activity_type(
        self, approver: ApprovalApprover, step_type: MailActivityType
    ) -> MailActivityType:
        return self.asking_activity_type_id or step_type
