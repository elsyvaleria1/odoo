from odoo import fields, models


class FrontdeskDrink(models.Model):
    _name = "frontdesk.drink"
    _description = "Frontdesk Drink"
    _order = "sequence, name"

    name = fields.Char(required=True)
    drink_image = fields.Image()
    sequence = fields.Integer(default=1)
    notify_user_ids = fields.Many2many(
        comodel_name="res.users",
        string="People to Notify",
        required=True,
    )
    active = fields.Boolean(default=True)
