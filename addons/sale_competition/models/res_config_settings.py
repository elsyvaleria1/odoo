from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    sale_competition_min_margin = fields.Float(
        related="company_id.sale_config_id.competition_min_margin",
        string="Sales Minimum Margin (%)",
        readonly=False,
    )
    sale_competition_undercut = fields.Float(
        related="company_id.sale_config_id.competition_undercut",
        readonly=False,
    )
    sale_competition_leader_gap = fields.Float(
        related="company_id.sale_config_id.competition_leader_gap",
        string="Sales Leader Gap (%)",
        readonly=False,
    )
