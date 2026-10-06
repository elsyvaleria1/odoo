from odoo import fields, models


class Adv(models.Model):
    _name = "geoengine.adv.fixture"
    _description = "Adv"
    name = fields.Char()
    kind = fields.Char()
    active = fields.Boolean(default=True)
    pt = fields.GeoPoint(srid=3857)
    zone = fields.GeoPolygon(srid=3857)
    wgs = fields.GeoPoint(srid=4326)


class Ref(models.Model):
    _name = "geoengine.adv.ref"
    _description = "Adv Ref"
    name = fields.Char()
    active = fields.Boolean(default=True)
    area = fields.GeoPolygon(srid=3857)


class Link(models.Model):
    _name = "geoengine.adv.link"
    _description = "Adv Link"
    name = fields.Char()
    ref_id = fields.Many2one(comodel_name="geoengine.adv.ref")


class Pred(models.Model):
    _name = "geoengine.pred.fixture"
    _description = "Pred"
    name = fields.Char()
    pt = fields.GeoPoint(srid=3857)


class Dw(models.Model):
    _name = "geoengine.dwithin.fixture"
    _description = "Dwithin"
    name = fields.Char()
    pt = fields.GeoPoint(srid=4326)
