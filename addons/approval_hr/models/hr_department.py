from typing import Any

from odoo import Command, api, fields, models
from odoo.fields import Domain


class HrDepartment(models.Model):
    _inherit = "hr.department"

    approval_category_ids = fields.Many2many(
        comodel_name="approval.category",
        relation="approval_category_department_rel",
        column1="department_id",
        column2="category_id",
        string="Approval Categories",
        help="Approval categories whose scope includes this department.",
    )
    approval_category_count = fields.Integer(
        compute="_compute_approval_category_count",
        help="Number of approval categories tagged with this department.",
    )

    @api.depends(
        "approval_category_ids.active",
        "approval_category_ids.allowed_user_ids",
        "approval_category_ids.allowed_group_ids",
    )
    def _compute_approval_category_count(self) -> None:
        data = self.env["approval.category"]._read_group(
            Domain.AND(
                [
                    [("department_ids", "in", self.ids), ("active", "=", True)],
                    self._approval_visibility_domain(),
                ],
            ),
            ["department_ids"],
            ["__count"],
        )
        mapped = {dept.id: count for dept, count in data}
        for department in self:
            department.approval_category_count = mapped.get(department.id, 0)

    def view_approval_categories(self) -> dict[str, Any]:
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "approval.action_approval_category_dashboard",
        )
        action["name"] = self.env._("%(dept)s — Approval Categories", dept=self.name)
        action["domain"] = Domain.AND(
            [
                [("department_ids", "in", self.ids)],
                self._approval_visibility_domain(),
            ],
        )
        action["context"] = {"default_department_ids": [Command.link(self.id)]}
        return action

    def _approval_visibility_domain(self) -> Domain:
        return Domain.OR(
            [
                [
                    ("allowed_user_ids", "=", False),
                    ("allowed_group_ids", "=", False),
                ],
                [("allowed_user_ids", "=", self.env.uid)],
                [("allowed_group_ids.all_user_ids", "=", self.env.uid)],
            ],
        )
