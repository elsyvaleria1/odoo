from odoo import fields, models


class SaleTender(models.Model):
    _name = "sale.tender"
    _inherit = ["mixin.tender.agreement", "sale.tender"]

    agreement_ids = fields.Many2many(comodel_name="sale.agreement")


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["mixin.order.tender.agreement", "sale.order"]

    awarded_agreement_id = fields.Many2one(comodel_name="sale.agreement")
