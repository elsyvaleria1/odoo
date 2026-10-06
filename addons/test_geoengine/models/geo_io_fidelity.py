from odoo import fields, models


class FidelityParcel(models.Model):
    _name = "geoengine.test.fidelity.parcel"
    _description = "Geo IO fidelity fixture"

    name = fields.Char()
    note = fields.Char()
    irrigated = fields.Boolean()
    owner_id = fields.Many2one("res.partner")
    boundary = fields.GeoPoint(srid=4326)
