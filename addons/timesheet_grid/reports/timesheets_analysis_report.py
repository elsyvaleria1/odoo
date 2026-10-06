from odoo import api, fields, models
from odoo.tools import frozendict


class TimesheetsAnalysisReport(models.Model):
    _inherit = "timesheets.analysis.report"
    _depends = frozendict(
        {
            "account.analytic.line": ["validated"],
        }
    )

    validated = fields.Boolean(
        string="Validated line",
        readonly=True,
        aggregator="bool_and",
    )
    validated_status = fields.Selection(
        selection=[("draft", "Draft"), ("validated", "Validated")],
        readonly=True,
    )
    is_timer_running = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_timer_running",
        search="_search_is_timer_running",
    )

    def _compute_is_timer_running(self) -> None:
        timer_timesheet_ids = set(
            self.env["account.analytic.line"]._search(
                [("id", "in", self.ids), ("is_timer_running", "=", True)]
            )
        )
        for timesheet_analysis in self:
            timesheet_analysis.is_timer_running = (
                timesheet_analysis.id in timer_timesheet_ids
            )

    def _search_is_timer_running(self, operator, value):
        return self.env["account.analytic.line"]._search_is_timer_running(
            operator, value
        )

    @api.model
    def _select(self):
        return (
            super()._select()
            + """,
            A.validated AS validated,
            CASE WHEN A.validated THEN 'validated' ELSE 'draft' END AS validated_status
        """
        )
