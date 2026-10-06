from odoo import fields, models


class PurchaseTender(models.Model):
    _name = "purchase.tender"
    _inherit = ["mixin.tender.agreement", "purchase.tender"]

    agreement_ids = fields.Many2many(comodel_name="purchase.agreement")


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["mixin.order.tender.agreement", "purchase.order"]

    awarded_agreement_id = fields.Many2one(comodel_name="purchase.agreement")
