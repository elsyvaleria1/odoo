import logging

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import email_normalize

from odoo.addons.google_gmail.models.mixin_google_gmail import (
    GMAIL,
    GMAIL_TOKEN_REQUEST_TIMEOUT,
)

_logger = logging.getLogger(__name__)


class GoogleGmailController(http.Controller):
    @http.route("/google_gmail/confirm", type="http", auth="user")
    def google_gmail_callback(self, code=None, state=None, error=None, **kwargs):
        """Callback URL during the OAuth process.

        Gmail redirects the user browser to this endpoint with the authorization code.
        We will fetch the refresh token and the access token thanks to this authorization
        code and save those values on the given mail server.
        """
        if error:
            _logger.warning("Google Gmail: an error occurred %s", error)
            return request.render(
                "google_gmail.google_gmail_oauth_error",
                {
                    "error": request.env._(
                        "An error occurred during the authentication process."
                    ),
                    "redirect_url": "/odoo",
                },
            )

        record_sudo = self._get_gmail_record(state)

        try:
            refresh_token, access_token, expiration = (
                record_sudo._get_gmail_refresh_token(code)
            )
        except UserError as e:
            return request.render(
                "google_gmail.google_gmail_oauth_error",
                {
                    "error": str(e),
                    "redirect_url": self._get_redirect_url(record_sudo),
                },
            )

        return self._check_email_and_redirect_to_gmail_record(
            access_token, expiration, refresh_token, record_sudo
        )

    @http.route("/google_gmail/iap_confirm", type="http", auth="user")
    def google_gmail_iap_callback(  # noqa: E8539  inbound: a token an outside service hands over, not one of ours
        self, access_token, refresh_token, expiration, state=None, **kwargs
    ):
        """Receive back the refresh token and access token from IAP.

        The authentication process with IAP is done in 4 steps;
        1. User database make a request to `<IAP>/api/mail_oauth/1/gmail`
        2. User browser is redirected to the URL we received from IAP
        3. User browser is redirected to `<IAP>/api/mail_oauth/1/gmail_callback`
           with the authorization_code
        4. User browser is redirected to `<DB>/google_gmail/iap_confirm`
        """
        record = self._get_gmail_record(state)
        return self._check_email_and_redirect_to_gmail_record(
            access_token, expiration, refresh_token, record
        )

    def _get_gmail_record(self, state):
        """Return the record, as superuser, whose authorization this session
        started with ``state``."""
        record = request.env["mixin.google.gmail"]._oauth2_record_of_state(GMAIL, state)
        if not record:
            _logger.error("Google Gmail: refused a state this session did not start.")
            raise Forbidden
        return record

    def _check_email_and_redirect_to_gmail_record(
        self, access_token, expiration, refresh_token, record
    ):
        # Verify the token information (that the email set on the
        # server is the email used to login on Gmail)
        if record._name == "ir.mail_server" and (
            record.owner_user_id or not request.env.user.has_group("base.group_system")
        ):
            # https://developers.google.com/identity/protocols/oauth2/scopes
            response = request.env["ir.egress"].request(
                "GET",
                "https://www.googleapis.com/oauth2/v2/userinfo",
                purpose="gmail_userinfo",
                params={"access_token": access_token},
                timeout=GMAIL_TOKEN_REQUEST_TIMEOUT,
            )
            if not response.ok:
                _logger.error(
                    "Google Gmail: Could not verify the token information: %s.",
                    response.text,
                )
                raise Forbidden

            response = response.json()

            if not response.get("verified_email") or email_normalize(
                response.get("email")
            ) != email_normalize(record[record._email_field]):
                _logger.error(
                    "Google Gmail: Invalid email address: %r != %s.",
                    response,
                    record[record._email_field],
                )
                return request.render(
                    "google_gmail.google_gmail_oauth_error",
                    {
                        "error": request.env._(
                            "Oops, you're creating an authorization to send from %(email_login)s but your address is %(email_server)s. Make sure your addresses match!",
                            email_login=response.get("email"),
                            email_server=record[record._email_field],
                        ),
                        "redirect_url": self._get_redirect_url(record),
                    },
                )

        record.write(
            {
                "active": True,
                "google_gmail_access_token": access_token,
                "google_gmail_access_token_expiration": expiration,
                "google_gmail_refresh_token": refresh_token,
            }
        )
        return request.redirect(self._get_redirect_url(record))

    def _get_redirect_url(self, record):
        """Return the redirect URL for the given record.

        If the user configured a personal mail server, we redirect him
        to the user preference view. If it's an admin and that he
        configured a standard incoming / outgoing mail server, then we
        redirect it to the mail server form view.
        """
        if (
            record._name != "ir.mail_server"
            or record != request.env.user.outgoing_mail_server_id
        ) and request.env.user.has_group("base.group_system"):
            return f"/odoo/{record._name}/{record.id}"
        return f"/odoo/my-preferences/{request.env.user.id}"
