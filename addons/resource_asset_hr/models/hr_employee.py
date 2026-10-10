from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    asset_ids = fields.Many2many(
        comodel_name="resource.resource",
        string="Assets Held",
        compute="_compute_asset_ids",
        groups="hr.group_hr_user",
    )
    asset_count = fields.Integer(
        compute="_compute_asset_ids",
        groups="hr.group_hr_user",
    )

    def _get_custody_assignments(self):
        return (
            self.env["resource.assignment"]
            .sudo()
            .search(
                [
                    ("assignee_id", "in", self.resource_id.ids),
                    ("state", "in", ("planned", "active")),
                ]
            )
        )

    def _compute_asset_ids(self) -> None:
        assignments = self._get_custody_assignments()
        assets = self.env["resource.resource"].search(
            [("id", "in", assignments.resource_id.ids), ("kind_id", "!=", False)]
        )
        active_by_assignee = assignments.filtered(
            lambda assignment: assignment.state == "active"
        ).grouped("assignee_id")
        for employee in self:
            held = active_by_assignee.get(
                employee.resource_id, assignments.browse()
            ).resource_id
            employee.asset_ids = assets & held
            employee.asset_count = len(employee.asset_ids)

    def action_view_assets(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "resource.action_resource_asset"
        )
        action["domain"] = [("id", "in", self.asset_ids.ids)]
        return action
