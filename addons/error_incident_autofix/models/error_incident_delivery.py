from datetime import timedelta
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

from .error_incident import FIX
from .error_incident_autofix_policy import DELIVERY_KINDS, HOTFIX, REVISION
from odoo.addons.integration_github.tools import get_github_client

_debug = DebugLog(__name__)

_REVIEW_STATES = ("pushed", "testing", "test_failed", "test_passed")
_AWAITING_PRODUCTION = ("merged", "hotfixing")


class ErrorIncident(models.Model):
    _name = "error.incident"
    _inherit = ["error.incident", "mixin.approval.gate"]
    _access_verbs = {
        "merge": models.Verb(methods=("action_autofix_merge",)),
        "hotfix": models.Verb(methods=("action_autofix_hotfix",)),
    }

    fix_state = fields.Selection(
        selection_add=[
            ("testing", "Testing"),
            ("test_failed", "Tests Failed"),
            ("test_passed", "Tests Passed"),
            ("closed", "Pull Request Closed"),
            ("merged", "Merged"),
            ("hotfixing", "Hotfixing"),
            ("deployed", "In Production"),
            ("not_deployed", "Not Deployed"),
        ],
        ondelete={
            "testing": "set default",
            "test_failed": "set default",
            "test_passed": "set default",
            "closed": "set default",
            "merged": "set default",
            "hotfixing": "set default",
            "deployed": "set default",
            "not_deployed": "set default",
        },
    )
    fix_commit = fields.Char(
        string="Fix Commit",
        readonly=True,
        help="The commit production must contain for the fix to be running: the "
        "merge, or the fix branch's head for a hotfix.",
    )
    date_fix_merged = fields.Datetime(
        string="Fix Merged",
        readonly=True,
        help="Since when production is asked whether it runs the merged fix.",
    )

    def _autofix_pull_changed(self, pull: models.BaseModel) -> None:
        self.check_singleton()
        if self.fix_state not in _REVIEW_STATES or pull != self._autofix_pull():
            return
        snapshot = self.approval_request_id.operation_snapshot or {}
        if snapshot.get("head") and snapshot["head"] != pull.head_sha:
            self._autofix_release_approval(
                self.env._("the pull request moved past the commit it asked about")
            )
        elif pull.pull_state in ("merged", "closed"):
            self._autofix_release_approval(
                self.env._("the pull request was merged or closed on GitHub")
            )
        if pull.pull_state == "merged":
            self.write(
                {
                    "fix_state": "merged",
                    "fix_commit": pull.merge_commit_sha,
                    "date_fix_merged": fields.Datetime.now(),
                }
            )
        elif pull.pull_state == "closed":
            self.write({"fix_state": "closed"})
        else:
            passing = (
                ("success", "none")
                if self._autofix_policy_passes_unchecked()
                else ("success",)
            )
            self.write(
                {
                    "fix_state": "test_failed"
                    if pull.checks_state == "failure"
                    else "test_passed"
                    if pull.checks_state in passing
                    else "testing"
                }
            )
        _debug.logic(
            "autofix.pull_changed",
            incident=self.id,
            pull=pull.id,
            state=self.fix_state,
        )

    def _autofix_pull(self) -> models.BaseModel:
        self.check_singleton()
        fix = self.fix_run_ids.filtered(lambda run: run.kind == FIX).sorted("id")[-1:]
        return fix.github_pull_id

    def _autofix_policy_passes_unchecked(self) -> bool:
        return bool(self._autofix_repository().pass_without_checks)

    def _check_before_approval(self, verb: str) -> None:
        super()._check_before_approval(verb)
        if verb not in ("merge", "hotfix"):
            return
        for incident in self:
            if incident.fix_state != "test_passed" or not incident._autofix_pull():
                raise UserError(
                    self.env._(
                        "Only a fix whose pull request passes its checks is merged "
                        "or hotfixed."
                    )
                )

    def _get_domain_approval_category(self) -> list:
        return [("approval_type", "=", "autofix")]

    def _get_approval_snapshot(self, operation: str) -> dict[str, Any]:
        self.check_singleton()
        pull = self._autofix_pull()
        return {"pull": pull.id, "head": pull.head_sha}

    def _get_approval_reason_html(self) -> str:
        self.check_singleton()
        pull = self._autofix_pull()
        return self.env._(
            "An agent's fix of %(incident)s passes its checks: %(pull)s, commit "
            "%(commit)s. %(analysis)s",
            incident=self.name,
            pull=pull.url or f"{pull.repository}#{pull.number}",
            commit=(pull.head_sha or "")[:12],
            analysis=self.fix_analysis or "",
        )

    def action_autofix_merge(self) -> None:
        for incident in self:
            pull = incident._autofix_pull()
            owner, _, name = pull.repository.partition("/")
            merged = get_github_client(self.env).merge_pull_request(
                owner, name, pull.number, merge_method="squash", sha=pull.head_sha
            )
            incident.write(
                {
                    "fix_state": "merged",
                    "fix_commit": merged.get("sha"),
                    "date_fix_merged": fields.Datetime.now(),
                }
            )
            incident._autofix_release_approval()
            incident.message_post(
                body=self.env._(
                    "The fix was merged as %(commit)s; it is resolved once production runs it.",
                    commit=(merged.get("sha") or "")[:12],
                )
            )

    def action_autofix_hotfix(self) -> None:
        policy = self.env["error.incident.autofix.policy"]._current()
        for incident in self:
            pull = incident._autofix_pull()
            repository = incident._autofix_repository()
            self.env["runner.job"].create(
                {
                    "name": f"Hotfix: {incident.name}"[:200],
                    "kind": HOTFIX,
                    "capability_id": self.env.ref("runner.capability_deploy").id,
                    "company_id": policy.company_id.id,
                    "res_model": incident._name,
                    "res_id": incident.id,
                    "github_repository": pull.repository,
                    "payload": {
                        "checkout": repository.checkout,
                        "repository": pull.repository,
                        "branch": pull.head_ref,
                        "base_branch": pull.base_ref or repository.base_branch,
                        "commit": pull.head_sha,
                    },
                }
            )
            incident.write({"fix_state": "hotfixing", "fix_commit": pull.head_sha})
            incident._autofix_release_approval()

    def _autofix_release_approval(self, reason: str | None = None) -> None:
        self.check_singleton()
        request = self.approval_request_id
        if not request:
            return
        _debug.logic("autofix.approval_spent", incident=self.id, request=request.id)
        if request.state == "new":
            request._force_terminal(
                "cancelled",
                body=self.env._(
                    "Cancelled: %s.", reason or self.env._("the fix moved on")
                ),
            )
        elif reason and request.state not in request._TERMINAL_STATES:
            request._force_terminal(
                "refused",
                body=self.env._("Refused: %s.", reason),
                refusal_reason=self.env.ref("approval.refusal_reason_other"),
                refusal_note=reason,
            )
            self.message_post(
                body=self.env._("The approval request was refused: %s.", reason),
                message_type="notification",
            )
        self.approval_request_id = False

    def _split_for_approval(self, operation: str) -> tuple:
        for incident in self:
            if (
                incident.approval_request_id
                and incident.approval_state in ("new", "pending", "approved")
                and incident._approval_request_gates(operation)
                and incident.approval_request_id.operation_snapshot
                and incident.approval_request_id.operation_snapshot
                != incident._get_approval_snapshot(operation)
            ):
                incident._autofix_release_approval(
                    self.env._("the pull request moved past the commit it asked about")
                )
        return super()._split_for_approval(operation)

    def _autofix_delivery_ended(self, run: models.BaseModel) -> None:
        self.check_singleton()
        if run.kind != HOTFIX or self.fix_state != "hotfixing":
            return
        if run.job_state != "succeeded":
            self.write({"fix_state": "test_passed"})
            self._autofix_pull_changed(self._autofix_pull())
            self.message_post(
                body=self.env._(
                    "The hotfix was not applied, or was reverted: %(error)s",
                    error=run.error or "",
                )
            )
            return
        self._autofix_contained((run.result or {}).get("contained") or [])

    @api.model
    def _autofix_contained(self, commits: list[str]) -> None:
        if not commits:
            return
        incidents = self.search(
            [
                ("fix_state", "in", _AWAITING_PRODUCTION),
                ("fix_commit", "in", list(commits)),
            ]
        )
        for incident in incidents:
            incident.write({"fix_state": "deployed"})
            incident.action_resolve()
            _debug.logic("autofix.deployed", incident=incident.id)

    @api.model
    def _cron_autofix_check_production(self) -> None:
        policy = self.env["error.incident.autofix.policy"]._current()
        if not policy:
            return
        merged = self.search(
            [("fix_state", "=", "merged"), ("fix_commit", "!=", False)]
        )
        merged.filtered(lambda incident: not incident.date_fix_merged).write(
            {"date_fix_merged": fields.Datetime.now()}
        )
        horizon = fields.Datetime.now() - timedelta(days=policy.production_wait_days)
        overdue = merged.filtered(lambda incident: incident.date_fix_merged < horizon)
        for incident in overdue:
            incident.write({"fix_state": "not_deployed"})
            incident.message_post(
                body=self.env._(
                    "Production has not run this fix in %(days)s days; it is no "
                    "longer asked about. Deploy it, or close the incident.",
                    days=policy.production_wait_days,
                )
            )
        waiting = merged - overdue
        if not waiting:
            return
        Run = self.env["runner.job"]
        if Run.search_count(
            [
                ("kind", "=", REVISION),
                ("job_state", "in", ("queued", "leased", "running")),
            ]
        ):
            return
        checkouts: dict[str, list[str]] = {}
        for incident in waiting:
            checkout = incident._autofix_repository().checkout
            if checkout:
                checkouts.setdefault(checkout, []).append(incident.fix_commit)
        if not checkouts:
            return
        Run.create(
            {
                "name": "Production revision",
                "kind": REVISION,
                "capability_id": self.env.ref("runner.capability_deploy").id,
                "company_id": policy.company_id.id,
                "max_attempts": 1,
                "payload": {"checkouts": checkouts},
            }
        )


class RunnerJob(models.Model):
    _inherit = "runner.job"

    def _github_permissions(self) -> dict[str, str]:
        if self.kind in DELIVERY_KINDS:
            return {"contents": "read", "metadata": "read"}
        return super()._github_permissions()

    def _complete(self, token: object, result: object, usage: dict[str, Any]) -> bool:
        first = super()._complete(token, result, usage)
        if first and self.kind == REVISION and isinstance(result, dict):
            self.env["error.incident"].with_privilege(
                "error_incident_autofix.privilege_report_runner_job",
                reason="a production revision resolves the incidents it ships",
            )._autofix_contained(
                [
                    commit
                    for commit in result.get("contained") or []
                    if isinstance(commit, str)
                ]
            )
        return first


class IntegrationGithubPull(models.Model):
    _inherit = "integration.github.pull"

    def _github_updated(self) -> None:
        super()._github_updated()
        for pull in self.filtered("incident_id"):
            pull.incident_id._autofix_pull_changed(pull)
