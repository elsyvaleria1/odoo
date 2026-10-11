import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from typing import Any

import psycopg

from odoo import api, fields, models
from odoo.exceptions import AccessError, ConcurrencyError, UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.redact import dump_masked, mask_data, mask_text
from odoo.tools import SQL

_debug = DebugLog(__name__)
_logger = logging.getLogger(__name__)

LEASE_SECONDS_PARAM = "agent_runner.lease_seconds"
DEFAULT_LEASE_SECONDS = 300
LIVE_STATES = ("leased", "running")
FINAL_STATES = ("succeeded", "failed", "cancelled")
EVENT_TYPES = ("info", "progress", "warning", "error")
MAX_EVENTS_PER_CALL = 100
MAX_EVENT_DATA = 16_000
MAX_CREDENTIAL_FAILURES = 30


class CredentialsRefused(Exception):
    pass


class LeaseLost(Exception):
    pass


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _masked_data(data: object) -> dict[str, Any] | bool:
    if not isinstance(data, dict):
        return False
    masked = mask_data(data)
    if len(dump_masked(masked)) > MAX_EVENT_DATA:
        return {"truncated": True}
    return masked


class AgentRun(models.Model):
    _name = "agent.run"
    _description = "Agent Run"
    _inherit = ["mixin.mail.thread"]
    _order = "id desc"

    name = fields.Char(
        required=True,
    )
    kind = fields.Selection(
        selection=[("probe", "Probe")],
        required=True,
        help="What the runner is asked to do; the modules that hand out work add "
        "their own.",
    )
    capability_id = fields.Many2one(
        comodel_name="agent.capability",
        string="Capability",
        required=True,
        ondelete="restrict",
        help="Only a runner with this capability claims the run.",
    )
    run_state = fields.Selection(
        selection=[
            ("queued", "Queued"),
            ("leased", "Leased"),
            ("running", "Running"),
            ("succeeded", "Succeeded"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        string="State",
        default="queued",
        index=True,
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
        help="Whose budget the run's spend counts against.",
    )
    priority = fields.Integer(
        default=10,
        help="Higher first.",
    )
    res_model = fields.Char(
        string="Owner Model",
        index=True,
        readonly=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Owner",
        readonly=True,
    )
    payload = fields.Json(
        readonly=True,
        help="What the runner is handed.",
    )
    ml_purpose = fields.Char(
        string="Data Purpose",
        readonly=True,
        help="What the run's agent sends its model, as the company's machine-learning "
        "data policy names it: the model key is handed only when that policy lets "
        "this purpose reach the vendor. Empty: the run calls no model.",
    )
    result = fields.Json(
        readonly=True,
        help="What the runner handed back.",
    )
    runner_id = fields.Many2one(
        comodel_name="agent.runner",
        string="Runner",
        index=True,
        readonly=True,
        ondelete="set null",
    )
    lease_digest = fields.Char(
        copy=False,
        readonly=True,
    )
    date_lease_until = fields.Datetime(
        string="Lease Until",
        copy=False,
        readonly=True,
    )
    date_not_before = fields.Datetime(
        string="Not Before",
        copy=False,
        readonly=True,
        help="Its credentials could not be prepared: no runner claims it before this.",
    )
    count_credential_failure = fields.Integer(
        string="Credential Failures",
        default=0,
        copy=False,
        readonly=True,
        help="Claims in a row its credentials could not be prepared for.",
    )
    date_started = fields.Datetime(
        string="Started",
        copy=False,
        readonly=True,
    )
    date_finished = fields.Datetime(
        string="Finished",
        copy=False,
        readonly=True,
    )
    count_attempt = fields.Integer(
        string="Attempts",
        default=0,
        copy=False,
        readonly=True,
    )
    max_attempts = fields.Integer(
        default=3,
        help="How many leases it may be handed before an expiry or a retryable "
        "failure fails it for good.",
    )
    error = fields.Text(
        copy=False,
        readonly=True,
    )
    count_input_token = fields.Integer(
        string="Input Tokens",
        default=0,
        copy=False,
        readonly=True,
    )
    count_output_token = fields.Integer(
        string="Output Tokens",
        default=0,
        copy=False,
        readonly=True,
    )
    cost = fields.Float(
        digits=(16, 6),
        default=0,
        copy=False,
        readonly=True,
    )
    event_ids = fields.One2many(
        comodel_name="agent.run.event",
        inverse_name="run_id",
        string="Events",
        readonly=True,
    )

    _max_attempts_positive = models.Constraint(
        "CHECK(max_attempts > 0)",
        "A run is handed out at least once.",
    )


    def action_cancel(self) -> None:
        live = self.filtered(lambda run: run.run_state not in FINAL_STATES)
        live.write({"run_state": "cancelled", "date_finished": fields.Datetime.now()})
        for run in live:
            run._log_event("system", self.env._("Cancelled."))
            run._notify_owner()

    def action_retry(self) -> None:
        ended = self.filtered(lambda run: run.run_state in ("failed", "cancelled"))
        if ended != self:
            raise UserError(self.env._("Only a failed or cancelled run is retried."))
        ended.write(
            {
                "run_state": "queued",
                "count_attempt": 0,
                "runner_id": False,
                "date_lease_until": False,
                "date_finished": False,
                "date_not_before": False,
                "count_credential_failure": 0,
                "error": False,
            }
        )


    @api.model
    def _lease_seconds(self) -> int:
        seconds = self.env.registry.settings.get_int(
            self.env, LEASE_SECONDS_PARAM, DEFAULT_LEASE_SECONDS
        )
        return max(seconds, 30)

    @api.model
    def _companies_over_budget(self) -> list[int]:
        companies = self.search([("run_state", "=", "queued")]).company_id
        return [
            company.id
            for company in companies.sudo()
            if company.ml_monthly_budget
            and company._ml_spend_this_month() >= company.ml_monthly_budget
        ]

    @api.model
    def _claim(self, runner: models.BaseModel) -> tuple[AgentRun, str] | None:
        runner.check_singleton()
        self.flush_model()
        cr = self.env.cr
        cr.execute(
            SQL("SELECT id FROM agent_runner WHERE id = %s FOR UPDATE", runner.id)
        )
        held = self.search_count(
            [("runner_id", "=", runner.id), ("run_state", "in", LIVE_STATES)]
        )
        if held >= runner.concurrency or not runner.capability_ids:
            _debug.logic("run.claim_skipped", runner=runner.id, held=held)
            return None
        blocked = self._companies_over_budget()
        token = secrets.token_urlsafe(32)
        now = fields.Datetime.now()
        cr.execute(
            SQL(
                """
                WITH picked AS (
                    SELECT id FROM agent_run
                     WHERE run_state = 'queued'
                       AND capability_id = ANY(%s)
                       AND company_id = %s
                       AND company_id <> ALL(%s)
                       AND (date_not_before IS NULL OR date_not_before <= %s)
                     ORDER BY priority DESC, id
                     LIMIT 1
                       FOR UPDATE SKIP LOCKED
                )
                UPDATE agent_run AS run
                   SET run_state = 'leased',
                       runner_id = %s,
                       lease_digest = %s,
                       date_lease_until = %s,
                       count_attempt = COALESCE(run.count_attempt, 0) + 1,
                       write_uid = %s,
                       write_date = %s
                  FROM picked
                 WHERE run.id = picked.id
             RETURNING run.id
                """,
                runner.capability_ids.ids,
                runner.company_id.id,
                blocked,
                now,
                runner.id,
                _digest(token),
                now + timedelta(seconds=self._lease_seconds()),
                self.env.uid,
                now,
            )
        )
        row = cr.fetchone()
        self.invalidate_model()
        if not row:
            _debug.logic("run.claim_empty", runner=runner.id, blocked=len(blocked))
            return None
        run = self.browse(row[0])
        run._log_event(
            "system",
            self.env._(
                "Leased to %(runner)s, attempt %(attempt)s.",
                runner=runner.name,
                attempt=run.count_attempt,
            ),
        )
        _debug.logic(
            "run.leased", run=run.id, runner=runner.id, attempt=run.count_attempt
        )
        return run, token

    @api.model
    def _lease(self, runner: models.BaseModel) -> dict[str, Any] | None:
        while found := self._claim(runner):
            run, token = found
            try:
                with self.env.cr.savepoint():
                    answer = run._lease_answer(token)
                if run.count_credential_failure:
                    run.write({"count_credential_failure": 0, "date_not_before": False})
                return answer
            except CredentialsRefused as refusal:
                run._log_event("error", str(refusal))
                run._end_attempt(str(refusal), requeue=False)
            except psycopg.Error, ConcurrencyError:
                raise
            except Exception as error:
                _logger.warning(
                    "The credentials of agent run %s could not be prepared",
                    run.id,
                    exc_info=True,
                )
                run._defer(mask_text(f"{type(error).__name__}: {error}", 1000))
        return None

    def _defer(self, reason: str) -> None:
        self.check_singleton()
        failures = self.count_credential_failure + 1
        self._log_event(
            "error",
            self.env._(
                "Its credentials could not be prepared: %(reason)s", reason=reason
            ),
        )
        if failures >= MAX_CREDENTIAL_FAILURES:
            self._end_attempt(reason, requeue=False)
            return
        self.write(
            {
                "run_state": "queued",
                "runner_id": False,
                "date_lease_until": False,
                "count_attempt": self.count_attempt - 1,
                "count_credential_failure": failures,
                "date_not_before": fields.Datetime.now()
                + timedelta(minutes=min(2 ** (failures - 1), 60)),
                "error": reason,
            }
        )
        _debug.logic("run.deferred", run=self.id, failures=failures)

    def _holds(self, token: object) -> bool:
        self.check_singleton()
        return (
            isinstance(token, str)
            and bool(self.lease_digest)
            and hmac.compare_digest(self.lease_digest, _digest(token))
        )

    def _lease_answer(self, token: str) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "capability": self.capability_id.code,
            "payload": self.payload or {},
            "attempt": self.count_attempt,
            "lease_token": token,
            "lease_seconds": self._lease_seconds(),
            "credentials": self._prepare_credentials(),
        }

    def _prepare_credentials(self) -> dict[str, Any]:
        if not self.ml_purpose:
            return {}
        provider = self.env.ref(
            "integration_machine_learning.ai_provider_anthropic"
        ).with_privilege(
            "integration_machine_learning.privilege_route_ml",
            reason="a run is handed the key of the provider its purpose may reach",
        )
        try:
            self.env["integration.ml.policy"]._check_allowed(
                self.company_id, self.ml_purpose, provider
            )
        except UserError as refusal:
            raise CredentialsRefused(str(refusal)) from refusal
        connection = self.env["integration.connection"]._resolve(
            provider.endpoint_id, company=self.company_id
        )
        key = (
            connection.credential_id._use_secret(
                f"agent_runner:{self.kind}", prefer="api_key"
            )
            if connection.credential_id
            else None
        )
        if not key:
            self._log_event(
                "warning",
                self.env._(
                    "No Anthropic credential: the runner's own model login is used."
                ),
            )
            return {}
        return {"anthropic": {"api_key": key.reveal()}}

    def _heartbeat(self, token: object) -> dict[str, Any]:
        if not self._holds(token):
            raise LeaseLost
        if self.run_state == "cancelled":
            return {"cancel": True}
        if self.run_state not in LIVE_STATES:
            raise LeaseLost
        now = fields.Datetime.now()
        vals = {"date_lease_until": now + timedelta(seconds=self._lease_seconds())}
        if self.run_state == "leased":
            vals |= {"run_state": "running", "date_started": now}
        self.write(vals)
        return {"cancel": False, "lease_seconds": self._lease_seconds()}

    def _append_events(self, token: object, events: object) -> int:
        if not self._holds(token) or self.run_state not in LIVE_STATES:
            raise LeaseLost
        if not isinstance(events, list):
            return 0
        vals_list = []
        for event in events[:MAX_EVENTS_PER_CALL]:
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            message = event.get("message")
            data = event.get("data")
            vals_list.append(
                {
                    "run_id": self.id,
                    "event_type": event_type if event_type in EVENT_TYPES else "info",
                    "message": mask_text(message, 4000)
                    if isinstance(message, str)
                    else False,
                    "data": _masked_data(data),
                }
            )
        self.env["agent.run.event"].create(vals_list)
        return len(vals_list)

    def _complete(self, token: object, result: object, usage: dict[str, Any]) -> bool:
        if not self._holds(token):
            raise LeaseLost
        if self.run_state == "succeeded":
            _debug.logic("run.complete_replayed", run=self.id)
            return False
        if self.run_state not in LIVE_STATES:
            raise LeaseLost
        self.write(
            {
                "run_state": "succeeded",
                "result": result if isinstance(result, dict) else {},
                "date_finished": fields.Datetime.now(),
                "date_lease_until": False,
                **self._spend_vals(usage),
            }
        )
        self._log_event("system", self.env._("Succeeded."))
        self._notify_owner()
        _debug.logic("run.succeeded", run=self.id, cost=usage["cost"])
        return True

    def _fail(
        self,
        token: object,
        error: object,
        retryable: bool,
        usage: dict[str, Any] | None = None,
    ) -> str:
        if not self._holds(token):
            raise LeaseLost
        if self.run_state not in LIVE_STATES:
            return self.run_state
        if usage:
            self.write(self._spend_vals(usage))
        message = mask_text(error, 4000) if isinstance(error, str) else ""
        self._log_event("error", message or self.env._("The runner gave no reason."))
        self._end_attempt(message, requeue=retryable)
        return self.run_state

    def _spend_vals(self, usage: dict[str, Any]) -> dict[str, Any]:
        return {
            "count_input_token": self.count_input_token + usage["input_tokens"],
            "count_output_token": self.count_output_token + usage["output_tokens"],
            "cost": self.cost + usage["cost"],
        }

    def _end_attempt(self, error: str, *, requeue: bool) -> None:
        if requeue and self.count_attempt < self.max_attempts:
            self.write(
                {
                    "run_state": "queued",
                    "runner_id": False,
                    "date_lease_until": False,
                    "error": error,
                }
            )
            _debug.logic("run.requeued", run=self.id, attempt=self.count_attempt)
            return
        self.write(
            {
                "run_state": "failed",
                "date_lease_until": False,
                "date_finished": fields.Datetime.now(),
                "error": error,
            }
        )
        self._notify_owner()
        _debug.logic("run.failed", run=self.id, attempt=self.count_attempt)

    @api.model
    def _reap_expired_leases(self) -> int:
        self.flush_model()
        self.env.cr.execute(
            SQL(
                """
                SELECT id FROM agent_run
                 WHERE run_state IN %s AND date_lease_until < %s
                 ORDER BY date_lease_until
                   FOR UPDATE SKIP LOCKED
                """,
                LIVE_STATES,
                fields.Datetime.now(),
            )
        )
        expired = self.browse([row[0] for row in self.env.cr.fetchall()])
        for run in expired:
            run._log_event(
                "warning",
                self.env._(
                    "The lease held by %(runner)s expired.",
                    runner=run.runner_id.name or "?",
                ),
            )
            run._end_attempt(self.env._("The runner stopped answering."), requeue=True)
        _debug.logic("run.reaped", count=len(expired))
        return len(expired)


    def _owner(self) -> models.BaseModel | None:
        self.check_singleton()
        if not self.res_model or self.res_model not in self.env:
            return None
        owner = self.env[self.res_model].browse(self.res_id).exists()
        return owner or None

    def _notify_owner(self) -> None:
        owner = self._owner()
        if owner is None:
            return
        try:
            with self.env.cr.savepoint():
                self._tell_owner(owner)
        except AccessError as error:
            _logger.warning("Agent run %s could not tell %s: %s", self.id, owner, error)
            self._log_event(
                "system",
                self.env._(
                    "%(owner)s was not told how this run ended: %(error)s",
                    owner=f"{owner._name},{owner.id}",
                    error=error,
                ),
            )

    def _tell_owner(self, owner) -> None:
        if hasattr(owner, "_agent_run_ended"):
            owner._agent_run_ended(self)
        if hasattr(owner, "message_post"):
            state = dict(self._fields["run_state"]._description_selection(self.env))
            owner.message_post(
                body=self.env._(
                    "%(run)s: %(state)s.",
                    run=self.name,
                    state=state[self.run_state],
                ),
            )

    def _log_event(self, event_type: str, message: str) -> None:
        self.env["agent.run.event"].create(
            {"run_id": self.id, "event_type": event_type, "message": message}
        )
