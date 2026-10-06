from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    purchase_min_margin = fields.Float(
        string="Minimum Purchase Margin (%)",
        help="The margin over what we pay that our resale price must keep for a "
        "product of this category. Empty: the company's.",
    )
