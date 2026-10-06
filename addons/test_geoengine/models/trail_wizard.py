from odoo import fields, models


class TrailPosition(models.Model):
    _name = "geoengine.test.trail.position"
    _description = "Trail wizard fixture"

    name = fields.Char()
    moment = fields.Datetime()
    device_id = fields.Many2one("res.partner")
    the_point = fields.GeoPoint(srid=4326)
