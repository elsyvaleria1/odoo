from odoo import fields, models


class BoundsParcel(models.Model):
    _name = "geoengine.test.bounds.parcel"
    _description = "Class-bounds fixture"

    name = fields.Char()
    active = fields.Boolean(default=True)
    yield_t = fields.Float()
    yield_unstored = fields.Float(compute="_compute_yield_unstored", store=False)
    boundary = fields.GeoPolygon(srid=4326)

    def _compute_yield_unstored(self):
        for rec in self:
            rec.yield_unstored = rec.yield_t * 2
