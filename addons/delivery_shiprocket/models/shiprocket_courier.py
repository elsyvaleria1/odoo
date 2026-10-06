from odoo import fields, models


class ShiprocketCourier(models.Model):
    _name = "shiprocket.courier"
    _description = "Shiprocket Courier"
    _order = "name"

    name = fields.Char(
        string="Service Name",
        readonly=True,
    )
    courier_code = fields.Integer(readonly=True)
    shiprocket_email = fields.Char()
