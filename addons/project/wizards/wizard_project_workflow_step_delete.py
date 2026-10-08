from typing import Any

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardProjectWorkflowStepDelete(models.TransientModel):
    _name = "wizard.project.workflow.step.delete"
    _description = "Workflow Step Delete Wizard"

    project_ids = fields.Many2many(
        comodel_name="project.project",
        string="Projects",
        export_string_translation=False,
        domain="['|', ('active', '=', False), ('active', '=', True)]",
        ondelete="cascade",
    )
    step_ids = fields.Many2many(
        comodel_name="project.workflow.step",
        string="Steps To Delete",
        export_string_translation=False,
        ondelete="cascade",
    )
    tasks_count = fields.Integer(
        string="Number of Tasks",
        export_string_translation=False,
        compute="_compute_tasks_count",
    )
    steps_active = fields.Boolean(
        export_string_translation=False,
        compute="_compute_steps_active",
    )

    @api.depends("step_ids")
    def _compute_tasks_count(self) -> None:
        for wizard in self:
            wizard.tasks_count = wizard.step_ids._get_member_count()

    @api.depends("step_ids")
    def _compute_steps_active(self) -> None:
        for wizard in self:
            wizard.steps_active = all(wizard.step_ids.mapped("active"))

    def action_archive(self) -> dict[str, Any]:
        _debug.logic(
            "steps_archive_requested",
            steps=self.step_ids,
            projects=len(self.project_ids),
            action="confirm" if len(self.project_ids) <= 1 else "ask",
        )
        if len(self.project_ids) <= 1:
            return self.action_confirm()

        return {
            "name": self.env._("Confirmation"),
            "view_mode": "form",
            "res_model": "wizard.project.workflow.step.delete",
            "views": [
                (
                    self.env.ref(
                        "project.view_project_workflow_step_delete_confirmation_wizard"
                    ).id,
                    "form",
                )
            ],
            "type": "ir.actions.act_window",
            "res_id": self.id,
            "target": "new",
            "context": self.env.context,
        }

    def action_confirm(self) -> dict[str, Any]:
        _debug.lifecycle("steps_archived", steps=self.step_ids)
        self.step_ids.action_archive()
        return self._prepare_action_close()

    def action_unlink(self) -> dict[str, Any]:
        _debug.lifecycle("steps_unlinked", steps=self.step_ids)
        self.step_ids.unlink()
        return self._prepare_action_close()

    def _prepare_action_close(self) -> dict[str, Any]:
        return {
            "type": "ir.actions.act_window_close",
            "infos": {
                "success": True,
            },
        }
