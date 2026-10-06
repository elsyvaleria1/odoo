from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    registration_ids = fields.One2many(
        comodel_name="event.registration",
        inverse_name="partner_id",
        string="Event Registrations",
    )
