import secrets
import uuid
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from .integration_github_pull import (
    _check_run_vals,
    _status_vals,
    _workflow_run_vals,
)
from odoo.addons.integration.tools.admission import Admission

_debug = DebugLog(__name__)

WEBHOOK_ROUTE = "/integration_github/webhook/"
DELIVERY_HEADER = "X-GitHub-Delivery"
EVENT_HEADER = "X-GitHub-Event"


class IntegrationGithubWebhook(models.Model):
    _name = "integration.github.webhook"
    _description = "GitHub Webhook"
    _inherit = ["mixin.inbound.gate", "mixin.mail.thread"]
    _order = "name, id"

    name = fields.Char(
        required=True,
    )
    active = fields.Boolean(
        default=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    hook_uuid = fields.Char(
        string="Hook ID",
        default=lambda self: uuid.uuid4().hex,
        index=True,
        copy=False,
        readonly=True,
        required=True,
    )
    url = fields.Char(
        string="Payload URL",
        compute="_compute_url",
        help="Paste it into the GitHub App's or the repository's webhook settings, "
        "with content type application/json.",
    )
    auth_type = fields.Selection(
        default="hmac_sha256",
    )

    _hook_uuid_uniq = models.Constraint(
        "UNIQUE(hook_uuid)",
        "Two webhooks cannot share an address.",
    )

    @api.depends("hook_uuid")
    def _compute_url(self) -> None:
        for hook in self:
            hook.url = f"{hook.get_base_url()}{WEBHOOK_ROUTE}{hook.hook_uuid}"

    def action_issue_secret(self) -> dict[str, Any]:
        self.check_singleton().check_access("write")
        Credential = self.env["credential.credential"]
        if not Credential._is_encryption_key_configured():
            raise UserError(
                self.env._(
                    "A webhook secret is stored encrypted, and this server has no "
                    "ODOO_API_ENCRYPTION_KEY."
                )
            )
        secret = secrets.token_urlsafe(32)
        if self.credential_id:
            self.credential_id.credential_value = secret
        else:
            self.credential_id = Credential.create(
                {
                    "name": self.env._(
                        "GitHub webhook secret: %(hook)s [#%(id)s]",
                        hook=self.name,
                        id=self.id,
                    ),
                    "category_id": self.env.ref(
                        "credential.credential_category_custom"
                    ).id,
                    "company_id": self.company_id.id,
                    "credential_value": secret,
                }
            )
        self.auth_type = "hmac_sha256"
        self.message_post(body=self.env._("A new signing secret was issued."))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Webhook secret for %(hook)s", hook=self.name),
                "message": self.env._(
                    "%(secret)s\n\nIt is shown once: paste it into GitHub's webhook "
                    "secret now. Deliveries signed with any earlier secret are refused.",
                    secret=secret,
                ),
                "type": "warning",
                "sticky": True,
            },
        }

    def _inbound_event_id(
        self, admission: Admission, event_type: str | None
    ) -> str | None:
        return request.httprequest.headers.get(
            DELIVERY_HEADER
        ) or super()._inbound_event_id(admission, event_type)

    def _dispatch(self, event: str, payload: dict[str, Any]) -> str:
        self.check_singleton()
        handler = (
            getattr(self, f"_github_{event}", None) if event.isidentifier() else None
        )
        if handler is None:
            _debug.logic("webhook.ignored", event=event)
            return "ignored"
        repository = payload.get("repository", {}).get("full_name")
        if not repository and event != "ping":
            return "ignored"
        outcome = handler(repository, payload)
        _debug.logic("webhook.dispatched", event=event, outcome=outcome)
        return outcome

    def _github_ping(self, repository: str | None, payload: dict[str, Any]) -> str:
        return "pong"

    def _github_pull_request(self, repository: str, payload: dict[str, Any]) -> str:
        self.env["integration.github.pull"]._upsert_from_github(
            repository, payload["pull_request"]
        )
        return "pull_request"

    def _github_check_run(self, repository: str, payload: dict[str, Any]) -> str:
        run = payload["check_run"]
        self._record_check(repository, f"check_run:{run['id']}", _check_run_vals(run))
        return "check"

    def _github_workflow_run(self, repository: str, payload: dict[str, Any]) -> str:
        run = payload["workflow_run"]
        self._record_check(
            repository, f"workflow_run:{run['id']}", _workflow_run_vals(run)
        )
        return "check"

    def _github_status(self, repository: str, payload: dict[str, Any]) -> str:
        self._record_check(
            repository,
            f"status:{payload['sha']}:{payload.get('context')}",
            _status_vals(payload["sha"], payload),
        )
        return "check"

    def _record_check(
        self, repository: str, external_ref: str, vals: dict[str, Any]
    ) -> None:
        self.env["integration.github.check"]._record(repository, external_ref, vals)
        self.env["integration.github.pull"]._checks_moved(repository, vals["head_sha"])
