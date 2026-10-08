import logging
import re
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

from .error_incident_autofix_policy import AUTOFIX_KINDS

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

DIAGNOSE = "error_incident.diagnose"
FIX = "error_incident.fix"
ML_PURPOSE = "error_incident.autofix"
# fix states an incident rests in; a dispatch starts from one of them
LIVE_FIX_STATES = ("diagnosing", "fixing")
IDLE_FIX_STATES = (
    "none",
    "not_a_defect",
    "unclear",
    "unchanged",
    "proposed",
    "failed",
    "test_failed",
    "closed",
    "not_deployed",
)
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){0,4}$")
_MAX_DIFF = 200_000


class ErrorIncident(models.Model):
    _inherit = "error.incident"

    fix_state = fields.Selection(
        selection=[
            ("none", "Not Dispatched"),
            ("diagnosing", "Diagnosing"),
            ("not_a_defect", "Not a Defect"),
            ("unclear", "Unclear"),
            ("fixing", "Fixing"),
            ("unchanged", "No Change Made"),
            ("proposed", "Fix Proposed"),
            ("pushed", "Fix Pushed"),
            ("failed", "Run Failed"),
        ],
        string="Autofix",
        default="none",
        required=True,
        tracking=True,
        help="Driven only by what the agent runs report.",
    )
    fix_analysis = fields.Text(
        string="Analysis",
        readonly=True,
        help="The diagnosis's root cause, then the fix's note.",
    )
    fix_diff = fields.Text(
        string="Proposed Change",
        readonly=True,
    )
    fix_branch = fields.Char(
        string="Fix Branch",
        readonly=True,
    )
    count_fix_attempt = fields.Integer(
        string="Fix Attempts",
        readonly=True,
        help="Since the last regression.",
    )
    fix_run_ids = fields.One2many(
        comodel_name="agent.run",
        inverse_name="res_id",
        string="Agent Runs",
        readonly=True,
        domain=[("res_model", "=", "error.incident")],
    )
    fix_cost = fields.Float(
        string="Agent Cost",
        digits=(16, 4),
        compute="_compute_fix_cost",
    )

    @api.depends("fix_run_ids.cost")
    def _compute_fix_cost(self) -> None:
        for incident in self:
            incident.fix_cost = sum(incident.fix_run_ids.mapped("cost"))

    # -- dispatch ---------------------------------------------------------------

    def _capture(self, payload: dict[str, Any]) -> int:
        incident_id = super()._capture(payload)
        incident = self.browse(incident_id)
        policy = self.env["error.incident.autofix.policy"]._current()
        if not policy or policy.mode == "off":
            return incident_id
        # the error being recorded comes first: an autofix that cannot be
        # considered is logged, never raised into the capture
        try:
            with self.env.cr.savepoint():
                incident._autofix_consider()
        except Exception:
            _logger.exception(
                "Could not consider incident %s for the autofix", incident_id
            )
        return incident_id

    def _on_regressed(self) -> None:
        """The fix did not hold: the incident is the agents' again, with its
        attempts counted afresh -- once, when it reopens, not at every
        occurrence after; a run still at work is left to finish."""
        super()._on_regressed()
        for incident in self:
            if incident.fix_state not in LIVE_FIX_STATES:
                incident.write({"fix_state": "none", "count_fix_attempt": 0})

    def _autofix_refusal(
        self, policy: models.BaseModel, *, by_hand: bool = False
    ) -> str | None:
        """Why this incident is not handed to the agents now, or ``None``."""
        self.check_singleton()
        if policy.mode == "off":
            return "off"
        if self.fix_state not in IDLE_FIX_STATES:
            return "busy"
        if self.count_fix_attempt >= policy.max_attempts:
            return "attempts_spent"
        if not policy._under_daily_cap():
            return "daily_cap"
        if not self._autofix_repository():
            return "unmapped"
        if by_hand:
            return None
        if self.incident_state not in ("new", "regressed"):
            return "with_a_person"
        if self.fix_state != "none":
            return "handled"
        if self.source == "client":
            return "browser"
        if self.count_occurrence < policy.min_occurrences:
            return "too_rare"
        if policy.require_internal_user and not self.user_ids.filtered(
            lambda user: not user.share
        ):
            return "no_internal_user"
        if self.exception_type in policy._lines("excluded_exception_types"):
            return "excluded_exception"
        if self.origin_module in policy._lines("excluded_modules"):
            return "excluded_module"
        return None

    def _autofix_consider(self) -> None:
        policy = self.env["error.incident.autofix.policy"]._current()
        for incident in self:
            refusal = incident._autofix_refusal(policy) if policy else "no_policy"
            if refusal:
                _debug.logic(
                    "autofix.not_dispatched", incident=incident.id, why=refusal
                )
                continue
            incident._autofix_diagnose(policy)

    def action_autofix_dispatch(self) -> None:
        """Hand the incident to the agents now, below the thresholds."""
        policy = self.env["error.incident.autofix.policy"]._current()
        for incident in self:
            refusal = (
                incident._autofix_refusal(policy, by_hand=True)
                if policy
                else "no_policy"
            )
            if refusal:
                raise UserError(self._refusal_text(refusal))
            incident._autofix_diagnose(policy)

    def _refusal_text(self, code: str) -> str:
        return {
            "no_policy": self.env._("No autofix policy is configured."),
            "off": self.env._("The autofix is off."),
            "busy": self.env._("A run is already working on this incident."),
            "attempts_spent": self.env._("This incident's fix attempts are spent."),
            "daily_cap": self.env._("Today's run cap is reached."),
            "unmapped": self.env._(
                "The repository of this incident's module is not mapped."
            ),
        }.get(code, code)

    def _autofix_repository(self) -> models.BaseModel:
        return self.env["error.incident.autofix.repository"]._for_module(
            self.origin_module
        )

    def _autofix_diagnose(self, policy: models.BaseModel) -> None:
        prompt = self.env["error.incident.autofix.prompt"]._current("diagnose")
        repository = self._autofix_repository()
        self._autofix_run(
            policy,
            DIAGNOSE,
            repository,
            {
                "prompt": prompt.body,
                "prompt_version": prompt.version,
                "model": policy.diagnose_model,
                "timeout": policy.diagnose_timeout,
                "base_branch": repository.base_branch,
            },
        )
        self.write({"fix_state": "diagnosing"})

    def _autofix_fix(self, policy: models.BaseModel, diagnosis: dict[str, Any]) -> None:
        prompt = self.env["error.incident.autofix.prompt"]._current("fix")
        repository = self._autofix_repository()
        slug = (
            diagnosis.get("slug")
            if _SLUG_RE.match(str(diagnosis.get("slug", "")))
            else "fix"
        )
        attempt = self.count_fix_attempt + 1
        # numbered over the incident's whole life: a fix after a regression
        # never reuses the branch, nor meets the pull request, of an earlier one
        lifetime = len(self.fix_run_ids.filtered(lambda run: run.kind == FIX)) + 1
        branch = f"{repository.base_branch}-fix-{slug}-i{self.id}-a{lifetime}"
        self._autofix_run(
            policy,
            FIX,
            repository,
            {
                "prompt": prompt.body,
                "prompt_version": prompt.version,
                "model": policy.fix_model,
                "timeout": policy.fix_timeout,
                "base_branch": repository.base_branch,
                "branch": branch,
                "diagnosis": diagnosis,
                "push": policy.mode == "live",
                "commit_author": {
                    "name": policy.commit_author_name,
                    "email": policy.commit_author_email,
                },
            },
        )
        self.write(
            {"fix_state": "fixing", "count_fix_attempt": attempt, "fix_branch": branch}
        )

    def _autofix_run(
        self,
        policy: models.BaseModel,
        kind: str,
        repository: models.BaseModel,
        payload: dict[str, Any],
    ) -> models.BaseModel:
        self.check_singleton()
        run = self.env["agent.run"].create(
            {
                "name": f"{'Diagnose' if kind == DIAGNOSE else 'Fix'}: {self.name}"[
                    :200
                ],
                "kind": kind,
                "capability_id": self.env.ref("agent_runner.capability_sandbox").id,
                "company_id": policy.company_id.id,
                "res_model": self._name,
                "res_id": self.id,
                "ml_purpose": ML_PURPOSE,
                "github_repository": repository.github_repository,
                "payload": {
                    **payload,
                    "repository": repository.github_repository,
                    "incident": self._autofix_incident_data(),
                },
            }
        )
        _debug.logic("autofix.dispatched", incident=self.id, kind=kind, run=run.id)
        return run

    def _autofix_incident_data(self) -> dict[str, Any]:
        """What the agent is told of the incident -- data, never instructions:
        the runner fences it off from the prompt."""
        occurrence = self.occurrence_ids[:1]
        previous = [
            {
                "branch": run.github_branch,
                "analysis": (run.result or {}).get("note"),
                "pull_request": run.github_pull_id.url,
            }
            for run in self.fix_run_ids
            if run.kind == FIX and run.run_state == "succeeded"
        ]
        return {
            "id": self.id,
            "title": self.name,
            "exception_type": self.exception_type,
            "message": occurrence.message,
            "traceback": occurrence.traceback,
            "origin": {
                "module": self.origin_module,
                "path": self.origin_path,
                "function": self.origin_function,
                "line": occurrence.origin_line,
            },
            "source": self.source,
            "location": occurrence.location,
            "occurrences": self.count_occurrence,
            "users": len(self.user_ids),
            "regressions": self.count_regression,
            "previous_fixes": previous,
        }

    # -- results ----------------------------------------------------------------

    def _agent_run_ended(self, run: models.BaseModel) -> None:
        if hasattr(super(), "_agent_run_ended"):
            super()._agent_run_ended(run)
        if run.kind not in AUTOFIX_KINDS:
            self._autofix_delivery_ended(run)
            return
        if not self._autofix_awaits(run):
            _debug.logic("autofix.stale_run", incident=self.id, run=run.id)
            return
        if run.run_state != "succeeded":
            self.write({"fix_state": "failed"})
            return
        result = run.result or {}
        if run.kind == DIAGNOSE:
            self._autofix_diagnosed(result)
        else:
            self._autofix_fixed(result)

    def _autofix_awaits(self, run: models.BaseModel) -> bool:
        """Whether the incident is waiting for this run: its newest diagnosis
        or fix, in the state that run leaves. A run overtaken -- by a
        regression, a person's dispatch, a retry -- changes nothing."""
        self.check_singleton()
        newest = self.fix_run_ids.filtered(lambda r: r.kind in AUTOFIX_KINDS).sorted(
            "id"
        )[-1:]
        waiting = "diagnosing" if run.kind == DIAGNOSE else "fixing"
        return run == newest and self.fix_state == waiting

    def _autofix_diagnosed(self, result: dict[str, Any]) -> None:
        verdict = result.get("verdict")
        analysis = str(result.get("root_cause") or "")[:10_000]
        if verdict == "not_a_defect":
            self.write({"fix_state": "not_a_defect", "fix_analysis": analysis})
            return
        if verdict != "defect":
            self.write({"fix_state": "unclear", "fix_analysis": analysis})
            return
        self.write({"fix_analysis": analysis})
        policy = self.env["error.incident.autofix.policy"]._current()
        if policy.mode == "off" or not policy._under_daily_cap():
            self.write({"fix_state": "unclear"})
            return
        self._autofix_fix(policy, result)

    def _autofix_fixed(self, result: dict[str, Any]) -> None:
        note = str(result.get("note") or "")[:10_000]
        analysis = "\n\n".join(part for part in (self.fix_analysis, note) if part)
        diff = result.get("diff") if isinstance(result.get("diff"), str) else ""
        # a fix an earlier attempt pushed is reported without its diff
        if result.get("verdict") != "fixed" or not (
            diff.strip() or result.get("pushed")
        ):
            self.write({"fix_state": "unchanged", "fix_analysis": analysis})
            return
        self.write(
            {
                "fix_state": "pushed" if result.get("pushed") else "proposed",
                "fix_analysis": analysis,
                "fix_diff": diff[:_MAX_DIFF],
            }
        )
