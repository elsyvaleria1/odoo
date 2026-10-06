from odoo import fields, models


class ResCurrency(models.Model):
    _inherit = "res.currency"

    monster_id = fields.Integer(string="Monster ID")
