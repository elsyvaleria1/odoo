from odoo import api, fields, models
from odoo.tools import frozendict


class PlanningAnalysisReport(models.Model):
    _inherit = "planning.analysis.report"
    _depends = frozendict(
        {
            "planning.slot": ["project_id"],
        }
    )

    project_id = fields.Many2one(
        comodel_name="project.project",
        readonly=True,
    )

    @api.model
    def _select(self):
        return (
            super()._select()
            + """,
            S.project_id AS project_id
        """
        )

    @api.model
    def _group_by(self):
        return (
            super()._group_by()
            + """,
            S.project_id
        """
        )
