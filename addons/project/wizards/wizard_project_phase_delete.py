from typing import Any

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardProjectPhaseDelete(models.TransientModel):
    _name = "wizard.project.phase.delete"
    _description = "Project Phase Delete Wizard"

    phase_ids = fields.Many2many(
        comodel_name="project.phase",
        string="Phases To Delete",
        export_string_translation=False,
        context={"active_test": False},
        ondelete="cascade",
    )
    projects_count = fields.Integer(
        string="Number of Projects",
        export_string_translation=False,
        compute="_compute_projects_count",
    )
    phases_active = fields.Boolean(
        export_string_translation=False,
        compute="_compute_phases_active",
    )

    @api.depends("phase_ids")
    def _compute_projects_count(self) -> None:
        counts = dict(
            self.env["project.project"]
            .with_context(active_test=False)
            ._read_group(
                [("phase_id", "in", self.phase_ids.ids)],
                ["phase_id"],
                ["__count"],
            )
        )
        for wizard in self:
            wizard.projects_count = sum(
                counts.get(record, 0) for record in wizard.phase_ids
            )

    @api.depends("phase_ids")
    def _compute_phases_active(self) -> None:
        for wizard in self:
            wizard.phases_active = all(wizard.phase_ids.mapped("active"))

    def action_archive(self) -> dict[str, Any]:
        projects = (
            self.with_context(active_test=False)
            .env["project.project"]
            .search([("phase_id", "in", self.phase_ids.ids)])
        )
        _debug.lifecycle("phases_archived", phases=self.phase_ids, projects=projects)
        projects.write({"active": False})
        self.phase_ids.write({"active": False})
        return self._prepare_action_redirect()

    def action_unarchive_project(self) -> None:
        inactive_projects = (
            self.env["project.project"]
            .with_context(active_test=False)
            .search([("active", "=", False), ("phase_id", "in", self.phase_ids.ids)])
        )
        _debug.lifecycle("projects_unarchived", projects=inactive_projects)
        inactive_projects.action_unarchive()

    def action_unlink(self) -> dict[str, Any]:
        _debug.lifecycle("phases_unlinked", phases=self.phase_ids)
        self.phase_ids.unlink()
        return self._prepare_action_redirect()

    def _prepare_action_redirect(self) -> dict[str, Any]:
        action = (
            self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "project.project_phase_configure"
            )
            if self.env.context.get("stage_view")
            else self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "project.open_view_project_all_group_stage"
            )
        )

        context = action.get("context", "{}")
        context = context.replace("uid", str(self.env.uid))
        context = dict(
            self.env["ir.actions.actions"]._eval_action_context(context),
            active_test=True,
        )
        action["context"] = context
        action["target"] = "main"
        return action
