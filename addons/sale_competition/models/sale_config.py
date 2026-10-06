from odoo import fields, models


class SaleConfig(models.Model):
    _inherit = "sale.config"

    competition_min_margin = fields.Float(
        string="Minimum Margin (%)",
        help="The margin over cost below which a quotation line should not go, "
        "for a product whose category sets none.",
    )
    competition_undercut = fields.Float(
        string="Undercut (%)",
        help="How far below the market price the recommended price goes.",
    )
    competition_leader_gap = fields.Float(
        string="Leader Gap (%)",
        default=5.0,
        help="How far below the market a price must be to count as leading it, "
        "with room to raise.",
    )
