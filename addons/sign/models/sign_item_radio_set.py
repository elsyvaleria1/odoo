from odoo import fields, models


class SignItemRadioSet(models.Model):
    _name = "sign.item.radio.set"
    _description = "Radio button set for keeping radio button items together"

    radio_items = fields.One2many(
        comodel_name="sign.item",
        inverse_name="radio_set_id",
    )
    num_options = fields.Count(
        count_of="radio_items",
        string="Number of Radio Button options",
    )
