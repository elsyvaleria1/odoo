import json
import logging
from datetime import timedelta
from typing import Any, Self
from urllib.parse import quote, urlparse

import requests

from odoo import api, fields, models
from odoo.db import get_or_create_row
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.libs import guarded_http, redact
from odoo.libs.breaker import Attempt
from odoo.libs.json import loads as json_loads
from odoo.libs.secret import Secret

from ..tools.api_client import is_private_host
from ..tools.connection_gate import (
    CONNECTION_CONTEXT_KEY,
    BudgetSpent,
    CircuitOpen,
    breaker_for,
    is_failure,
)
from ..tools.exceptions import AuthenticationError

_logger = logging.getLogger(__name__)


def _is_revoked_grant(response) -> bool:
    if response is None or response.status_code not in (400, 401):
        return False
    try:
        return response.json().get("error") == "invalid_grant"
    except ValueError, AttributeError:
        return False


_CIRCUIT_PENDING_KEY = "integration.connection.circuit"

SYNCED_FIELDS = {
    "company_id": "company_id",
    "owner_user_id": "user_id",
    "environment": "environment",
    "sequence": "sequence",
}


class IntegrationConnection(models.Model):
    _name = "integration.connection"
    _description = "Integration Connection"
    _order = "service_id, sequence, id"

    name = fields.Char(
        help="What this connection reaches, for a service whose connections each "
        "belong to one record: the device or the account.",
    )
    service_id = fields.Many2one(
        comodel_name="integration.service",
        index=True,
        required=True,
        ondelete="cascade",
    )
    credential_id = fields.Many2one(
        comodel_name="credential.credential",
        index=True,
        ondelete="cascade",
        help="The secret this connection authenticates with. Empty only for a "
        "service that authenticates with nothing.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        index=True,
        help="Empty: the connection serves every company that has none of its own.",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Personal To",
        index=True,
        help="Set for a personal connection, used only when the service allows them.",
    )
    environment = fields.Selection(
        selection=[
            ("test", "Test/Sandbox"),
            ("staging", "Staging"),
            ("production", "Production"),
        ],
        default="test",
        index=True,
        required=True,
        help="Which of the service's URLs this connection calls. Only connections in "
        "the service's own environment are used.",
    )
    service_environment = fields.Selection(
        related="service_id.environment",
        string="Service Environment",
        readonly=True,
    )
    service_auth_type = fields.Selection(
        related="service_id.auth_type",
        string="Authentication",
        readonly=True,
    )
    base_url = fields.Char(
        string="Base URL",
        help="Overrides the service's URL for this connection, for a service whose "
        "address differs per installation: a device, a bridge, a portal.",
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    synced_from_credential = fields.Boolean(
        readonly=True,
        help="Kept in step with its credential's Outbound Endpoint, company, owner, "
        "environment and priority, for code that still binds credentials that way.",
    )
    res_model = fields.Char(
        string="Serves Model",
        index=True,
        readonly=True,
        help="The model of the record this connection belongs to: a payment "
        "provider, a terminal, a carrier.",
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Serves Record",
        readonly=True,
    )
    breaker_failure_threshold = fields.Integer(
        string="Failures Before Pausing",
        default=5,
        help="Transport errors, timeouts and 5xx answers within the failure window "
        "that pause the connection. A 4xx answer is the provider's reply and does "
        "not count.",
    )
    breaker_failure_window = fields.Integer(
        string="Failure Window (s)",
        default=60,
    )
    breaker_max_cooldown = fields.Integer(
        string="Longest Pause (s)",
        default=300,
        help="A paused connection lets one call through after its pause; each "
        "failed probe doubles the pause up to this.",
    )
    budget_requests = fields.Integer(
        string="Call Budget",
        default=600,
        help="Calls allowed per budget window, shared by every worker. 0 turns the "
        "budget off.",
    )
    budget_window_seconds = fields.Integer(
        string="Budget Window (s)",
        default=60,
    )
    circuit_state = fields.Selection(
        selection=[("closed", "Calling"), ("open", "Paused")],
        default="closed",
        readonly=True,
        help="Paused after repeated failures: calls fail at once instead of "
        "waiting for their timeout, until a probe succeeds.",
    )
    last_success_at = fields.Datetime(readonly=True)
    last_failure_at = fields.Datetime(readonly=True)
    last_error = fields.Char(readonly=True)
    oauth_scope = fields.Char(
        string="OAuth Scope",
        help="The permissions this connection asks for, when they differ from the "
        "service's: a calendar asks for one scope, a mailbox for another, on one "
        "OAuth client.",
    )
    oauth_redirect_uri = fields.Char(
        string="Authorized Through",
        readonly=True,
        help="The redirect URI this connection was last authorized through.",
    )
    needs_reauthorization = fields.Boolean(
        readonly=True,
        help="The provider refused to refresh this connection's grant (revoked, "
        "expired or its client changed): it must be authorized again.",
    )

    _record_unique = models.UniqueIndex(
        "(res_model, res_id) WHERE res_model IS NOT NULL",
        "A record has one connection.",
    )

    @api.depends("name", "service_id", "company_id", "environment", "user_id")
    def _compute_display_name(self):
        for connection in self:
            if connection.name:
                connection.display_name = (
                    f"{connection.service_id.name} · {connection.name}"
                )
                continue
            parts = [
                connection.service_id.name or "",
                connection.company_id.name or self.env._("All companies"),
                dict(self._fields["environment"].selection).get(
                    connection.environment, ""
                ),
            ]
            if connection.user_id:
                parts.append(connection.user_id.name)
            connection.display_name = " · ".join(part for part in parts if part)

    @api.constrains(
        "service_id", "company_id", "environment", "active", "user_id", "credential_id"
    )
    def _check_one_active_connection(self) -> None:
        constrained = self.filtered(
            lambda connection: (
                connection.active
                and not connection.res_model
                and not connection.service_id.allow_multiple_credentials
                and not connection.service_id.per_record_connections
            )
        )
        if not constrained:
            return
        peers = self.search(
            [
                ("service_id", "in", constrained.service_id.ids),
                ("environment", "in", list(set(constrained.mapped("environment")))),
                ("active", "=", True),
                ("res_model", "=", False),
            ]
        )
        ids_by_key: dict[tuple, set[int]] = {}
        for peer in peers:
            key = (
                peer.service_id.id,
                peer.company_id.id,
                peer.environment,
                peer.user_id.id,
            )
            ids_by_key.setdefault(key, set()).add(peer.id)
        for connection in constrained:
            key = (
                connection.service_id.id,
                connection.company_id.id,
                connection.environment,
                connection.user_id.id,
            )
            if ids_by_key.get(key, set()) - {connection.id}:
                raise ValidationError(
                    self.env._(
                        "Only one active connection per service, company and "
                        "environment, and per user for a personal one, unless the "
                        "service allows several."
                    )
                )

    @api.constrains("service_id", "credential_id")
    def _check_credential_serves_this_service(self) -> None:
        for connection in self:
            bound_to = connection.credential_id.endpoint_id
            if bound_to and bound_to != connection.service_id:
                raise ValidationError(
                    self.env._(
                        "Credential %(credential)s is bound to %(bound)s and cannot "
                        "connect %(service)s.",
                        credential=connection.credential_id.display_name,
                        bound=bound_to.display_name,
                        service=connection.service_id.display_name,
                    )
                )

    @api.constrains("service_id", "base_url")
    def _check_tls_disabled_only_off_public_internet(self) -> None:
        for connection in self:
            if connection.service_id.verify_tls or not connection.base_url:
                continue
            host = urlparse(connection.base_url).hostname or ""
            if not host or is_private_host(host):
                continue
            raise ValidationError(
                self.env._(
                    "Service %(service)s calls without verifying TLS, so its "
                    "connections must stay on a private network. '%(host)s' is not "
                    "on one.",
                    service=connection.service_id.display_name,
                    host=host,
                )
            )

    @api.model
    def _resolve(self, service, company=None, user=None, environment=None) -> Self:
        if service.per_record_connections:
            return self.sudo().browse()
        company_id = getattr(company, "id", company) or self.env.company.id
        environment = environment or service.environment
        base = [
            ("service_id", "=", service.id),
            ("environment", "=", environment),
            ("active", "=", True),
            ("res_model", "=", False),
            "|",
            ("credential_id", "=", False),
            ("credential_id.active", "=", True),
        ]
        connections = self.sudo()
        scopes = []
        if service.allow_user_credentials:
            user_id = getattr(user, "id", user) or self.env.uid
            scopes += [
                [("user_id", "=", user_id), ("company_id", "=", company_id)],
                [("user_id", "=", user_id), ("company_id", "=", False)],
            ]
        scopes += [
            [("user_id", "=", False), ("company_id", "=", company_id)],
            [("user_id", "=", False), ("company_id", "=", False)],
        ]
        for scope in scopes:
            found = connections.search([*base, *scope], order="sequence, id", limit=1)
            if found:
                return found
        return connections.browse()

    @api.model
    def _for_credential(self, service, credential) -> Self:
        connections = self.sudo().search(
            [
                ("service_id", "=", service.id),
                ("credential_id", "=", credential.id),
                ("active", "=", True),
            ],
            order="sequence, id",
        )
        in_environment = connections.filtered(
            lambda connection: connection.environment == service.environment
        )
        return (in_environment or connections)[:1]

    def _is_credential_host_allowed(self, host: str) -> bool:
        self.check_singleton()
        own = (urlparse(self.base_url or "").hostname or "").lower()
        if own and (host or "").strip("[]").lower() == own:
            return True
        return self.service_id._is_credential_host_allowed(host)

    def _get_api_client(self, egress_policy: str = "private"):
        self.check_singleton()
        from odoo.addons.integration.tools import (
            get_api_client,
        )

        return get_api_client(
            self.env,
            self.service_id.code,
            company_id=self.company_id.id or None,
            connection_id=self.id,
            egress_policy=egress_policy,
        )

    def _base_url(self) -> str:
        self.check_singleton()
        if self.base_url:
            return self.base_url
        service = self.service_id
        if self.environment == "production":
            return service.endpoint_url
        return service.endpoint_url_test or service.endpoint_url

    def _get_auth_headers(self) -> dict[str, str | Secret]:
        self.check_singleton()
        credential = self.credential_id
        headers: dict[str, str | Secret] = {}
        if not credential:
            return headers
        auth_type = self.service_id.auth_type
        if auth_type == "bearer":
            token = credential._use_secret("integration:bearer", prefer="bearer_token")
            if token:
                headers["Authorization"] = token.prefixed("Bearer ")
        elif auth_type == "api_key":
            api_key = credential._use_secret("integration:api_key", prefer="api_key")
            if api_key:
                headers.update(self.service_id._api_key_headers(api_key))
        elif auth_type == "oauth2":
            access_token = Secret.of(self._oauth2_access_token())
            if access_token:
                headers["Authorization"] = access_token.prefixed("Bearer ")
        if credential.custom_headers:
            try:
                headers.update(json_loads(credential.custom_headers))
            except json.JSONDecodeError as error:
                _logger.warning(
                    "Invalid custom_headers JSON for credential %s: %s at line %s "
                    "column %s",
                    credential.id,
                    error.msg,
                    error.lineno,
                    error.colno,
                )
            except ValueError, TypeError:
                _logger.warning(
                    "The custom_headers of credential %s are not a JSON object",
                    credential.id,
                )
        return headers

    def _check_oauth_authorizer(self) -> None:
        self.check_singleton()
        user = self.env.user
        connection = self
        if connection.service_id.auth_type != "oauth2":
            raise UserError(
                self.env._(
                    "Service '%s' is not configured for OAuth 2.0 authentication",
                    connection.service_id.name,
                )
            )
        if connection.user_id:
            if (
                connection.user_id != user
                or not connection.service_id.allow_user_credentials
            ):
                raise AccessError(
                    self.env._("Only its own user authorizes a personal connection.")
                )
            return
        if connection.res_model:
            record = (
                self.env[connection.res_model]
                .with_user(user)
                .browse(connection.res_id)
                .exists()
            )
            if not record:
                raise UserError(self.env._("This connection's record is gone."))
            if hasattr(record, "_oauth_authorization_allowed"):
                if not record.sudo()._oauth_authorization_allowed(user):
                    raise AccessError(
                        self.env._("You are not allowed to authorize this connection.")
                    )
                return
            record.check_access("write")
            return
        if not user.has_group("credential.group_credential_admin"):
            raise AccessError(
                self.env._("You are not allowed to authorize API credentials.")
            )

    def _oauth_scope(self) -> str:
        self.check_singleton()
        return self.oauth_scope or self.service_id.oauth_scope or ""

    def _oauth_app_connection(self) -> Self:
        self.check_singleton()
        if self.credential_id and not self.user_id and not self.res_model:
            return self
        return self.service_id._oauth_app_connection(self.company_id)

    def _oauth_client(self) -> tuple[str, str | None]:
        self.check_singleton()
        vault = self.sudo()
        client_id = vault.service_id.oauth_client_id or ""
        client_secret = None
        for credential in (
            vault.credential_id,
            vault._oauth_app_connection().credential_id,
        ):
            if not credential:
                continue
            client_id = client_id or credential.oauth_client_id or ""
            client_secret = client_secret or credential._use_secret_payload(
                "integration:oauth_client"
            ).get("oauth_client_secret")
        return client_id, client_secret

    def _oauth_store_tokens(self, tokens: dict[str, Any], redirect_uri: str) -> None:
        self.check_singleton()
        connection = self.sudo()
        expires_in = int(tokens.get("expires_in") or 0)
        values: dict[str, Any] = {
            "oauth_access_token": tokens["access_token"],
            "oauth_token_date_expiration": fields.Datetime.now()
            + timedelta(seconds=expires_in)
            if expires_in
            else False,
        }
        if tokens.get("refresh_token"):
            values["oauth_refresh_token"] = tokens["refresh_token"]
        if connection.credential_id:
            connection.credential_id.write(values)
        else:
            connection.credential_id = connection.env["credential.credential"].create(
                {
                    "name": connection.display_name,
                    "category_id": self.env.ref(
                        "credential.credential_category_oauth2"
                    ).id,
                    "company_id": (connection.company_id or self.env.company).id,
                    "owner_user_id": connection.user_id.id,
                    "environment": connection.environment,
                    **values,
                }
            )
        connection.write(
            {"oauth_redirect_uri": redirect_uri, "needs_reauthorization": False}
        )

    def _oauth2_access_token(self, force: bool = False) -> str | bool:
        self.check_singleton()
        credential = self.credential_id
        tokens = credential._use_secret_payload("integration:oauth")
        expired = bool(credential.oauth_token_date_expiration) and not (
            credential._oauth2_access_token_is_current()
        )
        if not (force or expired) or not tokens.get("oauth_refresh_token"):
            return tokens.get("oauth_access_token") or False
        service = self.service_id
        client_id, client_secret = self._oauth_client()
        try:
            access_token, _seconds = credential._oauth2_refresh(
                service.oauth_token_endpoint,
                client_id,
                client_secret,
                purpose="integration",
                policy="private",
                extra={"scope": self._oauth_scope()}
                if service.oauth_token_sends_scope
                else None,
                force=force,
            )
        except requests.HTTPError as error:
            if _is_revoked_grant(error.response):
                self.needs_reauthorization = True
                self._queue_circuit_values({"needs_reauthorization": True})
                _logger.warning(
                    "OAuth grant of connection %s was refused on refresh", self.id
                )
                raise AuthenticationError(
                    self.env._(
                        "%(connection)s must be authorized again: the provider "
                        "refused its grant.",
                        connection=self.display_name,
                    ),
                    error.response.status_code,
                ) from None
            raise AuthenticationError(
                self.env._(
                    "The provider refused to refresh %(connection)s's access token.",
                    connection=self.display_name,
                ),
                error.response.status_code,
            ) from None
        return access_token

    def _is_oauth_authorized(self) -> bool:
        self.check_singleton()
        return bool(self.credential_id) and not self.needs_reauthorization

    def _oauth_authorize_url(self, return_url: str | None = None) -> str:
        self.check_singleton()
        url = f"/integration/oauth/authorize/{self.id}"
        return f"{url}?return_url={quote(return_url, safe='')}" if return_url else url

    def _forget_oauth_authorization(self) -> None:
        for connection in self.sudo():
            credential = connection.credential_id
            connection.write(
                {
                    "credential_id": False,
                    "oauth_redirect_uri": False,
                    "needs_reauthorization": False,
                }
            )
            credential.unlink()

    def action_oauth_authorize(self) -> dict[str, Any]:
        self.check_singleton()
        return {
            "type": "ir.actions.act_url",
            "url": self._oauth_authorize_url(),
            "target": "self",
        }

    @api.model
    def _find_bound(self, record) -> Self:
        record.check_singleton()
        return self.sudo().search(
            [("res_model", "=", record._name), ("res_id", "=", record.id)], limit=1
        )

    @api.model
    def _bound(self, record, service, scope: str = "") -> Self:
        connection = self._find_bound(record)
        if not connection:
            company = record["company_id"] if "company_id" in record._fields else None
            connection = connection.create(
                {
                    "name": record.display_name,
                    "service_id": service.id,
                    "company_id": company.id if company else False,
                    "environment": service.environment,
                    "res_model": record._name,
                    "res_id": record.id,
                    "oauth_scope": scope or False,
                }
            )
        elif scope and connection.oauth_scope != scope:
            connection.write(
                {
                    "oauth_scope": scope,
                    "needs_reauthorization": bool(connection.credential_id),
                }
            )
        return connection

    @api.model
    def _find_personal(self, service, user=None) -> Self:
        user = user or self.env.user
        elevated = self.sudo()
        service = service.with_env(elevated.env)
        return elevated.search(
            [
                ("service_id", "=", service.id),
                ("user_id", "=", user.id),
                ("environment", "=", service.environment),
                ("res_model", "=", False),
                ("active", "=", True),
            ],
            order="sequence, id",
            limit=1,
        )

    def _adopt_credential(
        self, credential, expires=None, client=None, redirect_path=None
    ) -> None:
        self.check_singleton()
        values = dict(client or {})
        if self.user_id:
            values["owner_user_id"] = self.user_id.id
        if expires and not credential.oauth_token_date_expiration:
            values["oauth_token_date_expiration"] = expires
        credential.write(values)
        base_url = self.env.registry.settings.get(self.env, "web.base.url", "")
        self.write(
            {
                "credential_id": credential.id,
                "oauth_redirect_uri": base_url.rstrip("/")
                + (redirect_path or self.service_id.oauth_redirect_path),
            }
        )

    @api.model
    def _personal(self, service, user=None, scope: str = "") -> Self:
        user = user or self.env.user
        connection = self._find_personal(service, user)
        if not connection:
            connection = connection.create(
                {
                    "name": f"{service.name} · {user.name}",
                    "service_id": service.id,
                    "user_id": user.id,
                    "company_id": user.company_id.id,
                    "environment": service.environment,
                    "oauth_scope": scope or False,
                }
            )
        granted = (connection.oauth_scope or "").split()
        missing = [word for word in scope.split() if word not in granted]
        if missing:
            connection.write(
                {
                    "oauth_scope": " ".join(granted + missing),
                    "needs_reauthorization": bool(connection.credential_id),
                }
            )
        return connection

    @api.model
    def _shared(self, service, company=None) -> Self:
        connections = self.sudo().with_context(active_test=False)
        company_id = getattr(company, "id", company) or self.env.company.id
        domain = [
            ("service_id", "=", service.id),
            ("company_id", "=", company_id),
            ("environment", "=", service.environment),
            ("user_id", "=", False),
            ("res_model", "=", False),
        ]
        connection = connections.search(
            [*domain, ("active", "=", True)], order="sequence, id", limit=1
        )
        if connection:
            return connection
        connection = connections.search(
            [*domain, ("credential_id", "=", False)], order="sequence, id", limit=1
        )
        if connection:
            connection.active = True
            return connection
        connection, _created = get_or_create_row(
            self.env.cr,
            lambda: connections.create(
                {
                    "name": service.name,
                    "service_id": service.id,
                    "company_id": company_id,
                    "environment": service.environment,
                }
            ),
            lambda: connections.search(
                [*domain, ("credential_id", "=", False)], order="sequence, id", limit=1
            ),
            conflict=f"integration.connection shared for {service.code},{company_id}",
        )
        return connection

    def _for_record(self, record, service_code: str, service_name: str, category: str):
        record.check_singleton()
        connections = self.sudo().with_context(active_test=False)
        domain = [("res_model", "=", record._name), ("res_id", "=", record.id)]
        connection = connections.search(domain, limit=1)
        if connection:
            return connection
        service = self.env["integration.service"]._get_per_record_service(
            service_code, service_name, category
        )
        company = record["company_id"] if "company_id" in record._fields else None
        connection, _created = get_or_create_row(
            self.env.cr,
            lambda: connections.create(
                {
                    "name": record.display_name,
                    "service_id": service.id,
                    "company_id": company.id if company else False,
                    "environment": service.environment,
                    "res_model": record._name,
                    "res_id": record.id,
                }
            ),
            lambda: connections.search(domain, limit=1),
            conflict=f"integration.connection for {record._name},{record.id}",
        )
        return connection

    def _egress_session(
        self, purpose: str, *, budgeted: bool = True, **session_options: Any
    ):
        self.check_singleton()
        connection = self.sudo()
        session_options.setdefault("max_seconds", guarded_http.CALL_BUDGET)
        session = (
            self.env["ir.egress"]
            .with_context(**{CONNECTION_CONTEXT_KEY: connection.id})
            .session(purpose=purpose, **session_options)
        )
        send = session.request

        def request(*args, **kwargs):
            url = kwargs.get("url", args[1] if len(args) > 1 else "")
            attempt = connection._admit_call(
                session.get_worst_case_seconds(url, kwargs.get("timeout")),
                budgeted=budgeted,
            )
            try:
                response = send(*args, **kwargs)
            except requests.RequestException as error:
                connection._settle_call(error=error, attempt=attempt)
                raise
            except BaseException:
                connection._release_call(attempt)
                raise
            connection._settle_call(response=response, attempt=attempt)
            return response

        session.request = request
        return session

    def _egress_request(self, method: str, url: str, *, purpose: str, **kwargs: Any):
        session_options = {
            name: kwargs.pop(name)
            for name in (
                "policy",
                "max_bytes",
                "max_seconds",
                "max_redirects",
                "budgeted",
            )
            if name in kwargs
        }
        session = self._egress_session(purpose, **session_options)
        if kwargs.get("stream"):
            return session.request(method, url, **kwargs)
        with session:
            return session.request(method, url, **kwargs)

    def _zeep_transport(self, purpose: str, timeout: float = 30.0):
        from zeep.transports import Transport

        return Transport(  # noqa: E8518 -- zeep sends through the connection's ir.egress session
            session=self._egress_session(purpose),
            timeout=timeout,
            operation_timeout=timeout,
        )

    def _admit_call(
        self, expected_seconds: float | None = None, *, budgeted: bool = True
    ) -> Attempt:
        self.check_singleton()
        attempt = breaker_for(self.env, self).acquire_attempt(expected_seconds)
        if attempt is None:
            raise CircuitOpen(
                self.env._(
                    "%(connection)s is paused after repeated failures; it will be "
                    "tried again shortly.",
                    connection=self.display_name,
                )
            )
        if not budgeted:
            return attempt
        try:
            self._check_call_budget()
        except BaseException:
            self._release_call(attempt)
            raise
        return attempt

    def _release_call(self, attempt: Attempt | None) -> None:
        breaker_for(self.env, self).release(attempt)

    def _get_call_service(self):
        return self.service_id.sudo()

    def _check_call_budget(self) -> None:
        service_spent, connection_spent = self._spend_call_budget()
        service = self._get_call_service()
        if service_spent:
            raise BudgetSpent(
                self.env._(
                    "Rate limit exceeded for service '%(service)s'. Please try again "
                    "later.",
                    service=service.code,
                )
            )
        if connection_spent:
            raise BudgetSpent(
                self.env._(
                    "%(connection)s has used its call budget of %(budget)s calls per "
                    "%(window)s seconds.",
                    connection=self.display_name,
                    budget=self.budget_requests,
                    window=self.budget_window_seconds,
                )
            )

    def _spend_call_budget(self) -> tuple[bool, bool]:
        self.check_singleton()
        service = self._get_call_service()
        with self.env.registry.cursor() as cr:
            cr.use_read_committed()
            env = self.env(cr=cr, su=True)
            service_spent = bool(
                service.rate_limit_enabled
                and not service.with_env(env).check_rate_limit(
                    company_id=self.company_id.id or None
                )
            )
            connection_spent = bool(
                not service_spent
                and self.budget_requests > 0
                and not env["rate.limit.bucket"].consume_for_key(
                    f"integration.connection:{self.id}",
                    subject_model=self._name,
                    subject_id=self.id,
                    capacity=float(self.budget_requests),
                    window_seconds=max(self.budget_window_seconds, 1),
                    company_id=self.company_id.id or None,
                )
            )
        return service_spent, connection_spent

    def _settle_call(
        self,
        response=None,
        error: BaseException | None = None,
        attempt: Attempt | None = None,
    ) -> None:
        self.check_singleton()
        breaker = breaker_for(self.env, self)
        if is_failure(response, error):
            if breaker.record_failure(attempt):
                self._queue_circuit_values(
                    {
                        "circuit_state": "open",
                        "last_failure_at": fields.Datetime.now(),
                        "last_error": redact.mask_text(
                            str(error)
                            if error is not None
                            else f"HTTP {response.status_code}"
                        )[:250],
                    }
                )
            return
        if breaker.record_success(attempt):
            self._queue_circuit_values(
                {"circuit_state": "closed", "last_success_at": fields.Datetime.now()}
            )

    def _queue_circuit_values(self, vals: dict[str, Any]) -> None:
        cr = self.env.cr
        pending = cr.precommit.durable_data.get(_CIRCUIT_PENDING_KEY)
        if pending is None:
            pending = cr.precommit.durable_data[_CIRCUIT_PENDING_KEY] = {}
            registry = self.env.registry
            connections = self.sudo()

            @cr.precommit.add_durable
            def write_circuit_states():
                for connection_id, values in pending.items():
                    connections.browse(connection_id).exists().write(values)

            @cr.postrollback.add
            def keep_circuit_states_of_rolled_back_transaction():
                if not pending:
                    return
                try:
                    with registry.cursor() as state_cr:
                        env = api.Environment(state_cr, api.SUPERUSER_ID, {})
                        for connection_id, values in pending.items():
                            env[self._name].browse(connection_id).exists().write(values)
                except Exception:
                    _logger.warning(
                        "Could not record the state of %s connection(s)",
                        len(pending),
                        exc_info=True,
                    )

        pending.setdefault(self.id, {}).update(vals)

    @api.model
    def _sync_from_credentials(self, credentials) -> None:
        connections = self.sudo().with_context(active_test=False)
        synced_by_credential = connections.search(
            [
                ("credential_id", "in", credentials.ids),
                ("synced_from_credential", "=", True),
            ]
        ).grouped("credential_id")
        stale = connections.browse()
        to_create: list[dict[str, Any]] = []
        for credential in credentials:
            synced = synced_by_credential.get(credential, connections.browse())
            if not credential.endpoint_id:
                stale |= synced
                continue
            vals: dict[str, Any] = {
                "service_id": credential.endpoint_id.id,
                "credential_id": credential.id,
                "active": credential.active,
                "synced_from_credential": True,
                **{
                    target: (
                        credential[source].id
                        if isinstance(credential[source], models.BaseModel)
                        else credential[source]
                    )
                    for source, target in SYNCED_FIELDS.items()
                },
            }
            if synced:
                synced[:1].write(vals)
                stale |= synced[1:]
            else:
                to_create.append(vals)
        stale.unlink()
        if to_create:
            connections.create(to_create)
