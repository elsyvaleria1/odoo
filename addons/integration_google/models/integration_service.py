from odoo import api, models

LEGACY_CALLBACK_PATH = "/google_account/authentication"


class IntegrationService(models.Model):
    _inherit = "integration.service"

    @api.model
    def _oauth_callback_paths(self) -> tuple[str, ...]:
        return (*super()._oauth_callback_paths(), LEGACY_CALLBACK_PATH)
