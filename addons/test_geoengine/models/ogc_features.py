from odoo import fields, models


class OgcSite(models.Model):
    _name = "geoengine.test.ogc.site"
    _description = "OGC fixture site"

    name = fields.Char()
    active = fields.Boolean(default=True)
    kind = fields.Selection([("well", "Well"), ("pump", "Pump")])
    seen = fields.Date()
    working = fields.Boolean()
    owner_id = fields.Many2one("res.users")
    secret = fields.Char(groups="base.group_system")
    position = fields.GeoPoint()
    hidden_position = fields.GeoPoint(groups="base.group_system")


class OgcUnread(models.Model):
    _name = "geoengine.test.ogc.unread"
    _description = "OGC fixture nobody reads"

    name = fields.Char()
    position = fields.GeoPoint()
