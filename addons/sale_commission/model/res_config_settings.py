from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    group_commission_forecast = fields.Boolean(
        string="Achievement Forecast",
        implied_group="sale_commission.group_commission_forecast",
    )
