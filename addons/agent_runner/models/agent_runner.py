import secrets
from datetime import timedelta
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

# A runner that has not called in this long is shown offline; its leases expire
# on their own clock.
_ONLINE_WINDOW = timedelta(minutes=2)
# Polling does not rewrite the row each time it calls.
_SEEN_RESOLUTION = timedelta(seconds=30)


class AgentRunner(models.Model):
    _name = "agent.runner"
    _description = "Agent Runner"
    _inherit = ["mixin.inbound.gate", "mixin.mail.thread"]
    _order = "name, id"

    name = fields.Char(
        required=True,
        tracking=True,
    )
    active = fields.Boolean(
        default=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        help="The company its calls are recorded under. The runs it claims may "
        "belong to any company it is allowed to serve.",
    )
    capability_ids = fields.Many2many(
        comodel_name="agent.capability",
        string="Capabilities",
        help="The kinds of work this runner may claim.",
    )
    concurrency = fields.Integer(
        default=1,
        help="How many runs it may hold at once.",
    )
    date_last_seen = fields.Datetime(
        string="Last Seen",
        readonly=True,
    )
    is_online = fields.Boolean(
        string="Online",
        compute="_compute_is_online",
    )
    run_ids = fields.One2many(
        comodel_name="agent.run",
        inverse_name="runner_id",
        string="Runs",
        readonly=True,
    )

    _concurrency_positive = models.Constraint(
        "CHECK(concurrency > 0)",
        "A runner holds at least one run at a time.",
    )

    @api.depends("date_last_seen")
    def _compute_is_online(self) -> None:
        horizon = fields.Datetime.now() - _ONLINE_WINDOW
        for runner in self:
            runner.is_online = bool(
                runner.date_last_seen and runner.date_last_seen >= horizon
            )

    def action_issue_token(self) -> dict[str, Any]:
        """A new bearer token, shown once; the one before stops working."""
        self.check_singleton().check_access("write")
        Credential = self.env["credential.credential"]
        if not Credential._is_encryption_key_configured():
            raise UserError(
                self.env._(
                    "A runner token is stored encrypted, and this server has no "
                    "ODOO_API_ENCRYPTION_KEY."
                )
            )
        token = secrets.token_urlsafe(32)
        bearer = self.env.ref("credential.credential_category_bearer_token")
        if self.credential_id.category_id == bearer:
            self.credential_id.credential_value = token
        else:
            self.credential_id = Credential.create(
                {
                    "name": self.env._(
                        "Agent runner token: %(runner)s [#%(id)s]",
                        runner=self.name,
                        id=self.id,
                    ),
                    "category_id": bearer.id,
                    "company_id": self.company_id.id,
                    "credential_value": token,
                }
            )
        self.auth_type = "bearer"
        self.message_post(body=self.env._("A new token was issued."))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Token for %(runner)s", runner=self.name),
                "message": self.env._(
                    "%(token)s\n\nIt is shown once: hand it to the runner now. Any "
                    "token issued before no longer works.",
                    token=token,
                ),
                "type": "warning",
                "sticky": True,
            },
        }

    @api.model
    def _receiver_for_bearer(self, **_path_args: Any) -> AgentRunner:
        """The runner whose token the call carries; the gate verifies it again."""
        header = request.httprequest.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return self.browse()
        return self._get_by_credential_token(token.strip(), [("active", "=", True)])

    # Polls: a call that hands nothing out and changes nothing leaves no row.
    _UNLOGGED_EVENTS = frozenset({"agent_claim", "agent_heartbeat"})

    def _inbound_event_logged(self, event_type: str | None) -> bool:
        return event_type not in self._UNLOGGED_EVENTS

    def _inbound_service_user(self) -> models.BaseModel:
        return (
            self.service_user_id
            or self.env.ref("agent_runner.user_agent_runner", raise_if_not_found=False)
            or self.env["res.users"]
        )

    def _touch(self) -> None:
        now = fields.Datetime.now()
        if not self.date_last_seen or now - self.date_last_seen >= _SEEN_RESOLUTION:
            self.date_last_seen = now
