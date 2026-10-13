from odoo import fields, models


class AccountTaxGroup(models.Model):
    _inherit = "account.tax.group"

    tax_payable_account_id = fields.Many2one(
        comodel_name="account.account",
        check_company=True,
        help="Tax current account used as a counterpart to the Tax Closing Entry when in favor of the authorities.",
    )
    tax_receivable_account_id = fields.Many2one(
        comodel_name="account.account",
        check_company=True,
        help="Tax current account used as a counterpart to the Tax Closing Entry when in favor of the company.",
    )
    advance_tax_payment_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Tax Advance Account",
        check_company=True,
        help="Downpayments posted on this account will be considered by the Tax Closing Entry.",
    )
