from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    invoice_approval_required = fields.Boolean(
        default=False,
        tracking=True,
        help="If checked, all customer invoices for this partner will require approval "
        "regardless of amount or other settings. "
        "Use this for high-value customers or special approval requirements.",
    )
    bill_approval_required = fields.Boolean(
        default=False,
        tracking=True,
        help="If checked, all vendor bills from this partner will require approval "
        "regardless of amount or other settings. "
        "Use this for new vendors or high-risk suppliers.",
    )
    invoice_approval_notes = fields.Text(
        string="Invoice/Bill Approval Notes",
        help="Special instructions or notes for approvers regarding "
        "invoices/bills for this partner. "
        "Example: 'New customer - verify credit terms before approving'",
    )
