from odoo import fields, models

UTM_14N = 32614


class TileSite(models.Model):
    _name = "geoengine.test.tile.site"
    _description = "Vector tile fixture"
    _order = "name desc, id"

    name = fields.Char()
    active = fields.Boolean(default=True)
    score = fields.Float()
    colour = fields.Char()
    kind = fields.Selection([("well", "Well"), ("pump", "Pump")])
    seen = fields.Date()
    position = fields.GeoPoint()
    utm_position = fields.GeoPoint(srid=UTM_14N)
    zone = fields.GeoPolygon()
    restricted_position = fields.GeoPoint(groups="base.group_system")
    restricted_score = fields.Float(groups="base.group_system")
