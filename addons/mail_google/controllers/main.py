from odoo import http

from odoo.addons.integration.controllers.oauth import OAuthController
from odoo.addons.mail_google.models.integration_service import LEGACY_CALLBACK_PATH


class GmailOAuthController(OAuthController):
    # registered in Google consoles for Gmail before the standard callback
    @http.route(
        LEGACY_CALLBACK_PATH, type="http", auth="user", website=False, csrf=False
    )
    def gmail_legacy_callback(
        self, code=None, state=None, error=None, error_description=None, **kw
    ):
        return self._handle_callback(code, state, error, error_description)
