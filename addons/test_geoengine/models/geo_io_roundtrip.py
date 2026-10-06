from odoo import fields, models


class IoParcel(models.Model):
    _name = "geoengine.test.io.parcel"
    _description = "GeoJSON I/O fixture"

    name = fields.Char()
    code = fields.Char()
    area = fields.Float()
    owner_id = fields.Many2one("res.partner")
    boundary = fields.GeoPolygon(srid=4326)
