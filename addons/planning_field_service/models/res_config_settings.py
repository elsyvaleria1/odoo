from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    group_field_service_allow_geolocation = fields.Boolean(
        string="Geolocation",
        implied_group="planning.group_field_service_allow_geolocation",
        help="Log where the phone was when a visit is started and completed.",
    )
