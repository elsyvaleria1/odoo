from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    lazada_buyer_extern_id = fields.Char(string="Lazada Buyer ID")
