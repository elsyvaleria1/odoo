from odoo import fields, models


class UoM(models.Model):
    _inherit = "uom.uom"

    fedex_code = fields.Char(help="UoM Code sent to FedEx")
