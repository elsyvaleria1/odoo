from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    sale_min_margin = fields.Float(
        string="Minimum Sale Margin (%)",
        help="The margin over cost below which a quotation line of this category "
        "should not go. Empty: the company's.",
    )
