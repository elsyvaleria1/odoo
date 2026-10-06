from odoo import fields, models


class ShiprocketChannel(models.Model):
    _name = "shiprocket.channel"
    _description = "Shiprocket Channel"
    _order = "name"

    name = fields.Char(
        string="Channel Name",
        readonly=True,
    )
    channel_code = fields.Integer(readonly=True)
    shiprocket_email = fields.Char()
