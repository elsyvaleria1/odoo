from odoo import http

from odoo.addons.auth_passkey.controllers import main as auth_passkey_main


class WebauthnController(auth_passkey_main.WebauthnController):
    @http.route(check_identity=False)
    def json_start_authentication(self):
        return super().json_start_authentication()
