from typing import Literal, Self

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.fields import Command

from odoo.addons.approval.models import approval_trace as trace
from odoo.addons.approval.models.approval_category import CATEGORY_SELECTION


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    approval_type = fields.Selection(
        selection_add=[
            ("hr", "HR"),
        ],
        ondelete={
            "hr": "cascade",
        },
    )
    manager_approval = fields.Selection(
        selection=CATEGORY_SELECTION,
        default="no",
        required=True,
        tracking=True,
        help="""How the requester's manager participates as an approver:

        • None: the manager is not added
        • Optional: the manager is added as an optional approver
        • Required: the manager must approve the request

        A step that takes its approvers from a security group never asks the
        manager; the manager joins the steps that count approvers added to the
        request, or waits in a step of their own when required.""",
    )
    department_ids = fields.Many2many(
        comodel_name="hr.department",
        relation="approval_category_department_rel",
        column1="category_id",
        column2="department_id",
        string="Departments",
        help="Departments where this category appears on the Approvals dashboard.\n"
        "Leave empty to hide it from the dashboard (still reachable via "
        "Configuration > Approval Categories).",
    )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        categories = super().create(vals_list)
        categories.filtered("step_ids")._sync_requester_manager_steps()
        return categories

    def write(self, vals: ValuesType) -> Literal[True]:
        result = super().write(vals)
        if "manager_approval" in vals:
            self.filtered("step_ids")._sync_requester_manager_steps()
        return result

    def _adds_requester_manager(self) -> bool:
        self.check_singleton()
        return self.manager_approval != "no"

    def _get_manager_step_source(self) -> ValuesType:
        return {
            "subject_model_id": self.env["ir.model"]._get("approval.request").id,
            "subject_user_path": "requester_manager_user_id",
        }

    def _prepare_manager_order_vals(self) -> ValuesType:
        return {
            "subject_user_sequence": self.env[
                "approval.request"
            ]._get_sequence_manager(),
            "subject_user_required": self.manager_approval == "required",
        }

    def _sync_requester_manager_steps(self) -> None:
        source = self._get_manager_step_source()
        for category in self:
            asking = category.step_ids.filtered(
                lambda step: (
                    step.subject_model_id.id == source["subject_model_id"]
                    and step.subject_user_path == source["subject_user_path"]
                )
            )
            pooled = asking.filtered(
                lambda step: step.member_ids or step.counts_added_approvers
            )
            pooled.write(
                {
                    "subject_model_id": False,
                    "subject_user_path": False,
                    "subject_user_required": False,
                }
            )
            trace.STEPS.event(
                "requester_manager_cleared",
                category=category.id,
                pools_cleared=pooled.ids,
                steps_removed=(asking - pooled).ids,
            )
            (asking - pooled).unlink()
            if not category._adds_requester_manager():
                continue
            pools = category.step_ids.filtered(
                lambda step: (
                    step.counts_added_approvers
                    and not step.group_id
                    and not step.subject_user_path
                )
            )
            pools.write(source)
            ordered = pools.filtered("in_order")
            ordered.write(category._prepare_manager_order_vals())
            separate_step = category.manager_approval == "required" and bool(
                not pools or pools - ordered
            )
            if separate_step:
                category.step_ids = [
                    Command.create(
                        {
                            "name": self.env._("Requester's manager"),
                            "sequence": min(
                                category.step_ids.mapped("sequence"), default=10
                            ),
                            "minimum": 1,
                            **source,
                        }
                    )
                ]
            trace.STEPS.event(
                "requester_manager_synced",
                category=category.id,
                manager_approval=category.manager_approval,
                pools=pools.ids,
                ordered=ordered.ids,
                separate_step=separate_step,
            )
