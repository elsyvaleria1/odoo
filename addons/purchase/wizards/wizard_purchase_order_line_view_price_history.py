from odoo import fields, models


class WizardPurchaseOrderLineViewPriceHistory(models.TransientModel):
    _name = "wizard.purchase.order.line.view.price.history"
    _inherit = ["mixin.order.line.price.history"]
    _description = "Purchase Order Line Price History"

    _price_history_line_model = "purchase.order.line"
    _price_history_action = "purchase.action_purchase_history"

    line_id = fields.Many2one(
        comodel_name="purchase.order.line",
        string="Target Purchase Order Line",
    )
    line_ids = fields.One2many(
        comodel_name="wizard.purchase.order.line.view.price.history.line",
        inverse_name="wizard_id",
        string="Historical Purchase Lines",
    )
    partner_id = fields.Many2one(string="Vendor")
    include_draft = fields.Boolean(string="Include RFQs")
