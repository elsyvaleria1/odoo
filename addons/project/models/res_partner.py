from typing import Self

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    project_ids = fields.One2many(
        comodel_name="project.project",
        inverse_name="partner_id",
        string="Projects",
        export_string_translation=False,
    )
    task_ids = fields.One2many(
        comodel_name="project.task",
        inverse_name="partner_id",
        string="Tasks",
        export_string_translation=False,
    )
    task_count = fields.Integer(
        string="# Tasks",
        export_string_translation=False,
        compute="_compute_task_count",
    )

    @api.constrains("company_id", "project_ids")
    def _check_same_company_as_projects(self) -> None:
        if self._get_partners_with_records_of_other_company("project.project"):
            raise UserError(
                self.env._(
                    "Partner company cannot be different from its assigned projects' company"
                )
            )

    @api.constrains("company_id", "task_ids")
    def _check_same_company_as_tasks(self) -> None:
        if self._get_partners_with_records_of_other_company("project.task"):
            raise UserError(
                self.env._(
                    "Partner company cannot be different from its assigned tasks' company"
                )
            )

    def _get_partners_with_records_of_other_company(self, model_name: str) -> Self:
        partners = self.filtered("company_id")
        if not partners:
            return partners
        mismatched = partners.browse(
            [
                partner.id
                for partner, company in self.env[model_name]._read_group(
                    [("partner_id", "in", partners.ids), ("company_id", "!=", False)],
                    ["partner_id", "company_id"],
                )
                if company != partner.company_id
            ]
        )
        _debug.logic(
            "partner_company_checked",
            model=model_name,
            partners=partners,
            mismatched=mismatched,
        )
        return mismatched

    @_debug.perf.timed
    def _compute_task_count(self) -> None:
        all_partners = self.with_context(active_test=False).search_fetch(
            [("id", "child_of", self.ids)],
            ["parent_id"],
        )
        task_data = self.env["project.task"]._read_group(
            domain=[("partner_id", "in", all_partners.ids)],
            groupby=["partner_id"],
            aggregates=["__count"],
        )
        self_ids = set(self._ids)

        self.task_count = 0
        for partner, count in task_data:
            while partner:
                if partner.id in self_ids:
                    partner.task_count += count
                partner = partner.parent_id

    def action_view_tasks(self) -> dict:
        self.check_singleton()
        action = {
            **self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "project.project_task_action_from_partner"
            ),
            "display_name": self.env._(
                "%(partner_name)s's Tasks", partner_name=self.name
            ),
            "context": {
                "default_partner_id": self.id,
            },
        }
        all_child = self.with_context(active_test=False).search(
            [("id", "child_of", self.ids)]
        )
        search_domain = [("partner_id", "in", (self | all_child).ids)]
        _debug.logic(
            "tasks_action_opened",
            partners=self,
            children=len(all_child),
            task_count=self.task_count,
            view="form" if self.task_count <= 1 else "list",
        )
        if self.task_count <= 1:
            task_id = self.env["project.task"].search(search_domain, limit=1)
            action["res_id"] = task_id.id
            action["views"] = [
                (view_id, view_type)
                for view_id, view_type in action["views"]
                if view_type == "form"
            ]
        else:
            action["domain"] = search_domain
        return action
