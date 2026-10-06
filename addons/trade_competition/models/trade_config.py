from odoo import fields, models


class TradeConfig(models.Model):
    _inherit = "trade.config"

    competition_freight_adjusted = fields.Boolean(
        string="Adjust for Freight",
        help="Add the freight a competitor leaves to the counterparty to its "
        "comparable price.",
    )
    competition_financing_rate = fields.Float(
        string="Financing Rate (%)",
        help="Annual rate at which the credit a competitor's payment terms give "
        "is priced into its comparable price. Zero leaves credit out.",
    )
