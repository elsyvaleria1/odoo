from odoo import fields, models


class AccessSite(models.Model):
    _name = "geoengine.test.access.site"
    _description = "Map access fixture"

    name = fields.Char()
    position = fields.GeoPoint()
    zone = fields.GeoPolygon(groups="base.group_system")


class AccessHidden(models.Model):
    _name = "geoengine.test.access.hidden"
    _description = "Map access fixture nobody reads"

    name = fields.Char()
    position = fields.GeoPoint()
