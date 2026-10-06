from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    approval_required = fields.Boolean(
        default=False,
        tracking=True,
        help="If checked, all invoices and bills using this journal "
        "will require approval regardless of amount or other settings. "
        "Use this for controlled journals (high-value, foreign currency, etc.).",
    )
    approval_notes = fields.Text(
        help="Special instructions or notes for approvers regarding "
        "invoices/bills using this journal. "
        "Example: 'Foreign currency journal - verify exchange rate'"
    )
