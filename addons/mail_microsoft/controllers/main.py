from odoo import http

from odoo.addons.integration.controllers.oauth import OAuthController
from odoo.addons.mail_microsoft.models.integration_service import (
    LEGACY_CALLBACK_PATH,
)


class OutlookOAuthController(OAuthController):
    @http.route(
        LEGACY_CALLBACK_PATH, type="http", auth="user", website=False, csrf=False
    )
    def outlook_legacy_callback(
        self, code=None, state=None, error=None, error_description=None, **kw
    ):
        return self._handle_callback(code, state, error, error_description)
