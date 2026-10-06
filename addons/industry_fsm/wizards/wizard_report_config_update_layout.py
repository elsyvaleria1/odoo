from odoo import models


class WizardReportConfigUpdateLayout(models.TransientModel):
    _inherit = "wizard.report.config.update.layout"

    def _get_preview_template(self):
        if self.env.context.get(
            "active_model"
        ) == "project.task" and self.env.context.get("active_id"):
            return "industry_fsm.worksheet_custom_preview"
        return super()._get_preview_template()

    def _get_render_information(self, styles):
        res = super()._get_render_information(styles)
        if self.env.context.get(
            "active_model", ""
        ) == "project.task" and self.env.context.get("active_id"):
            task = self.env["project.task"].browse(self.env.context.get("active_id"))
            res["doc"] = task
        return res
