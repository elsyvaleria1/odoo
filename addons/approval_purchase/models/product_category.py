from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    po_approval_required = fields.Boolean(
        default=False,
        groups="purchase.group_purchase_manager",
        help="If checked, all purchase orders containing products from this category "
        "will require approval regardless of amount or other settings. "
        "Use this for controlled products (chemicals, equipment, etc.).",
    )
    po_approval_notes = fields.Text(
        groups="purchase.group_purchase_manager",
        help="Special instructions or notes for approvers regarding "
        "purchase orders containing products from this category. "
        "Example: 'Controlled chemical - verify safety requirements'",
    )
