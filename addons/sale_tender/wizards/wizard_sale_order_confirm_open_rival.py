from odoo import fields, models


class WizardSaleOrderConfirmOpenRival(models.TransientModel):
    _name = "wizard.sale.order.confirm.open.rival"
    _inherit = ["mixin.tender.warning"]
    _description = "Confirming one bid of a sale tender while others are open"

    order_ids = fields.Many2many(
        comodel_name="sale.order",
        relation="sale_tender_warning_order_rel",
    )
    rival_ids = fields.Many2many(
        comodel_name="sale.order",
        relation="sale_tender_warning_rival_rel",
    )
