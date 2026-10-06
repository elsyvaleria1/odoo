from odoo import fields, models


class PurchaseConfig(models.Model):
    _inherit = "purchase.config"

    competition_min_margin = fields.Float(
        string="Minimum Margin (%)",
        help="The margin over what we pay that our resale price must keep, for a "
        "product whose category sets none.",
    )
    competition_overbid = fields.Float(
        string="Overbid (%)",
        help="How far above the market price the recommended price goes.",
    )
    competition_leader_gap = fields.Float(
        string="Leader Gap (%)",
        default=5.0,
        help="How far above the market a price must be to count as leading it, "
        "with room to lower.",
    )
