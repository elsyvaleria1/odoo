from odoo import fields, models


class ProjectTaskBurndownChartReport(models.AbstractModel):
    _inherit = "project.task.burndown.chart.report"

    worksheet_template_id = fields.Many2one(
        comodel_name="worksheet.template",
        readonly=True,
    )

    @property
    def task_specific_fields(self):
        return super().task_specific_fields + [
            "worksheet_template_id",
        ]
