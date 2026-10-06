from odoo import fields, models


class HeatmapSite(models.Model):
    _name = "geoengine.test.heatmap.site"
    _description = "Heatmap/cluster fixture"

    name = fields.Char()
    position = fields.GeoPoint(srid=3857)
    footprint = fields.GeoPolygon(srid=3857)
    tonnage = fields.Float()
