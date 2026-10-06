from odoo import fields, models


class CrsZone(models.Model):
    _name = "geoengine.test.crs.zone"
    _description = "CRS contract fixture"

    name = fields.Char()
    area_wgs84 = fields.GeoPolygon(srid=4326)
    area_mercator = fields.GeoPolygon(srid=3857)
