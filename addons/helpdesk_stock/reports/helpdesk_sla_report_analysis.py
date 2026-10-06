from odoo import fields, models
from odoo.tools import frozendict


class HelpdeskSlaReportAnalysis(models.Model):
    _inherit = "helpdesk.sla.report.analysis"
    _depends = frozendict(
        {
            "helpdesk.ticket": ["product_id"],
        }
    )

    product_id = fields.Many2one(
        comodel_name="product.product",
        readonly=True,
    )

    def _select(self):
        select_str = super()._select()
        select_str += ", T.product_id as product_id"
        return select_str
