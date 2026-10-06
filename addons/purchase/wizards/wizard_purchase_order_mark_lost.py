from odoo import fields, models


class WizardPurchaseOrderMarkLost(models.TransientModel):
    _name = "wizard.purchase.order.mark.lost"
    _inherit = "mixin.order.loss"
    _description = "Mark requests for quotation as lost"

    order_ids = fields.Many2many(
        comodel_name="purchase.order",
        relation="purchase_order_loss_wizard_rel",
        string="Requests for Quotation",
        default=lambda self: self.env.context.get("active_ids"),
    )
