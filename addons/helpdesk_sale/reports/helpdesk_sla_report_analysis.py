from odoo import fields, models
from odoo.tools import frozendict


class HelpdeskSlaReportAnalysis(models.Model):
    _inherit = "helpdesk.sla.report.analysis"
    _depends = frozendict(
        {
            "helpdesk.ticket": ["sale_order_id"],
        }
    )

    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Ref. Sales Order",
        readonly=True,
        groups="sale.group_sale_salesman,account.group_account_invoice",
    )

    def _select(self):
        select_str = super()._select()
        select_str += ", T.sale_order_id as sale_order_id"
        return select_str
