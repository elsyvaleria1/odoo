from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    competition_freight_adjusted = fields.Boolean(
        related="company_id.trade_config_id.competition_freight_adjusted",
        readonly=False,
    )
    competition_financing_rate = fields.Float(
        related="company_id.trade_config_id.competition_financing_rate",
        readonly=False,
    )
