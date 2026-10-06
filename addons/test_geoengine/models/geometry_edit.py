from odoo import fields, models


class EditedFence(models.Model):
    _name = "geoengine.test.edited.fence"
    _description = "Shape edit fixture"

    name = fields.Char()
    zones = fields.GeoMultiPolygon()
    route = fields.GeoMultiLine()


class SplitParcel(models.Model):
    _name = "geoengine.test.split.parcel"
    _description = "Split and merge fixture"

    name = fields.Char()
    active = fields.Boolean(default=True)
    zones = fields.GeoMultiPolygon()
    area = fields.GeoPolygon()
