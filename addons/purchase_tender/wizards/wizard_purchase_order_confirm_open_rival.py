from odoo import fields, models


class WizardPurchaseOrderConfirmOpenRival(models.TransientModel):
    _name = "wizard.purchase.order.confirm.open.rival"
    _inherit = ["mixin.tender.warning"]
    _description = "Confirming one offer of a tender while others are open"

    order_ids = fields.Many2many(
        comodel_name="purchase.order",
        relation="purchase_tender_warning_order_rel",
    )
    rival_ids = fields.Many2many(
        comodel_name="purchase.order",
        relation="purchase_tender_warning_rival_rel",
    )
