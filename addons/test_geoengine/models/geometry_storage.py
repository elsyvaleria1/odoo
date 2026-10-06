from odoo import fields, models


class StorageSite(models.Model):
    _name = "geoengine.test.storage.site"
    _description = "Geometry storage fixture"

    name = fields.Char()
    mercator = fields.GeoPoint(srid=3857)
    wgs84 = fields.GeoPoint(srid=4326)
    lambert = fields.GeoPoint(srid=2154)
    utm = fields.GeoPoint(srid=32614)
    elevated = fields.GeoPoint(srid=4326, dim="3")


class StorageMixin(models.AbstractModel):
    _name = "geoengine.test.storage.mixin"
    _description = "Abstract geometry fixture"

    spot = fields.GeoPoint()
