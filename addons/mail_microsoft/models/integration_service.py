from odoo import api, models

LEGACY_CALLBACK_PATH = "/microsoft_outlook/confirm"


class IntegrationService(models.Model):
    _inherit = "integration.service"

    @api.model
    def _oauth_callback_paths(self) -> tuple[str, ...]:
        return (*super()._oauth_callback_paths(), LEGACY_CALLBACK_PATH)
