from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

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
        ],
        ondelete={
            "testing": "set default",
            "test_failed": "set default",
            "test_passed": "set default",
            "closed": "set default",
            "merged": "set default",
            "hotfixing": "set default",
            "deployed": "set default",
        },
    )
    fix_commit = fields.Char(
        string="Fix Commit",
        readonly=True,
        help="The commit production must contain for the fix to be running: the "
        "merge, or the fix branch's head for a hotfix.",
    )

    # -- the pull request -------------------------------------------------------

    def _autofix_pull_changed(self, pull: models.BaseModel) -> None:
        self.check_singleton()
        if self.fix_state not in _REVIEW_STATES:
            return
        if pull.pull_state == "merged":
            self.write({"fix_state": "merged", "fix_commit": pull.merge_commit_sha})
        elif pull.pull_state == "closed":
            self.write({"fix_state": "closed"})
        else:
            self.write(
                {
                    "fix_state": {
                        "failure": "test_failed",
                        "success": "test_passed",
                    }.get(pull.checks_state, "testing")
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
        return self.pull_ids.filtered(lambda pull: pull.pull_state != "closed")[:1]

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
            merged = get_github_client(self.env).merge_pull_request(
                owner, name, pull.number, merge_method="squash"
            )
            incident.write({"fix_state": "merged", "fix_commit": merged.get("sha")})
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
                        "commit": pull.head_sha,
                    },
                }
            )
            incident.write({"fix_state": "hotfixing", "fix_commit": pull.head_sha})

    # -- production --------------------------------------------------------------

    def _autofix_delivery_ended(self, run: models.BaseModel) -> None:
        self.check_singleton()
        if run.kind != HOTFIX:
            return
        if run.run_state != "succeeded":
            self.write({"fix_state": "test_passed"})
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
        """Ask production which awaited fixes it runs, unless it is being asked."""
        waiting = self.search(
            [("fix_state", "=", "merged"), ("fix_commit", "!=", False)]
        )
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
        policy = self.env["error.incident.autofix.policy"]._current()
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
