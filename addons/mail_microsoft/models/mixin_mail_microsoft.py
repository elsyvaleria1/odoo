from odoo import models

from odoo.addons.mail_oauth2.oauth2_provider import Oauth2MailProvider

OUTLOOK = Oauth2MailProvider(
    label="Outlook",
    service="integration_microsoft.service_microsoft",
    # offline_access asks for a refresh token; `openid email` has the code
    # exchange name the account that consented
    scope=lambda records: (
        "openid email offline_access "
        f"https://outlook.office.com/User.read {records._MAIL_MICROSOFT_SCOPE}"
    ),
)


class MixinMailMicrosoft(models.AbstractModel):
    _name = "mixin.mail.microsoft"
    _inherit = ["mixin.oauth2.mail.provider"]
    _description = "Outlook Mixin"

    # what the server does with its mailbox, on the concrete model
    _MAIL_MICROSOFT_SCOPE = None

    def action_mail_microsoft_authorize(self):
        return self._oauth2_open_uri(OUTLOOK)

    def _mail_microsoft_auth_string(self, login) -> str:
        return self._oauth2_generate_string(OUTLOOK, login)
