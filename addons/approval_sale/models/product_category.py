from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    so_approval_required = fields.Boolean(
        default=False,
        groups="sale.group_sale_manager",
        help="If checked, all sales orders containing products from this category "
        "will require approval regardless of amount or other settings. "
        "Use this for controlled products (high-value items, regulated products, etc.).",
    )
    so_approval_notes = fields.Text(
        help="Special instructions or notes for approvers regarding "
        "sales orders containing products from this category. "
        "Example: 'High-value product - verify customer payment terms'"
    )
