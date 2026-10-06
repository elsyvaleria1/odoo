import time

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.web import urljoin as url_join
from odoo.tools import register_signed_scope

from odoo.addons.mail_oauth2.models.mixin_oauth2_mail_provider import (
    OAUTH2_STATE_MAX_AGE_SECONDS,
    OAUTH2_TOKEN_REQUEST_TIMEOUT,
    OAUTH2_TOKEN_VALIDITY_THRESHOLD,
)
from odoo.addons.mail_oauth2.oauth2_provider import Oauth2MailProvider

OUTLOOK_TOKEN_REQUEST_TIMEOUT = OAUTH2_TOKEN_REQUEST_TIMEOUT
OUTLOOK_TOKEN_VALIDITY_THRESHOLD = OAUTH2_TOKEN_VALIDITY_THRESHOLD

OUTLOOK = Oauth2MailProvider(
    prefix="microsoft_outlook",
    label="Outlook",
    route="microsoft_outlook",
    csrf_scope=register_signed_scope(
        "microsoft_outlook_oauth",
        purpose="the OAuth state that returns an Outlook authorization to the "
        "mail server it was started from, in the session and for the user that "
        "started it",
        lifetime="its expiry: the callback refuses a state older than "
        f"{OAUTH2_STATE_MAX_AGE_SECONDS} seconds, or one already consumed",
    ),
    iap_service="outlook",
    iap_endpoint_param="mail.server.outlook.iap.endpoint",
    iap_endpoint_default="https://outlook.api.odoo.com",
    authorize_url=lambda records: url_join(
        records._get_microsoft_endpoint(), "authorize"
    ),
    token_url=lambda records: url_join(records._get_microsoft_endpoint(), "token"),
    # offline_access is needed to have the refresh_token
    scope=lambda records: (
        "openid email offline_access "
        f"https://outlook.office.com/User.read {records._OUTLOOK_SCOPE}"
    ),
    authorize_extra_params={"response_mode": "query"},
    token_sends_scope=True,
    token_error_detail=True,
)


class MixinMicrosoftOutlook(models.AbstractModel):
    _name = "mixin.microsoft.outlook"
    _inherit = ["mixin.oauth2.mail.provider"]

    _description = "Microsoft Outlook Mixin"

    _OUTLOOK_SCOPE = None

    # Doors onto `oauth2_credential_id`, not stores. The names stay: they are in
    # the views and in every caller.
    microsoft_outlook_refresh_token = fields.Char(
        string="Outlook Refresh Token",
        compute="_compute_microsoft_outlook_tokens",
        inverse="_inverse_microsoft_outlook_refresh_token",
        copy=False,
        classification="secret.credential",
        groups="base.group_system",
    )
    microsoft_outlook_access_token = fields.Char(
        string="Outlook Access Token",
        compute="_compute_microsoft_outlook_tokens",
        inverse="_inverse_microsoft_outlook_access_token",
        copy=False,
        classification="secret.credential",
        groups="base.group_system",
    )
    microsoft_outlook_access_token_expiration = fields.Integer(
        string="Outlook Access Token Expiration Timestamp",
        copy=False,
        groups="base.group_system",
    )

    @api.depends("oauth2_credential_id")
    def _compute_microsoft_outlook_tokens(self) -> None:
        for record in self:
            access_token, refresh_token = record._oauth2_stored_tokens()
            record.microsoft_outlook_access_token = access_token
            record.microsoft_outlook_refresh_token = refresh_token

    def _inverse_microsoft_outlook_access_token(self) -> None:
        for record in self:
            record._oauth2_store_tokens(
                access_token=record.microsoft_outlook_access_token
            )

    def _inverse_microsoft_outlook_refresh_token(self) -> None:
        for record in self:
            record._oauth2_store_tokens(
                refresh_token=record.microsoft_outlook_refresh_token
            )

    def open_microsoft_outlook_uri(self):
        return self._oauth2_open_uri(OUTLOOK)

    def _get_outlook_refresh_token(self, authorization_code):
        """Request the refresh token and the initial access token from the authorization code.

        :return:
            refresh_token, access_token, access_token_expiration
        """
        return self._oauth2_get_refresh_token(OUTLOOK, authorization_code)

    def _get_outlook_token(self, grant_type, **values):
        return self._oauth2_get_token(OUTLOOK, grant_type, **values)

    def _get_outlook_access_token(self, refresh_token) -> tuple:
        """A fresh grant for this refresh token, straight from Microsoft (or
        IAP): refresh_token, access_token, id_token, access_token_expiration.

        The connect flow reads the id_token to check which mailbox signed in;
        the stored credential's own refresh does not return one.
        """
        client_id, client_secret = self._oauth2_credentials(OUTLOOK)
        if not client_id or not client_secret:
            return self._get_outlook_access_token_iap(refresh_token)
        response = self._get_outlook_token("refresh_token", refresh_token=refresh_token)
        return (
            response["refresh_token"],
            response["access_token"],
            response["id_token"],
            int(time.time()) + int(response["expires_in"]),
        )

    def _get_outlook_access_token_iap(self, refresh_token):
        return self._oauth2_get_access_token_iap(OUTLOOK, refresh_token)

    def _generate_outlook_oauth2_string(self, login):
        """Generate a OAuth2 string which can be used for authentication.

        :param login: Email address of the Outlook account to authenticate
        :return: The SASL argument for the OAuth2 mechanism.
        """
        return self._oauth2_generate_string(
            OUTLOOK, login, self._renew_outlook_access_token
        )

    def _renew_outlook_access_token(self) -> None:
        if not self.microsoft_outlook_refresh_token:
            raise UserError(
                self.env._("Please connect with your Outlook account before using it.")
            )
        client_id, client_secret = self._oauth2_credentials(OUTLOOK)
        if not client_id or not client_secret:
            (
                self.microsoft_outlook_refresh_token,
                self.microsoft_outlook_access_token,
                _id_token,
                self.microsoft_outlook_access_token_expiration,
            ) = self._get_outlook_access_token_iap(self.microsoft_outlook_refresh_token)
            return
        _access_token, expiration = self._oauth2_refresh_access_token(OUTLOOK)
        self.microsoft_outlook_access_token_expiration = expiration

    @api.model
    def _get_microsoft_endpoint(self):
        return self.env.registry.settings.get(
            self.env,
            "mail_microsoft.endpoint",
            "https://login.microsoftonline.com/common/oauth2/v2.0/",
        )
