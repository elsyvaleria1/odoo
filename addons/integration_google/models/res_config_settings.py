from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    google_oauth_client_id = fields.Char(string="Google Client ID")
    google_oauth_client_secret = fields.Char(string="Google Client Secret")

    @api.model
    def _oauth_client_settings(self) -> dict[str, str]:
        return {
            **super()._oauth_client_settings(),
            "google_oauth": "integration_google.service_google",
        }
