from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    shopee_buyer_identifier = fields.Integer(string="Shopee Buyer ID")
