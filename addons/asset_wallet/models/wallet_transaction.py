from odoo import fields, models


class WalletTransaction(models.Model):
    _inherit = "wallet.transaction"

    asset_id = fields.Many2one(
        related="card_id.asset_id",
    )
    trace_id = fields.Many2one(
        related="card_id.trace_id",
    )
