from odoo import models
from odoo.tools import frozendict


class MailingTraceReport(models.Model):
    _inherit = "mailing.trace.report"
    _depends = frozendict(
        {
            "mailing.mailing": ["use_in_marketing_automation"],
        }
    )

    def _report_get_request_where_items(self):
        res = super()._report_get_request_where_items()
        res.append("mailing.use_in_marketing_automation IS NOT TRUE")
        return res
