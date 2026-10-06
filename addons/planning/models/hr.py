import logging
from datetime import datetime, time, timedelta

from odoo import api, fields, models
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    default_planning_role_id = fields.Many2one(
        related="resource_id.default_role_id",
        readonly=False,
        groups="hr.group_hr_user",
        help="Role that will be selected by default when creating a shift for this employee.\n"
        "This role will also have precedence over the other roles of the employee when planning orders.",
    )
    planning_role_ids = fields.Many2many(
        related="resource_id.role_ids",
        readonly=False,
        groups="hr.group_hr_user",
        help="Roles that the employee can fill in. When creating a shift for this employee, only the shift templates for these roles will be displayed.\n"
        "Similarly, only the open shifts available for these roles will be sent to the employee when the schedule is published.\n"
        "Additionally, the employee will only be assigned orders for these roles (with the default planning role having precedence over the other ones).\n"
        "Leave empty for the employee to be assigned shifts regardless of the role.",
    )
    employee_token = fields.Char(
        related="resource_id.planning_token",
        string="Security Token",
        export_string_translation=False,
        groups="hr.group_hr_user",
    )
    has_slots = fields.Boolean(compute="_compute_has_slots")

    def action_reset_planning_token(self):
        return self.resource_id.action_reset_planning_token()

    @api.depends("job_title")
    @api.depends_context("show_job_title")
    def _compute_display_name(self):
        if not self.env.context.get("show_job_title"):
            return super()._compute_display_name()
        for employee in self:
            employee.display_name = (
                f"{employee.name} ({employee.sudo().job_title})"
                if employee.sudo().job_title
                else employee.name
            )
        return None

    @api.onchange("default_planning_role_id")
    def _onchange_default_planning_role_id(self) -> None:
        self.planning_role_ids |= self.default_planning_role_id

    @api.onchange("planning_role_ids")
    def _onchange_planning_role_ids(self) -> None:
        if self.default_planning_role_id.id not in self.planning_role_ids.ids:
            self.default_planning_role_id = self.planning_role_ids[:1]

    def action_archive(self):
        res = super().action_archive()
        departure_date = datetime.combine(
            fields.Date.context_today(self) + timedelta(days=1), time.min
        )
        planning_slots = (
            self.env["planning.slot"]
            .sudo()
            .search(
                [
                    ("resource_id", "in", self.resource_id.ids),
                    ("end_datetime", ">=", departure_date),
                ]
            )
        )
        planning_slots._manage_archived_resources(departure_date)
        return res

    def _compute_has_slots(self) -> None:
        result = set()
        if self.ids:
            result.update(
                id_
                for [id_] in self.env.execute_query(
                    SQL(
                        """ SELECT id
                      FROM hr_employee e
                     WHERE id = ANY(%s)
                       AND EXISTS(SELECT 1 FROM planning_slot WHERE employee_id = e.id LIMIT 1) """,
                        list(self.ids),
                    )
                )
            )

        for employee in self:
            employee.has_slots = employee._origin.id in result

    def action_view_planning(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "planning.planning_action_schedule_by_resource"
        )
        action.update(
            {
                "name": self.env._("View Planning"),
                "domain": [("resource_id", "in", self.resource_id.ids)],
                "context": {
                    "search_default_group_by_resource": True,
                    "filter_resource_ids": self.resource_id.ids,
                    "hide_open_shift": True,
                    "default_resource_id": self.resource_id.id
                    if len(self) == 1
                    else False,
                },
            }
        )
        return action
