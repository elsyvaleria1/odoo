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
        """Exclude upsell subscription information from sales report.

        Do not add upsell information to the sales report as it will be
        updated on the original sale order. Note: this analysis may not be
        accurate because it does not take account of discounts, for example.
        """
        conditions = super()._get_where_conditions()
        conditions.append("""(
                o.subscription_state IS NULL OR
                (t.recurring_invoice IS False AND
                o.subscription_state = '7_upsell') OR
                o.subscription_state != '7_upsell'
            )""")
        return conditions
