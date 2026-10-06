from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    purchase_competition_min_margin = fields.Float(
        related="company_id.purchase_config_id.competition_min_margin",
        string="Purchase Minimum Margin (%)",
        readonly=False,
    )
    purchase_competition_overbid = fields.Float(
        related="company_id.purchase_config_id.competition_overbid",
        readonly=False,
    )
    purchase_competition_leader_gap = fields.Float(
        related="company_id.purchase_config_id.competition_leader_gap",
        string="Purchase Leader Gap (%)",
        readonly=False,
    )
