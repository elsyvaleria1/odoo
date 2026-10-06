from odoo import fields, models


class MapSite(models.Model):
    _name = "geoengine.test.static.site"
    _description = "Static map fixture"

    name = fields.Char()
    position = fields.GeoPoint(srid=4326)
    area = fields.GeoPolygon()
    restricted = fields.GeoPoint(groups="base.group_system")
