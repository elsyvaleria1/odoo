from odoo import fields, models
from odoo.tools import frozendict


class SaleOrderLogReport(models.Model):
    _inherit = "sale.order.log.report"
    _depends = frozendict(
        {
            "sale.order": ["commission_plan_id", "referrer_id"],
        }
    )

    referrer_id = fields.Many2one(
        comodel_name="res.partner",
        readonly=True,
    )
    commission_plan_id = fields.Many2one(
        comodel_name="commission.plan",
        readonly=True,
    )

    def _select(self):
        select = super()._select()
        return f"""
                {select},
                so.referrer_id AS referrer_id,
                so.commission_plan_id AS commission_plan_id
        """
