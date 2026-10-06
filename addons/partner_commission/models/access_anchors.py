from odoo import models
from odoo.tools import frozendict


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    _access_anchors = frozendict(
        {
            "order_user": models.Anchor("order_id.user_id", kind="owner"),
        }
    )
