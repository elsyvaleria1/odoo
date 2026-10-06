from odoo import fields, models
from odoo.tools import frozendict


class SaleSubscriptionReport(models.Model):
    _inherit = "sale.subscription.report"
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

    def _get_fields_select(self):
        res = super()._get_fields_select()
        res["referrer_id"] = "o.referrer_id"
        res["commission_plan_id"] = "o.commission_plan_id"
        return res

    def _get_fields_group_by(self) -> list:
        return [
            *super()._get_fields_group_by(),
            "o.referrer_id",
            "o.commission_plan_id",
        ]
