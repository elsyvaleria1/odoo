from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    address_autocomplete_google_api_key = fields.Char(
        string="Google Places API Key",
        readonly=False,
        secret_parameter="address_autocomplete_google.api_key",
    )
