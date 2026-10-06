from odoo import fields, models


class WizardPurchaseOrderLineViewPriceHistoryLine(models.TransientModel):
    _name = "wizard.purchase.order.line.view.price.history.line"
    _inherit = ["mixin.order.line.price.history.line"]
    _description = "Purchase Order Line Price History Result"

    wizard_id = fields.Many2one(
        comodel_name="wizard.purchase.order.line.view.price.history",
        ondelete="cascade",
    )
    line_id = fields.Many2one(comodel_name="purchase.order.line")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    order_id = fields.Many2one(related="line_id.order_id")
    partner_id = fields.Many2one(
        related="line_id.partner_id",
        string="Vendor",
    )
    date = fields.Datetime(related="line_id.date_order")
    qty = fields.Float(related="line_id.product_qty")
    product_uom_id = fields.Many2one(related="line_id.product_uom_id")
    price_unit = fields.Float(related="line_id.price_unit")
    discount = fields.Float(related="line_id.discount")
    tax_ids = fields.Many2many(related="line_id.tax_ids")
