from odoo import fields, models


class RasterSite(models.Model):
    _name = "geoengine.test.raster.site"
    _description = "Raster layer fixture"

    name = fields.Char()
    position = fields.GeoPoint(srid=3857)
