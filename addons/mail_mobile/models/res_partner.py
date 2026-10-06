from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    ocn_token = fields.Char(
        string="OCN Token",
        copy=False,
        readonly=True,
        help="Used for sending notification to registered devices",
    )
