from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    stock_approval_required = fields.Boolean(
        string="Require Approval for Stock Transfers",
        default=False,
        help="If checked, stock transfers of products in this category will require approval",
    )
