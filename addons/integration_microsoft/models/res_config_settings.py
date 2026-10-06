from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    microsoft_oauth_client_id = fields.Char(string="Microsoft Client ID")
    microsoft_oauth_client_secret = fields.Char(string="Microsoft Client Secret")

    @api.model
    def _oauth_client_settings(self) -> dict[str, str]:
        return {
            **super()._oauth_client_settings(),
            "microsoft_oauth": "integration_microsoft.service_microsoft",
        }
