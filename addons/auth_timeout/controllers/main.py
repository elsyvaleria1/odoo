from odoo import http
from odoo.http import request


class AuthTimeOutController(http.Controller):
    @http.route(
        "/auth-timeout/check-identity",
        type="http",
        auth="user",
        website=True,
        sitemap=False,
        check_identity=False,
    )
    def check_identity(self, redirect=None):
        return request.render("auth_timeout.check_identity", {"redirect": redirect})

    @http.route(
        "/auth-timeout/session/check-identity",
        type="jsonrpc",
        auth="user",
        check_identity=False,
    )
    def check_identity_session(self, **kwargs):
        return request.env["ir.http"]._check_identity(kwargs)

    @http.route(
        "/auth-timeout/send-totp-mail-code",
        type="jsonrpc",
        auth="user",
        check_identity=False,
    )
    def send_totp_mail_code(self):
        self.env.user._send_totp_mail_code()
