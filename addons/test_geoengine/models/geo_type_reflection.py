from odoo import fields, models


class ReflectionParcel(models.Model):
    _name = "geoengine.test.reflection.parcel"
    _description = "geo_type reflection fixture"

    name = fields.Char()
    boundary = fields.GeoPolygon(srid=4326)
