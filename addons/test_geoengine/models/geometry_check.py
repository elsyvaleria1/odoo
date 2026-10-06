from odoo import fields, models


class CheckedParcel(models.Model):
    _name = "geoengine.test.checked.parcel"
    _description = "Geometry check fixture"

    name = fields.Char()
    area = fields.GeoPolygon()
    zones = fields.GeoMultiPolygon()
    area_wgs84 = fields.GeoPolygon(srid=4326)
