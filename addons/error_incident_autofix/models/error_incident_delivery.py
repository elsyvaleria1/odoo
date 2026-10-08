from datetime import timedelta
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

from .error_incident import FIX
from .error_incident_autofix_policy import DELIVERY_KINDS, HOTFIX, REVISION
from odoo.addons.integration_github.tools import get_github_client

_debug = DebugLog(__name__)

# A fix on its way: its pull request is followed until production runs it.
_REVIEW_STATES = ("pushed", "testing", "test_failed", "test_passed")
_AWAITING_PRODUCTION = ("merged", "hotfixing")


class ErrorIncident(models.Model):
    """From a pushed fix to production: the pull request's checks, the merge or
    the hotfix a person approves, and the revision production reports."""

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

    # -- the pull request -------------------------------------------------------

    def _autofix_pull_changed(self, pull: models.BaseModel) -> None:
        self.check_singleton()
        if self.fix_state not in _REVIEW_STATES or pull != self._autofix_pull():
            # an earlier fix's pull request speaks for that fix, not this one
            return
        snapshot = self.approval_request_id.operation_snapshot or {}
        if snapshot.get("head") and snapshot["head"] != pull.head_sha:
            # what was asked about is gone: its approval covers nothing
            self._autofix_release_approval(
                self.env._("the pull request moved past the commit it asked about")
            )
        elif pull.pull_state in ("merged", "closed"):
            # merged or closed on GitHub: no merge or hotfix is left to decide
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
        """The pull request of the incident's newest fix: the one a merge or a
        hotfix is about."""
        self.check_singleton()
        fix = self.fix_run_ids.filtered(lambda run: run.kind == FIX).sorted("id")[-1:]
        return fix.github_pull_id

    def _autofix_policy_passes_unchecked(self) -> bool:
        return bool(self._autofix_repository().pass_without_checks)

    # -- merge and hotfix, each a person's decision ------------------------------

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
        # what was approved is this commit: a pull request pushed to since is a
        # new decision
        self.check_singleton()
        pull = self._autofix_pull()
        return {"pull": pull.id, "head": pull.head_sha}

    def _get_approval_request_name(self) -> str:
        return self.env._("Autofix: %s", self.name)

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
        """Merge the fix's pull request -- once a person approved it."""
        for incident in self:
            pull = incident._autofix_pull()
            owner, _, name = pull.repository.partition("/")
            # the approved commit, and only it: GitHub refuses the merge when
            # the head moved after the approval, however late its webhook is
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
        """Apply the fix to production before it is merged -- once a person
        approved it. The deploy runner applies, upgrades and checks the server,
        and reverts it when the server does not come back healthy."""
        policy = self.env["error.incident.autofix.policy"]._current()
        for incident in self:
            pull = incident._autofix_pull()
            repository = incident._autofix_repository()
            self.env["agent.run"].create(
                {
                    "name": f"Hotfix: {incident.name}"[:200],
                    "kind": HOTFIX,
                    "capability_id": self.env.ref("agent_runner.capability_deploy").id,
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
        """The approval is spent -- its operation ran, or what it was asked
        about changed: the next merge or hotfix of this incident is a new
        decision with a request of its own. One still pending is refused for
        ``reason``, so no approver grants it after."""
        self.check_singleton()
        request = self.approval_request_id
        if not request:
            return
        _debug.logic("autofix.approval_spent", incident=self.id, request=request.id)
        if reason and request.state not in request._TERMINAL_STATES | {"new"}:
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
        # a request about a commit that is no longer the pull request's head --
        # approved, or still pending because its approval could not run -- is
        # released, and the operation asks again, instead of refused for good
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

    # -- production --------------------------------------------------------------

    def _autofix_delivery_ended(self, run: models.BaseModel) -> None:
        self.check_singleton()
        if run.kind != HOTFIX or self.fix_state != "hotfixing":
            return
        if run.run_state != "succeeded":
            self.write({"fix_state": "test_passed"})
            # the pull request is read again: merged or closed while the
            # hotfix ran, the incident follows that, not the hotfix
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
        """Production runs these commits: the incidents whose fix is among them
        are fixed -- resolved, and their users told."""
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
        """Ask production which awaited fixes it runs, unless it is being asked.
        A fix production has not run for the policy's wait is no longer asked
        about: the incident says so, once, for a person to deploy or decide."""
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
        Run = self.env["agent.run"]
        if Run.search_count(
            [
                ("kind", "=", REVISION),
                ("run_state", "in", ("queued", "leased", "running")),
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
                "capability_id": self.env.ref("agent_runner.capability_deploy").id,
                "company_id": policy.company_id.id,
                "max_attempts": 1,
                "payload": {"checkouts": checkouts},
            }
        )


class AgentRun(models.Model):
    _inherit = "agent.run"

    def _github_permissions(self) -> dict[str, str]:
        if self.kind in DELIVERY_KINDS:
            return {"contents": "read", "metadata": "read"}
        return super()._github_permissions()

    def _complete(self, token: object, result: object, usage: dict[str, Any]) -> bool:
        first = super()._complete(token, result, usage)
        if first and self.kind == REVISION and isinstance(result, dict):
            self.env["error.incident"]._autofix_contained(
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
