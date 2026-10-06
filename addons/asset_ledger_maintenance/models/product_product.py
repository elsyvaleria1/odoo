from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    maintenance_ok = fields.Boolean(
        related="product_tmpl_id.maintenance_ok",
        readonly=False,
    )
