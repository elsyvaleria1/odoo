from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    so_approval_required = fields.Boolean(
        default=False,
        groups="sale.group_sale_manager",
        help="If checked, all sales orders containing this product "
        "will require approval regardless of amount or other settings. "
        "Use this for controlled products (high-value items, regulated goods, etc.).",
    )
    so_approval_notes = fields.Text(
        help="Special instructions or notes for approvers regarding "
        "sales orders containing this product. "
        "Example: 'High-value item - verify customer credit before approving'"
    )
