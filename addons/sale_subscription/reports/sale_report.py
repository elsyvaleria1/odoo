from odoo import models
from odoo.tools import frozendict


class SaleReport(models.Model):
    _inherit = "sale.report"
    _depends = frozendict(
        {
            "product.template": ["recurring_invoice"],
            "sale.order": ["subscription_state"],
        }
    )

    def _get_where_conditions(self):
        conditions = super()._get_where_conditions()
        conditions.append("""(
                o.subscription_state IS NULL OR
                (t.recurring_invoice IS False AND
                o.subscription_state = '7_upsell') OR
                o.subscription_state != '7_upsell'
            )""")
        return conditions
