import base64
import hashlib
import json
import logging
import secrets
from urllib.parse import urlencode, urlsplit

import requests
import werkzeug.utils

from odoo import http
from odoo.exceptions import AccessDenied, AccessError, UserError
from odoo.http import request
from odoo.tools import (
    consume_session_state,
    issue_session_state,
    register_signed_scope,
)

from ..models.integration_service import (
    OAUTH_CALLBACK_PATH,
    OAUTH_LEGACY_CALLBACK_PATHS,
)

_logger = logging.getLogger(__name__)

_AUTHORIZE_PATH = "/integration/oauth/authorize/<int:connection_id>"
# the credential form's button predates connections: it authorizes the
# connection that credential is bound to
_CREDENTIAL_AUTHORIZE_PATH = "/api_transport/oauth/authorize/<int:credential_id>"
_CALLBACK_PATH = OAUTH_CALLBACK_PATH

_OAUTH_STATE_MAX_AGE_SECONDS = 600
# the verifier stays in the session: the state crosses the browser and the
# provider in the clear, and a code intercepted with its verifier is redeemable
_PKCE_SESSION_KEY = "integration.oauth_pkce_verifier"

OAUTH_STATE_SCOPE = register_signed_scope(
    "integration.oauth_state",
    purpose="the state an OAuth authorization carries through the provider back "
    "to the callback, bound to the database, user, connection and session nonce "
    "that started it",
    lifetime=f"its expiry: the callback refuses a state older than "
    f"{_OAUTH_STATE_MAX_AGE_SECONDS} seconds, or one already consumed",
)


