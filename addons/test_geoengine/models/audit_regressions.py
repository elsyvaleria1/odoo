from odoo import fields, models


class AuditSpot(models.Model):
    _name = "audit.spot"
    _description = "Audit Spot"
    name = fields.Char()
    spot = fields.GeoPoint()
    grade = fields.Integer()


class AuditOther(models.Model):
    _name = "audit.other"
    _description = "Audit Other"
    name = fields.Char()
    spot = fields.GeoPoint()


class AuditArea(models.Model):
    _name = "audit.area"
    _description = "Audit Area"
    name = fields.Char()
    zone = fields.GeoPolygon()
    zones = fields.GeoMultiPolygon()
