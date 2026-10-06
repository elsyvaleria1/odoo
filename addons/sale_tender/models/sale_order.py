from odoo import fields, models


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["mixin.order.tender", "sale.order"]

    _tender_invite_model = "wizard.sale.order.invite.buyer"
    _tender_warning_model = "wizard.sale.order.confirm.open.rival"

    tender_id = fields.Many2one(comodel_name="sale.tender")
    tender_order_ids = fields.One2many(
        related="tender_id.order_ids",
        string="Bids",
    )


class SaleOrderLine(models.Model):
    _name = "sale.order.line"
    _inherit = ["mixin.order.line.tender", "sale.order.line"]