def _privileged(model: str):
    return request.env[model].with_privilege(
        "integration.privilege_oauth_authorization",
        reason="the authorizing user reads the connection they authorize",
    )


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _same_site_path(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme or parts.netloc:
        own = urlsplit(request.httprequest.host_url)
        if (parts.scheme, parts.netloc) != (own.scheme, own.netloc):
            return None
    path = parts.path or "/"
    if not path.startswith("/") or path.startswith("//"):
        return None
    return path + (f"?{parts.query}" if parts.query else "")


class OAuthController(http.Controller):
    @http.route(_AUTHORIZE_PATH, type="http", auth="user", website=False)
    def authorize(self, connection_id, return_url=None, **kw):
        return self._authorize_or_error_page(
            lambda: _privileged("integration.connection").browse(connection_id),
            return_url,
        )

    @http.route(_CREDENTIAL_AUTHORIZE_PATH, type="http", auth="user", website=False)
    def authorize_credential(self, credential_id, return_url=None, **kw):
        def connection():
            credential = _privileged("credential.credential").browse(credential_id)
            if not credential.exists():
                raise UserError(
                    request.env._("Credential not found (ID: %s)") % credential_id
                )
            if not credential.active:
                raise UserError(request.env._("Credential is inactive"))
            found = request.env["integration.connection"]._for_credential(
                credential.endpoint_id, credential
            )
            if not found:
                raise UserError(
                    request.env._("Credential %s is bound to no service.")
                    % credential.display_name
                )
            return found

        return self._authorize_or_error_page(connection, return_url)

    def _authorize_or_error_page(self, get_connection, return_url):
        try:
            connection = get_connection()
            if not connection.exists():
                raise UserError(request.env._("Connection not found"))
            connection._check_oauth_authorizer()
            return self._redirect_to_provider(connection, return_url)
        except AccessDenied, AccessError:
            _logger.warning(
                "Unauthorized OAuth authorize attempt by user %s",
                request.env.user.login,
            )
            return request.env["ir.http"]._serve_error_page(
                request.env._("OAuth Authorization Error"),
                request.env._("You are not allowed to authorize this connection."),
                status=403,
            )
        except UserError as e:
            return request.env["ir.http"]._serve_error_page(
                request.env._("OAuth Authorization Error"),
                str(e),
                status=400,
            )
        except Exception:
            _logger.exception("OAuth authorization failed")
            return request.env["ir.http"]._serve_error_page(
                request.env._("OAuth Authorization Error"),
                request.env._(
                    "An unexpected error occurred. Please contact your administrator."
                ),
                status=500,
            )

    def _redirect_to_provider(self, connection, return_url):
        service = connection.service_id
        client_id, _secret = connection._oauth_client()
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
                request.env._("OAuth Authorization URL not configured for service '%s'")
                % service.name
            )
        if not service.oauth_token_endpoint:
            raise UserError(
                request.env._("OAuth Token URL not configured for service '%s'")
                % service.name
            )
        redirect_uri = self._get_redirect_uri(connection)
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            **service._oauth_authorize_extra(),
        }
        if scope := connection._oauth_scope():
            params["scope"] = scope
        if service.oauth_use_pkce:
            verifier, challenge = _pkce_pair()
            request.session[_PKCE_SESSION_KEY] = verifier
            params["code_challenge"] = challenge
            params["code_challenge_method"] = "S256"
        else:
            request.session.pop(_PKCE_SESSION_KEY, None)
        params["state"] = self._get_oauth_state(
            connection.id, redirect_uri, _same_site_path(return_url)
        )
        _logger.info(
            "OAuth authorization initiated: connection_id=%s, service=%s, user=%s",
            connection.id,
            service.code,
            request.env.user.login,
        )
        return werkzeug.utils.redirect(
            f"{service.oauth_auth_endpoint}?{urlencode(params)}", 303
        )

    # csrf=False: the OAuth state is HMAC-signed and verified in the body
    @http.route(
        [OAUTH_CALLBACK_PATH, *OAUTH_LEGACY_CALLBACK_PATHS],
        type="http",
        auth="user",
        website=False,
        csrf=False,
    )
    def callback(self, code=None, state=None, error=None, error_description=None, **kw):
        return self._handle_callback(code, state, error, error_description)

    def _handle_callback(self, code, state, error, error_description):
        verifier = request.session.pop(_PKCE_SESSION_KEY, None)
        try:
            if error:
                _logger.warning(
                    "OAuth authorization denied: %s", error_description or error
                )
                return request.env["ir.http"]._serve_error_page(
                    request.env._("Authorization Denied"),
                    request.env._("OAuth authorization was denied: %s")
                    % (error_description or error),
                    status=403,
                )
            if not state:
                raise UserError(request.env._("Missing state parameter"))
            claims = consume_session_state(
                request.env, OAUTH_STATE_SCOPE, request.session, state
            )
            if claims is None:
                raise AccessDenied(
                    request.env._(
                        "The authorization state is invalid, expired or already "
                        "used. Please start the authorization again."
                    )
                )
            connection = (
                _privileged("integration.connection")
                .browse(claims.get("connection_id"))
                .exists()
            )
            if not connection:
                raise UserError(request.env._("Connection not found"))
            connection._check_oauth_authorizer()
            if not code:
                raise UserError(request.env._("Missing authorization code"))
            redirect_uri = claims["redirect_uri"]
            tokens = self._exchange_code_for_tokens(
                connection,
                code,
                redirect_uri,
                code_verifier=verifier
                if connection.service_id.oauth_use_pkce
                else None,
            )
            # a record that refuses the account it was authorized with keeps
            # none of the tokens
            with request.env.cr.savepoint():
                connection._oauth_store_tokens(tokens, redirect_uri)
                if connection.res_model:
                    # the authorizer was checked: the record hears of it whatever
                    # the user may write of it
                    record = (
                        request.env[connection.res_model]
                        .sudo()
                        .browse(connection.res_id)
                    )
                    if hasattr(record, "_on_oauth_authorized"):
                        record._on_oauth_authorized(connection, tokens)
            _logger.info(
                "OAuth tokens obtained successfully: connection_id=%s, service=%s",
                connection.id,
                connection.service_id.code,
            )
            return werkzeug.utils.redirect(
                claims.get("return_url") or self._default_return(connection), 303
            )
        except AccessDenied as e:
            _logger.error("OAuth callback access denied: %s", e)
            return request.env["ir.http"]._serve_error_page(
                request.env._("Access Denied"),
                str(e),
                status=403,
            )
        except AccessError:
            _logger.error("OAuth callback by a user who may not authorize it")
            return request.env["ir.http"]._serve_error_page(
                request.env._("Access Denied"),
                request.env._("You are not allowed to authorize this connection."),
                status=403,
            )
        except UserError as e:
            _logger.warning("OAuth callback user error: %s", e)
            return request.env["ir.http"]._serve_error_page(
                request.env._("OAuth Error"),
                str(e),
                status=400,
            )
        except Exception as e:
            _logger.exception("OAuth callback failed")
            return request.env["ir.http"]._serve_error_page(
                request.env._("OAuth Error"),
                request.env._("Token exchange failed: %s") % str(e),
                status=500,
            )

    def _get_oauth_state(self, connection_id, redirect_uri="", return_url=None):
        return issue_session_state(
            request.env,
            OAUTH_STATE_SCOPE,
            request.session,
            {
                "connection_id": connection_id,
                "redirect_uri": redirect_uri,
                "return_url": return_url,
            },
            max_age_seconds=_OAUTH_STATE_MAX_AGE_SECONDS,
        )

    def _get_redirect_uri(self, connection):
        """The service's callback, or the one this connection was last
        authorized through: its provider's console lists that one for sure."""
        service = connection.service_id
        path = urlsplit(connection.oauth_redirect_uri or "").path
        if path not in service._oauth_callback_paths():
            path = service.oauth_redirect_path or OAUTH_CALLBACK_PATH
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
        return f"{base_url}{path}"

    def _exchange_code_for_tokens(
        self, connection, code, redirect_uri, code_verifier=None
    ):
        service = connection.service_id
        client_id, client_secret = connection._oauth_client()
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
        }
        if client_secret:
            token_data["client_secret"] = client_secret
        if code_verifier:
            token_data["code_verifier"] = code_verifier
        if service.oauth_token_sends_scope and (scope := connection._oauth_scope()):
            token_data["scope"] = scope
        try:
            with connection.env["ir.egress"].session(
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
            raise UserError(
                request.env._("Token exchange failed: %s")
                % self._parse_token_error(e.response)
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

    def _default_return(self, connection):
        if (
            connection.credential_id
            and not connection.user_id
            and not connection.res_model
        ):
            credential_id = connection.credential_id.id
            return f"/web#id={credential_id}&model=credential.credential&view_type=form"
        return f"/web#id={connection.id}&model=integration.connection&view_type=form"
