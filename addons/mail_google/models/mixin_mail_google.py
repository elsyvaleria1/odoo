from odoo import models

from odoo.addons.mail_oauth2.oauth2_provider import Oauth2MailProvider

GMAIL = Oauth2MailProvider(
    label="Gmail",
    service="integration_google.service_google",
    scope="https://mail.google.com/ openid email",
)


class MixinMailGoogle(models.AbstractModel):
    _name = "mixin.mail.google"
    _inherit = ["mixin.oauth2.mail.provider"]
    _description = "Gmail Mixin"

    def action_mail_google_authorize(self):
        return self._oauth2_open_uri(GMAIL)

    def _mail_google_auth_string(self, login) -> str:
        return self._oauth2_generate_string(GMAIL, login)
