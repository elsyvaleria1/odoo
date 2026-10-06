from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    po_approval_required = fields.Boolean(
        default=False,
        groups="purchase.group_purchase_manager",
        help="If checked, all purchase orders containing this product "
        "will require approval regardless of amount or other settings. "
        "Use this for controlled products (specialized equipment, regulated items, etc.).",
    )
    po_approval_notes = fields.Text(
        groups="purchase.group_purchase_manager",
        help="Special instructions or notes for approvers regarding "
        "purchase orders containing this product. "
        "Example: 'Specialized equipment - verify technical requirements'",
    )
