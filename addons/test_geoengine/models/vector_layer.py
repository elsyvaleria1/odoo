from odoo import fields, models


class LayerSite(models.Model):
    _name = "geoengine.test.layer.site"
    _description = "Vector layer fixture"

    name = fields.Char()
    band = fields.Char()
    tonnage = fields.Integer()
    active = fields.Boolean(default=True)
    position = fields.GeoPoint(srid=3857)


class LayerOther(models.Model):
    _name = "geoengine.test.layer.other"
    _description = "A second model, for the cross-model refusals"

    code = fields.Char()
    qty = fields.Integer()
