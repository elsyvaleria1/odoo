from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    online_partner_information = fields.Char(readonly=True)
