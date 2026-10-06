from odoo import fields, models


class WizardSaleOrderLineViewPriceHistory(models.TransientModel):
    _name = "wizard.sale.order.line.view.price.history"
    _inherit = ["mixin.order.line.price.history"]
    _description = "Sale Order Line Price History"

    _price_history_line_model = "sale.order.line"
    _price_history_action = "sale.action_sale_history"

    line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Target Sale Order Line",
    )
    line_ids = fields.One2many(
        comodel_name="wizard.sale.order.line.view.price.history.line",
        inverse_name="wizard_id",
        string="Historical Sale Lines",
    )
    partner_id = fields.Many2one(string="Customer")
    include_draft = fields.Boolean(string="Include Quotations")
