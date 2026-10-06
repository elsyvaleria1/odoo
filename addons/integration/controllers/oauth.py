import json
import logging
from datetime import timedelta
from urllib.parse import urlencode

import requests
import werkzeug.utils

from odoo import fields, http
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request
from odoo.tools import (
    consume_session_state,
    issue_session_state,
    register_signed_scope,
)

_logger = logging.getLogger(__name__)

_AUTHORIZE_PATH = "/api_transport/oauth/authorize/<int:credential_id>"
_CALLBACK_PATH = "/api_transport/oauth/callback"
_CALLBACK_PATH_LEGACY = "/api_gateway/oauth/callback"
_CALLBACK_PATH_REGISTERED_WITH_PROVIDERS = _CALLBACK_PATH_LEGACY

_OAUTH_STATE_MAX_AGE_SECONDS = 600

OAUTH_STATE_SCOPE = register_signed_scope(
    "integration.oauth_state",
    purpose="the state an OAuth authorization carries through the provider back "
    "to the callback, bound to the database, user, credential and session nonce "
    "that started it",
    lifetime=f"its expiry: the callback refuses a state older than "
    f"{_OAUTH_STATE_MAX_AGE_SECONDS} seconds, or one already consumed",
)


class OAuthController(http.Controller):
    @http.route(
        _AUTHORIZE_PATH,
        type="http",
        auth="user",
        website=False,
    )
    def authorize(self, credential_id, **kw):
        try:
            if not request.env.user.has_group("credential.group_credential_admin"):
                _logger.warning(
                    "Unauthorized OAuth authorize attempt by user %s "
                    "(credential_id=%s)",
                    request.env.user.login,
                    credential_id,
                )
                raise AccessDenied(
                    request.env._("You are not allowed to authorize API credentials.")
                )

            credential = request.env["credential.credential"].browse(credential_id)

            if not credential.exists():
                raise UserError(
                    request.env._("Credential not found (ID: %s)") % credential_id
                )

            if not credential.active:
                raise UserError(request.env._("Credential is inactive"))

            service = credential.endpoint_id

            if not service.auth_type == "oauth2":
                raise UserError(
                    request.env._(
                        "Service '%s' is not configured for OAuth 2.0 authentication"
                    )
                    % service.name
                )

            client_id = credential._oauth_client_id()
            if not client_id:
                raise UserError(
                    request.env._(
                        "OAuth Client ID not configured for service '%(service)s'. "
                        "Set it on the service, or on the credential itself.",
                        service=service.name,
                    )
                )

            if not service.oauth_auth_endpoint:
                raise UserError(
                    request.env._(
                        "OAuth Authorization URL not configured for service '%s'"
                    )
                    % service.name
                )

            if not service.oauth_token_endpoint:
                raise UserError(
                    request.env._("OAuth Token URL not configured for service '%s'")
                    % service.name
                )

            state = self._get_oauth_state(credential_id)

            redirect_uri = self._get_redirect_uri()

            params = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
            }

            if service.oauth_scope:
                params["scope"] = service.oauth_scope

            auth_url = f"{service.oauth_auth_endpoint}?{urlencode(params)}"

            _logger.info(
                "OAuth authorization initiated: credential_id=%s, service=%s, user=%s",
                credential_id,
                service.code,
                request.env.user.login,
            )

            return werkzeug.utils.redirect(auth_url, 303)

        except AccessDenied as e:
            return request.env["ir.http"]._serve_error_page(
                request.env._("Access Denied"),
                str(e),
            )

        except UserError as e:
            return request.env["ir.http"]._serve_error_page(
                request.env._("OAuth Authorization Error"),
                str(e),
            )

        except Exception:
            _logger.exception("OAuth authorization failed")
            return request.env["ir.http"]._serve_error_page(
                request.env._("OAuth Authorization Error"),
                request.env._(
                    "An unexpected error occurred. Please contact your administrator."
                ),
            )

    # csrf=False: the OAuth state is HMAC-signed and verified in the body
    @http.route(
        [_CALLBACK_PATH, _CALLBACK_PATH_LEGACY],
        type="http",
        auth="user",
        website=False,
        csrf=False,
    )
    def callback(self, code=None, state=None, error=None, error_description=None, **kw):
        try:
            if not request.env.user.has_group("credential.group_credential_admin"):
                _logger.warning(
                    "Unauthorized OAuth callback attempt by user %s",
                    request.env.user.login,
                )
                raise AccessDenied(
                    request.env._(
                        "You are not allowed to complete API credential authorization."
                    )
                )

            if error:
                error_msg = error_description or error
                _logger.warning("OAuth authorization denied: %s", error_msg)
                return request.env["ir.http"]._serve_error_page(
                    request.env._("Authorization Denied"),
                    request.env._("OAuth authorization was denied: %s") % error_msg,
                )

            if not state:
                raise UserError(request.env._("Missing state parameter"))

            state_data = consume_session_state(
                request.env, OAUTH_STATE_SCOPE, request.session, state
            )
            if state_data is None:
                raise AccessDenied(
                    request.env._(
                        "The authorization state is invalid, expired or already "
                        "used. Please start the authorization again."
                    )
                )

            credential_id = state_data.get("credential_id")
            if not credential_id:
                raise UserError(request.env._("Missing credential_id in state"))

            if not code:
                raise UserError(request.env._("Missing authorization code"))

            credential = (
                request.env["credential.credential"].sudo().browse(credential_id)
            )

            if not credential.exists():
                raise UserError(request.env._("Credential not found"))

            tokens = self._exchange_code_for_tokens(credential, code)

            vals = {
                "oauth_access_token": tokens.get("access_token"),
                "oauth_refresh_token": tokens.get("refresh_token"),
            }

            if tokens.get("expires_in"):
                date_expiration = fields.Datetime.now() + timedelta(
                    seconds=int(tokens["expires_in"])
                )
                vals["oauth_token_date_expiration"] = date_expiration

            credential.write(vals)

            _logger.info(
                "OAuth tokens obtained successfully: credential_id=%s, service=%s",
                credential.id,
                credential.endpoint_id.code,
            )

            return self._redirect_to_credential(credential_id)

        except AccessDenied as e:
            _logger.error("OAuth callback access denied: %s", e)
            return request.env["ir.http"]._serve_error_page(
                request.env._("Access Denied"),
                str(e),
            )

        except UserError as e:
            _logger.warning("OAuth callback user error: %s", e)
            return request.env["ir.http"]._serve_error_page(
                request.env._("OAuth Error"),
                str(e),
            )

        except Exception as e:
            _logger.exception("OAuth callback failed")
            return request.env["ir.http"]._serve_error_page(
                request.env._("OAuth Error"),
                request.env._("Token exchange failed: %s") % str(e),
            )

    def _get_redirect_uri(self):
        base_url = request.env.registry.settings.get(
            request.env, "web.base.url", ""
        ).rstrip("/")
        if not base_url:
            raise UserError(
                request.env._(
                    "OAuth requires the 'web.base.url' system parameter to be "
                    "configured. Set it in Settings → Technical → System "
                    "Parameters before using OAuth.",
                ),
            )
        return f"{base_url}{_CALLBACK_PATH_REGISTERED_WITH_PROVIDERS}"

    def _get_oauth_state(self, credential_id):
        return issue_session_state(
            request.env,
            OAUTH_STATE_SCOPE,
            request.session,
            {"credential_id": credential_id},
            max_age_seconds=_OAUTH_STATE_MAX_AGE_SECONDS,
        )

    def _exchange_code_for_tokens(self, credential, code):
        service = credential.endpoint_id

        redirect_uri = self._get_redirect_uri()

        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": credential._oauth_client_id(),
            "redirect_uri": redirect_uri,
        }

        client_secret = credential._use_secret_payload(
            "integration:oauth_exchange"
        ).get("oauth_client_secret")
        if client_secret:
            token_data["client_secret"] = client_secret

        try:
            with credential.env["ir.egress"].session(
                purpose="oauth_token", policy="private"
            ) as session:
                response = session.post(
                    service.oauth_token_endpoint,
                    data=token_data,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    timeout=30,
                )

            response.raise_for_status()

            tokens = response.json()

            if "access_token" not in tokens:
                raise UserError(request.env._("Missing access_token in response"))

            return tokens

        except requests.exceptions.HTTPError as e:
            error_details = self._parse_token_error(e.response)
            raise UserError(
                request.env._("Token exchange failed: %s") % error_details
            ) from e

        except requests.exceptions.RequestException as e:
            raise UserError(
                request.env._("Token exchange request failed: %s") % str(e)
            ) from e

        except (json.JSONDecodeError, ValueError) as e:
            raise UserError(
                request.env._("Invalid token response format: %s") % str(e)
            ) from e

    def _parse_token_error(self, response):
        try:
            error_data = response.json()
            error = error_data.get("error", "unknown_error")
            error_description = error_data.get("error_description", error)
            return f"{error}: {error_description}"
        except ValueError, AttributeError:
            return f"HTTP {response.status_code}: {response.text[:200]}"

    def _redirect_to_credential(self, credential_id):
        url = f"/web#id={credential_id}&model=credential.credential&view_type=form"
        return werkzeug.utils.redirect(url, 303)
