from odoo import fields, models
from odoo.tools import frozendict


class ReportProjectTaskUser(models.Model):
    _inherit = "report.project.task.user"
    _depends = frozendict(
        {
            "project.task": ["worksheet_template_id"],
        }
    )

    worksheet_template_id = fields.Many2one(
        comodel_name="worksheet.template",
        readonly=True,
    )

    def _select(self):
        return (
            super()._select()
            + """,
            t.worksheet_template_id
        """
        )

    def _group_by(self):
        return (
            super()._group_by()
            + """,
                t.worksheet_template_id
        """
        )
