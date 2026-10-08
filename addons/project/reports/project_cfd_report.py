from collections.abc import Sequence

from odoo import api, fields, models
from odoo.exceptions import UserError


class ProjectCFDReport(models.AbstractModel):
    _name = "project.cfd.report"
    _inherit = ["project.task.burndown.chart.report"]
    _description = "Cumulative Flow Diagram"

    task_count = fields.Integer(readonly=True)

    @api.model
    def _check_group_by(self, groupby: Sequence[str]) -> None:
        if "step_id" not in groupby:
            raise UserError(
                self.env._(
                    "The Cumulative Flow Diagram must be grouped by date"
                    " and by Workflow Step."
                )
            )
        super()._check_group_by(groupby)
