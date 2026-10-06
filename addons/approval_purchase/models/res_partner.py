from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    po_approval_required = fields.Boolean(
        default=False,
        groups="purchase.group_purchase_manager",
        help="If checked, all purchase orders from this vendor will require approval "
        "regardless of amount or other settings. "
        "Use this for new vendors or high-risk suppliers.",
    )
    po_approval_notes = fields.Text(
        groups="purchase.group_purchase_manager",
        help="Special instructions or notes for approvers regarding "
        "purchase orders from this vendor. "
        "Example: 'New vendor - verify credentials before approving'",
    )
