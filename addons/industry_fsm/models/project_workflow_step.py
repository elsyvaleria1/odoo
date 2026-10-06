from odoo import models


class ProjectWorkflowStep(models.Model):
    _inherit = "project.workflow.step"

    def _default_project_ids(self):
        """Include FSM projects when creating steps in FSM mode."""
        default_project_ids = super()._default_project_ids()
        if self.env.context.get("fsm_mode") and not default_project_ids:
            default_project = self.env["project.project"].search(
                [("is_fsm", "=", True)]
            )
            default_project_ids = default_project.ids
        return default_project_ids
