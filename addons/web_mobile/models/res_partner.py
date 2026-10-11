from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    image_medium = fields.Binary(
        related="avatar_128",
        string="Medium-sized image",
        store=False,
        readonly=True,
    )
