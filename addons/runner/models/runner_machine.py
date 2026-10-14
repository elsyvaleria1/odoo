import secrets
from datetime import timedelta
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

_ONLINE_WINDOW = timedelta(minutes=2)
_SEEN_RESOLUTION = timedelta(seconds=30)


class RunnerMachine(models.Model):
    _name = "runner.machine"
    _description = "Runner Machine"
    _inherit = ["mixin.inbound.gate", "mixin.mail.thread"]
    _order = "name, id"
    _receiver_privileges = ("runner.privilege_runner",)
    _inbound_elevated = False

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
        required=True,
        help="The company it works for: it claims that company's jobs only, and is "
        "handed that company's keys. A machine serving several companies runs "
        "one runner per company.",
    )
    capability_ids = fields.Many2many(
        comodel_name="runner.capability",
        string="Capabilities",
        help="The kinds of work this runner may claim.",
    )
    concurrency = fields.Integer(
        default=1,
        help="How many jobs it may hold at once.",
    )
    date_last_seen = fields.Datetime(
        string="Last Seen",
        readonly=True,
    )
    is_online = fields.Boolean(
        string="Online",
        compute="_compute_is_online",
    )
    job_ids = fields.One2many(
        comodel_name="runner.job",
        inverse_name="machine_id",
        string="Jobs",
        readonly=True,
    )

    _concurrency_positive = models.Constraint(
        "CHECK(concurrency > 0)",
        "A runner holds at least one job at a time.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        runners = super().create(vals_list)
        runners._place_service_user()
        return runners

    def write(self, vals):
        result = super().write(vals)
        if vals.keys() & {"company_id", "service_user_id", "active"}:
            self._place_service_user()
        return result

    def _place_service_user(self) -> None:
        Gate = self.env["mixin.inbound.gate"]
        for principal, runners in (
            self.filtered("active")
            .grouped(lambda runner: runner._inbound_service_user())
            .items()
        ):
            Gate._place_principal_in_companies(principal, runners.company_id)

    @api.depends("date_last_seen")
    def _compute_is_online(self) -> None:
        horizon = fields.Datetime.now() - _ONLINE_WINDOW
        for runner in self:
            runner.is_online = bool(
                runner.date_last_seen and runner.date_last_seen >= horizon
            )

    def action_issue_token(self) -> dict[str, Any]:
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
                        "Runner token: %(runner)s [#%(id)s]",
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
                "className": "o_notification_line_breaks",
            },
        }

    @api.model
    def _receiver_for_bearer(self, **_path_args: Any) -> RunnerMachine:
        header = request.httprequest.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return self.browse()
        return self._get_by_credential_token(token.strip(), [("active", "=", True)])

    _UNLOGGED_EVENTS = frozenset({"runner_claim", "runner_heartbeat"})

    def _inbound_event_logged(self, event_type: str | None) -> bool:
        return event_type not in self._UNLOGGED_EVENTS

    def _inbound_service_user(self) -> models.BaseModel:
        return (
            self.service_user_id
            or self.env.ref("runner.user_runner", raise_if_not_found=False)
            or self.env["res.users"]
        )

    def _touch(self) -> None:
        now = fields.Datetime.now()
        if not self.date_last_seen or now - self.date_last_seen >= _SEEN_RESOLUTION:
            self.date_last_seen = now
