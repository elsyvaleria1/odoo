from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict

if TYPE_CHECKING:
    from odoo.addons.approval.models.approval_approver import ApprovalApprover
    from odoo.addons.approval.models.res_users import ResUsers
    from odoo.addons.hr.models.hr_employee import HrEmployee


class ApprovalRequest(models.Model):
    _inherit = "approval.request"
    _access_anchors = frozendict(
        {
            "approver_delegate": models.Anchor(
                "approver_ids.delegate_id", kind="owner"
            ),
            "approver_user": models.Anchor("approver_ids.user_id", kind="owner"),
            "category_allowed_group_all_user": models.Anchor(
                "category_id.allowed_group_ids.all_user_ids", kind="owner"
            ),
            "category_allowed_user": models.Anchor(
                "category_id.allowed_user_ids", kind="owner"
            ),
            "owner": "request_owner_id",
        }
    )

    manager_approval = fields.Selection(related="category_id.manager_approval")
    requester_manager_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Requester's Manager",
        compute="_compute_requester_manager_user_id",
        help="The manager of the requester's employee in the request's company, when "
        "that manager has an active user other than the requester. A step reads it "
        "to ask the manager on requests that have no source document.",
    )

    def _compute_requester_manager_user_id(self) -> None:
        for request in self:
            request.requester_manager_user_id = request._get_owner_manager_user()

    def action_confirm(self) -> None:
        for request in self:
            request._check_manager_approval_constraints()

            if request.manager_approval == "optional":
                manager_user = request._get_owner_manager_user()

                if (
                    not manager_user
                    and len(request.approver_ids) < request.approval_minimum
                ):
                    raise UserError(
                        self.env._(
                            "This category expects your manager as an optional approver, "
                            "but you do not have a manager configured. You need to add at "
                            "least %(missing)d more approver(s) to meet the minimum of "
                            "%(minimum)d approvers.\n\n"
                            "Either:\n"
                            "• Ask your HR administrator to assign a manager to your profile, or\n"
                            "• Manually add %(missing)d more approver(s) to this request",
                            missing=request.approval_minimum
                            - len(request.approver_ids),
                            minimum=request.approval_minimum,
                        ),
                    )

        super().action_confirm()

    def _get_owner_employee(self) -> HrEmployee:
        self.check_singleton()
        return self.env["hr.employee"].search(
            [
                ("user_id", "=", self.request_owner_id.id),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )

    def _get_owner_manager_user(self) -> ResUsers:
        self.check_singleton()
        manager_user = self._get_owner_employee().parent_id.user_id
        if not manager_user or not manager_user.active:
            return self.env["res.users"]
        if manager_user == self.request_owner_id:
            return self.env["res.users"]
        return manager_user

    def _get_escalation_manager(self, approver: ApprovalApprover) -> ResUsers:
        employee = (
            self.env["hr.employee"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("user_id", "=", approver.user_id.id),
                    ("company_id", "=", self.company_id.id),
                ],
                limit=1,
            )
        )
        manager = employee.parent_id
        seen: set[int] = set()
        while manager and manager.id not in seen:
            seen.add(manager.id)
            manager_user = manager.user_id
            if (
                manager_user
                and manager_user.active
                and manager_user != approver.user_id
            ):
                return manager_user
            manager = manager.parent_id
        return super()._get_escalation_manager(approver)

    @api.model
    def _supplies_manager_chain(self) -> bool:
        return True

    def _get_manager_chain(self, user: ResUsers) -> ResUsers:
        self.check_singleton()
        employee = (
            self.env["hr.employee"]
            .with_privilege(
                "approval.privilege_walk_authority",
                reason="a step walks the requester's managers",
            )
            .with_context(active_test=False)
            .search(
                [("user_id", "=", user.id), ("company_id", "=", self.company_id.id)],
                limit=1,
            )
        )
        chain = self.env["res.users"]
        manager = employee.parent_id
        seen: set[int] = set()
        while manager and manager.id not in seen:
            seen.add(manager.id)
            if manager.user_id and manager.user_id != user:
                chain |= manager.user_id
            manager = manager.parent_id
        return chain

    def _check_manager_approval_constraints(self) -> None:
        for request in self:
            if request.manager_approval != "required":
                continue
            employee = request._get_owner_employee()

            if not employee:
                raise UserError(
                    self.env._(
                        "This request requires manager approval, but you do not have "
                        "an employee profile in company '%(company)s'. Please contact "
                        "your HR administrator to create your employee record.",
                        company=request.company_id.name,
                    ),
                )

            if not employee.parent_id:
                raise UserError(
                    self.env._(
                        "This request requires manager approval, but no manager is "
                        "assigned to your employee profile. Please contact your HR "
                        "administrator to assign a manager to your profile."
                    ),
                )

            manager_user = employee.parent_id.user_id
            if not manager_user or not manager_user.active:
                raise UserError(
                    self.env._(
                        "This request requires manager approval, but your manager "
                        "'%(manager)s' does not have an active user account. Please "
                        "contact your HR administrator.",
                        manager=employee.parent_id.name,
                    ),
                )

            if manager_user == request.request_owner_id:
                raise UserError(
                    self.env._(
                        "This request requires manager approval, but you are "
                        "recorded as your own manager. Please contact your HR "
                        "administrator.",
                    ),
                )
