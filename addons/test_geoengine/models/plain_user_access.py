from odoo import fields, models


class PlainSite(models.Model):
    _name = "geoengine.test.plain.site"
    _description = "Plain-user access fixture"

    name = fields.Char()
    band = fields.Char()
    tonnage = fields.Integer()
    position = fields.GeoPoint(srid=3857)
