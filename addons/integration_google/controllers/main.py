from odoo import http

from odoo.addons.integration.controllers.oauth import OAuthController
from odoo.addons.integration_google.models.integration_service import (
    LEGACY_CALLBACK_PATH,
)


class GoogleOAuthController(OAuthController):
    @http.route(
        LEGACY_CALLBACK_PATH, type="http", auth="user", website=False, csrf=False
    )
    def google_legacy_callback(
        self, code=None, state=None, error=None, error_description=None, **kw
    ):
        return self._handle_callback(code, state, error, error_description)
