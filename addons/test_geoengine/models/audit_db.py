from odoo import fields, models


class GeoAuditFixture(models.Model):
    _name = "geoengine.audit.fixture"
    _description = "Geoengine Audit Fixture"

    name = fields.Char()
    the_point = fields.GeoPoint(srid=3857)
    the_zone = fields.GeoPolygon(srid=3857)
