from odoo import fields, models


class ResourceAsset(models.Model):
    _inherit = "resource.asset.vehicle"

    weight_capacity = fields.Float(related="product_id.weight_capacity")
    weight_uom_name = fields.Char(related="product_id.weight_uom_name")
    volume_capacity = fields.Float(related="product_id.volume_capacity")
    volume_uom_name = fields.Char(related="product_id.volume_uom_name")
