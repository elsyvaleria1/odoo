from odoo import models


class PurchaseOrderLine(models.Model):
    _name = "purchase.order.line"
    _inherit = ["mixin.approval.document.line", "purchase.order.line"]
