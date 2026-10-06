from odoo import fields, models


class AccountConfig(models.Model):
    _inherit = "account.config"

    collection_custody_days_cash = fields.Integer(
        string="Cash Custody Days",
        default=1,
        help="Working days, on the company's calendar, a collector may hold cash "
        "before it is overdue and the daily check reminds them to hand it in.",
    )
    collection_custody_days_check = fields.Integer(
        string="Check Custody Days",
        default=2,
        help="Working days, on the company's calendar, a collector may hold a check "
        "before it is overdue.",
    )
    collection_currency_id = fields.Many2one(
        related="company_id.currency_id",
    )
    collection_custody_limit = fields.Monetary(
        string="Custody Limit",
        currency_field="collection_currency_id",
        help="Most a collector may hold before handing it in, in the company "
        "currency; zero sets no limit. Past it, the collector is asked to hand "
        "in before collecting more.",
    )
    collection_send_receipt = fields.Boolean(
        string="Send Collection Receipts",
        default=True,
        help="Send the customer a receipt, with a link to verify it, as soon as a "
        "collector records what the customer paid.",
    )
    collection_supervisor_id = fields.Many2one(
        comodel_name="res.users",
        check_company=True,
        help="Who answers for field collections: receives what customers report "
        "about their receipts and the payment complements still unsent.",
    )
    collection_shortage_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Collector Shortage Account",
        domain="[('reconcile', '=', True), ('account_type', 'in', ('asset_receivable', 'asset_current'))]",
        check_company=True,
        help="Receivable the money missing from a remittance is charged to, in the "
        "collector's name.",
    )
    collection_overage_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Collector Overage Account",
        domain="[('account_type', 'in', ('income', 'income_other', 'liability_current'))]",
        check_company=True,
        help="Account the money a remittance brings beyond its collections is "
        "credited to.",
    )
    collection_check_fee_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Bounced Check Fee Account",
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        check_company=True,
        help="Income account crediting the bank fee a customer is charged when "
        "their check bounces.",
    )
    collection_max_distance_km = fields.Float(
        string="Collection Distance Limit (km)",
        default=2.0,
        help="A collection recorded farther than this from the customer's "
        "geolocated address is marked for review; zero marks none.",
    )
