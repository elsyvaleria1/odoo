from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    so_approval_required = fields.Boolean(
        default=False,
        groups="sale.group_sale_manager",
        help="If checked, all sales orders for this customer will require approval "
        "regardless of amount or other settings. "
        "Use this for new customers or high credit risk.",
    )
    so_approval_notes = fields.Text(
        help="Special instructions or notes for approvers regarding "
        "sales orders for this customer. "
        "Example: 'New customer - verify credit limit before approving'"
    )
