from odoo import fields, models


class ConfigZone(models.Model):
    _name = "config.zone"
    _description = "Config Zone"
    name = fields.Char()
    area = fields.GeoPolygon()
    qty = fields.Integer()


class CountZone(models.Model):
    _name = "count.zone"
    _description = "Count Zone"
    name = fields.Char()
    active = fields.Boolean(default=True)
    area = fields.GeoPolygon()
    grade = fields.Integer()
