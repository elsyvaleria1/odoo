from odoo import models
from odoo.fields import Domain

from odoo.addons.sale_subscription.models.sale_order import SUBSCRIPTION_PROGRESS_STATE


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _get_domain_order_fiscal_position_recompute(self):
        return super()._get_domain_order_fiscal_position_recompute() | Domain(
            [
                "&",
                "|",
                ("partner_id", "in", self.ids),
                ("partner_shipping_id", "in", self.ids),
                "&",
                ("website_id", "!=", False),
                "&",
                ("state", "=", "done"),
                "&",
                ("locked", "=", False),
                "&",
                ("is_subscription", "=", True),
                ("subscription_state", "in", SUBSCRIPTION_PROGRESS_STATE),
            ]
        )
