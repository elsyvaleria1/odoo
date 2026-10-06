import logging
import time
from urllib.parse import urlencode as url_encode

import requests

from odoo import api, fields, models, release
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.libs.web import urljoin as url_join
from odoo.tools import consume_session_state, email_normalize, issue_session_state

from odoo.addons.mail_oauth2.tools import get_iap_error_message

OAUTH2_TOKEN_REQUEST_TIMEOUT = 5

OAUTH2_TOKEN_VALIDITY_THRESHOLD = OAUTH2_TOKEN_REQUEST_TIMEOUT + 5

OAUTH2_STATE_MAX_AGE_SECONDS = 1800

_logger = logging.getLogger(__name__)

_UNSET = object()


class MixinOauth2MailProvider(models.AbstractModel):
    _name = "mixin.oauth2.mail.provider"

    _description = "OAuth2 Mail Provider Mixin"

    active = fields.Boolean(default=True)

    oauth2_credential_id = fields.Many2one(
        comodel_name="credential.credential",
        string="OAuth2 Credential",
        copy=False,
        ondelete="restrict",
        groups="base.group_system",
        help="Holds this record's OAuth tokens.",
    )

    def _oauth2_stored_tokens(self) -> tuple:
        self.check_singleton()
        credential = self.oauth2_credential_id.sudo()
        tokens = (
            credential._use_secret_payload("mail_oauth2:tokens") if credential else {}
        )
        return (
            tokens.get("oauth_access_token") or False,
            tokens.get("oauth_refresh_token") or False,
        )

    def _oauth2_store_tokens(self, access_token=_UNSET, refresh_token=_UNSET) -> None:
        self.check_singleton()
        values = {}
        if access_token is not _UNSET:
            values["oauth_access_token"] = access_token or False
        if refresh_token is not _UNSET:
            values["oauth_refresh_token"] = refresh_token or False

        credential = self.oauth2_credential_id.sudo()
        if credential:
            if any(values.values()):
                credential.write(values)
            else:
                self.oauth2_credential_id = False
                credential.unlink()
            return
        if not any(values.values()):
            return
        self.oauth2_credential_id = (
            self.env["credential.credential"]
            .sudo()
            .create(
                {
                    "name": self.env._(
                        "%(model)s: %(record)s",
                        model=self._description,
                        record=self.display_name,
                    ),
                    "category_id": self.env.ref(
                        "credential.credential_category_oauth2"
                    ).id,
                    **values,
                }
            )
            .id
        )

    def _oauth2_credentials(self, provider) -> tuple:
        Config = self.env["ir.config_parameter"].sudo()
        return (
            Config.get_param(provider.field("client_id")),
            self.env["credential.credential"]._get_system_secret(
                provider.field("client_secret")
            ),
        )

    def _oauth2_redirect_uri(self, provider):
        return url_join(self.get_base_url(), f"/{provider.route}/confirm")

    def _oauth2_iap_endpoint(self, provider):
        return self.env.registry.settings.get(
            self.env, provider.iap_endpoint_param, provider.iap_endpoint_default
        )

    def _oauth2_authorize_uri(self, provider, client_id, state):
        self.check_singleton()
        return "%s?%s" % (
            provider.resolve(provider.authorize_url, self),
            url_encode(
                {
                    "client_id": client_id,
                    "response_type": "code",
                    "redirect_uri": self._oauth2_redirect_uri(provider),
                    "scope": provider.resolve(provider.scope, self),
                    **provider.authorize_extra_params,
                    "state": state,
                }
            ),
        )

    def _oauth2_open_uri(self, provider) -> dict:
        self.check_singleton()

        if not self.env.is_admin():
            raise AccessError(
                self.env._(
                    "Only the administrator can link a mail server to %s.",
                    provider.label,
                )
            )

        if not email_normalize(self[self._email_field]):
            raise UserError(self.env._("Please enter a valid email address."))

        client_id, client_secret = self._oauth2_credentials(provider)
        state = self._oauth2_issue_state(provider)
        if client_id and client_secret:
            uri = self._oauth2_authorize_uri(provider, client_id, state)
        else:
            uri = self._oauth2_iap_authorize_uri(provider, state)

        if not uri:
            raise UserError(
                self.env._("Please configure your %s credentials.", provider.label)
            )

        return {
            "type": "ir.actions.act_url",
            "url": uri,
            "target": "self",
        }

    def _oauth2_issue_state(self, provider):
        self.check_singleton()
        return issue_session_state(
            self.env,
            provider.csrf_scope,
            request.session,
            {"model": self._name, "id": self.id},
            max_age_seconds=OAUTH2_STATE_MAX_AGE_SECONDS,
        )

    @api.model
    def _oauth2_record_of_state(self, provider, state):
        """The record, as superuser, that the session started the authorization
        of ``state`` from: one of this mixin's models, or None."""
        claims = consume_session_state(
            self.env, provider.csrf_scope, request.session, state
        )
        if claims is None:
            return None
        model_name = claims.get("model")
        if model_name not in self.env or not isinstance(
            self.env[model_name], self.env.registry[self._name]
        ):
            return None
        return self.env[model_name].browse(claims.get("id")).exists().sudo() or None

    def _oauth2_iap_authorize_uri(self, provider, state):
        if release.version_info[-1] != "e":
            raise UserError(
                self.env._("Please configure your %s credentials.", provider.label)
            )

        db_uuid = self.env.registry.settings.get(self.env, "database.uuid", False)
        callback_params = url_encode({"state": state})
        callback_url = url_join(
            self.get_base_url(), f"/{provider.route}/iap_confirm?{callback_params}"
        )

        try:
            response = self.env["ir.egress"].request(
                "GET",
                url_join(
                    self._oauth2_iap_endpoint(provider),
                    f"/api/mail_oauth/1/{provider.iap_service}",
                ),
                purpose="mail_oauth2",
                policy="private",
                params={"db_uuid": db_uuid, "callback_url": callback_url},
                timeout=OAUTH2_TOKEN_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            _logger.error("Can not contact IAP: %s.", e)
            raise UserError(
                self.env._(
                    "Oops, we could not authenticate you. Please try again later."
                )
            ) from e

        response = response.json()
        if "error" in response:
            self._raise_iap_error(response["error"])

        return response["url"]

    def _oauth2_get_refresh_token(self, provider, authorization_code) -> tuple:
        response = self._oauth2_get_token(
            provider, "authorization_code", code=authorization_code
        )
        return (
            response["refresh_token"],
            response["access_token"],
            int(time.time()) + int(response["expires_in"]),
        )

    def _oauth2_refresh_access_token(self, provider) -> tuple:
        self.check_singleton()
        client_id, client_secret = self._oauth2_credentials(provider)
        extra = {"redirect_uri": self._oauth2_redirect_uri(provider)}
        if provider.token_sends_scope:
            extra["scope"] = provider.resolve(provider.scope, self)
        try:
            access_token, seconds = self.oauth2_credential_id._oauth2_refresh(
                provider.resolve(provider.token_url, self),
                client_id,
                client_secret,
                purpose="mail_oauth2",
                policy="private",
                timeout=OAUTH2_TOKEN_REQUEST_TIMEOUT,
                extra=extra,
            )
        except requests.HTTPError as error:
            raise UserError(
                self._oauth2_token_error(provider, error.response)
            ) from error
        self.invalidate_recordset()
        return access_token, int(time.time()) + seconds

    def _oauth2_get_token(self, provider, grant_type, **values):
        client_id, client_secret = self._oauth2_credentials(provider)
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": grant_type,
            "redirect_uri": self._oauth2_redirect_uri(provider),
            **values,
        }
        if provider.token_sends_scope:
            data["scope"] = provider.resolve(provider.scope, self)

        response = self.env["ir.egress"].request(
            "POST",
            provider.resolve(provider.token_url, self),
            purpose="mail_oauth2",
            policy="private",
            data=data,
            timeout=OAUTH2_TOKEN_REQUEST_TIMEOUT,
        )

        if not response.ok:
            raise UserError(self._oauth2_token_error(provider, response))

        return response.json()

    def _oauth2_token_error(self, provider, response) -> str:
        if not provider.token_error_detail:
            return self.env._("An error occurred when fetching the access token.")
        try:
            detail = response.json()["error_description"]
        except ValueError, KeyError, TypeError:
            detail = self.env._("Unknown error.")
        return self.env._(
            "An error occurred when fetching the access token. %s", detail
        )

    def _oauth2_get_access_token_iap(self, provider, refresh_token):
        db_uuid = self.env.registry.settings.get(self.env, "database.uuid", False)

        response = self.env["ir.egress"].request(
            "GET",
            url_join(
                self._oauth2_iap_endpoint(provider),
                f"/api/mail_oauth/1/{provider.iap_service}_access_token",
            ),
            purpose="mail_oauth2",
            policy="private",
            params={"refresh_token": refresh_token, "db_uuid": db_uuid},
            timeout=OAUTH2_TOKEN_REQUEST_TIMEOUT,
        )

        if not response.ok:
            _logger.error("Can not contact IAP: %s.", response.text)
            raise UserError(
                self.env._(
                    "Oops, we could not authenticate you. Please try again later."
                )
            )

        response = response.json()
        if "error" in response:
            self._raise_iap_error(response["error"])

        return response

    def _raise_iap_error(self, error) -> None:
        raise UserError(get_iap_error_message(self.env, error))

    def _oauth2_generate_string(self, provider, login, renew) -> str:
        self.check_singleton()
        now_timestamp = int(time.time())
        expiration = self[provider.field("access_token_expiration")]

        if (
            not self[provider.field("access_token")]
            or not expiration
            or expiration - OAUTH2_TOKEN_VALIDITY_THRESHOLD < now_timestamp
        ):
            renew()
            _logger.info(
                "%s: fetch new access token. It expires in %i minutes",
                provider.label,
                (self[provider.field("access_token_expiration")] - now_timestamp) // 60,
            )
        else:
            _logger.info(
                "%s: reuse existing access token. It expires in %i minutes",
                provider.label,
                (expiration - now_timestamp) // 60,
            )

        return "user=%s\1auth=Bearer %s\1\1" % (
            login,
            self[provider.field("access_token")],
        )
