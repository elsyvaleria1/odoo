from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    invoice_approval_threshold = fields.Monetary(
        string="Invoice Approval Threshold Amount",
        currency_field="currency_id",
        default=0.0,
        help="Customer invoices with total >= this amount require approval. "
        "Set to 0 to disable amount-based approval for invoices.",
    )
    bill_approval_threshold = fields.Monetary(
        string="Bill Approval Threshold Amount",
        currency_field="currency_id",
        default=0.0,
        help="Vendor bills with total >= this amount require approval. "
        "Set to 0 to disable amount-based approval for bills.",
    )
    auto_post_on_approval = fields.Boolean(
        string="Auto-Post on Approval",
        default=False,
        help="Automatically post invoices/bills when all required approvals are granted. "
        "If disabled, users must manually post after approval.",
    )
