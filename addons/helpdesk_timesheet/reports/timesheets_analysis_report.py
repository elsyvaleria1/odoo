from odoo import api, fields, models
from odoo.tools import frozendict


class TimesheetsAnalysisReport(models.Model):
    _inherit = "timesheets.analysis.report"
    _depends = frozendict(
        {
            "account.analytic.line": ["helpdesk_ticket_id"],
        }
    )

    helpdesk_ticket_id = fields.Many2one(
        comodel_name="helpdesk.ticket",
        readonly=True,
    )

    @api.model
    def _select(self):
        return (
            super()._select()
            + """,
                A.helpdesk_ticket_id AS helpdesk_ticket_id
        """
        )
