from odoo import models


class WizardReportConfigUpdateLayout(models.TransientModel):
    _inherit = "wizard.report.config.update.layout"

    def _get_render_information(self, styles):
        res = super()._get_render_information(styles)
        if (
            self.env.context.get("active_model", "") == "project.task"
            and self.env.context.get("active_id")
            and res["doc"].worksheet_template_id
        ):
            task = res["doc"]
            worksheet_map = {}
            x_model = task.worksheet_template_id.model_id.model
            worksheet_map[task.id] = self.env[x_model].search(
                [("x_project_task_id", "=", task.id)],
                limit=1,
                order="create_date DESC",
            )
            res["worksheet_map"] = worksheet_map
        return res
