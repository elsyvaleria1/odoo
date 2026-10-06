from odoo import fields, models


class CoercionPoly(models.Model):
    _name = "coercion.poly"
    _description = "Coercion Poly"
    name = fields.Char()
    area = fields.GeoPolygon()
    val = fields.Integer()


class CoercionMulti(models.Model):
    _name = "coercion.multi"
    _description = "Coercion Multi"
    name = fields.Char()
    area = fields.GeoMultiPolygon()


class CoercionPt3857(models.Model):
    _name = "coercion.pt3857"
    _description = "Coercion Pt 3857"
    name = fields.Char()
    loc = fields.GeoPoint()


class CoercionPt4326(models.Model):
    _name = "coercion.pt4326"
    _description = "Coercion Pt 4326"
    name = fields.Char()
    loc = fields.GeoPoint(srid=4326)
