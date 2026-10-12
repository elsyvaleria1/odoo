import logging
from typing import Any

import psycopg

from odoo import api, fields, models
from odoo.exceptions import ConcurrencyError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

from ..tools import create_once, get_github_client, repository_domain, same_repository

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


def _split_repository(repository: str) -> tuple[str, str]:
    owner, _, name = repository.partition("/")
    return owner, name


class IntegrationGithubPull(models.Model):
    _name = "integration.github.pull"
    _description = "GitHub Pull Request"
    _inherit = ["mixin.mail.thread"]
    _order = "date_last_event desc, id desc"
    _access_anchors = frozendict({"company": ""})

    name = fields.Char(
        string="Title",
        required=True,
    )
    repository = fields.Char(
        index=True,
        required=True,
        help="owner/name",
    )
    number = fields.Integer(
        required=True,
    )
    url = fields.Char(
        string="URL",
    )
    head_ref = fields.Char(
        string="Branch",
        index=True,
    )
    head_sha = fields.Char(
        string="Head Commit",
    )
    head_repository = fields.Char(
        help="owner/name of the repository the branch lives in: another than the "
        "pull request's own for one opened from a fork.",
    )
    base_ref = fields.Char(
        string="Base Branch",
    )
    author_login = fields.Char(
        string="Author",
    )
    is_draft = fields.Boolean(
        string="Draft",
    )
    pull_state = fields.Selection(
        selection=[
            ("open", "Open"),
            ("closed", "Closed"),
            ("merged", "Merged"),
        ],
        string="State",
        default="open",
        required=True,
        tracking=True,
    )
    date_merged = fields.Datetime(
        string="Merged",
    )
    merge_commit_sha = fields.Char(
        string="Merge Commit",
    )
    checks_state = fields.Selection(
        selection=[
            ("none", "No Checks"),
            ("pending", "Pending"),
            ("success", "Passing"),
            ("failure", "Failing"),
        ],
        string="Checks",
        default="none",
        required=True,
        tracking=True,
    )
    check_ids = fields.One2many(
        comodel_name="integration.github.check",
        string="Checks of the Head Commit",
        compute="_compute_check_ids",
    )
    date_last_event = fields.Datetime(
        string="Last Event",
    )
    date_github_updated = fields.Datetime(
        string="Updated on GitHub",
        help="When GitHub last changed the pull request, as the newest delivery "
        "said: an older delivery, redelivered or reordered, changes nothing.",
    )

    _number_uniq = models.Constraint(
        "UNIQUE(repository, number)",
        "A pull request is recorded once per repository.",
    )

    @api.depends("repository", "head_sha")
    def _compute_check_ids(self) -> None:
        Check = self.env["integration.github.check"]
        heads = {(pull.repository, pull.head_sha) for pull in self if pull.head_sha}
        by_head: dict[tuple[str, str], list[int]] = {}
        if heads:
            checks = Check.search(
                Domain.OR(
                    [("repository", "=", repo), ("head_sha", "=", sha)]
                    for repo, sha in heads
                )
            )
            for check in checks:
                by_head.setdefault((check.repository, check.head_sha), []).append(
                    check.id
                )
        for pull in self:
            pull.check_ids = Check.browse(
                by_head.get((pull.repository, pull.head_sha), [])
            )

    @api.model
    def _upsert_from_github(
        self, repository: str, pr: dict[str, Any], *, authoritative: bool = False
    ) -> IntegrationGithubPull:
        merged = bool(pr.get("merged") or pr.get("merged_at"))
        updated = _github_datetime(pr.get("updated_at"))
        vals = {
            "name": (pr.get("title") or f"#{pr['number']}")[:500],
            "url": pr.get("html_url"),
            "head_ref": pr.get("head", {}).get("ref"),
            "head_sha": pr.get("head", {}).get("sha"),
            "head_repository": ((pr.get("head") or {}).get("repo") or {}).get(
                "full_name"
            ),
            "base_ref": pr.get("base", {}).get("ref"),
            "author_login": pr.get("user", {}).get("login"),
            "is_draft": bool(pr.get("draft")),
            "pull_state": "merged"
            if merged
            else ("closed" if pr.get("state") == "closed" else "open"),
            "date_merged": _github_datetime(pr.get("merged_at")),
            "merge_commit_sha": pr.get("merge_commit_sha") if merged else False,
            "date_last_event": fields.Datetime.now(),
            "date_github_updated": updated,
        }
        domain = [
            *repository_domain("repository", repository),
            ("number", "=", pr["number"]),
        ]
        pull = self.search(domain, limit=1) or create_once(
            self, domain, {**vals, "repository": repository, "number": pr["number"]}
        )
        if (
            updated
            and pull.date_github_updated
            and (
                updated < pull.date_github_updated
                or (
                    updated == pull.date_github_updated
                    and vals["pull_state"] == "open"
                    and pull.pull_state != "open"
                )
            )
        ):
            _debug.logic("pull.stale_delivery", pull=pull.id, number=pr["number"])
            return pull
        if (
            not authoritative
            and updated
            and updated == pull.date_github_updated
            and vals["pull_state"] == pull.pull_state == "open"
            and vals["head_sha"] != pull.head_sha
        ):
            _debug.logic("pull.same_second_heads", pull=pull.id, number=pr["number"])
            try:
                with self.env.cr.savepoint():
                    owner, name = _split_repository(repository)
                    current = get_github_client(self.env).get_pull_request(
                        owner, name, pr["number"]
                    )
                    return self._upsert_from_github(
                        repository, current, authoritative=True
                    )
            except psycopg.Error, ConcurrencyError:
                raise
            except Exception:
                _logger.warning(
                    "Pull request %s#%s: two heads in one second, and GitHub "
                    "could not be asked which is current; the later delivery wins",
                    repository,
                    pr["number"],
                    exc_info=True,
                )
        pull.write(vals)
        pull._refresh_checks_state()
        pull._github_updated()
        _debug.logic(
            "pull.upserted",
            repository=repository,
            number=pr["number"],
            state=pull.pull_state,
        )
        return pull

    def _from_its_repository(self) -> bool:
        self.check_singleton()
        return same_repository(self.head_repository, self.repository)

    def _refresh_checks_state(self) -> None:
        self.invalidate_recordset(["check_ids"])
        for pull in self:
            state = pull.check_ids._aggregate_state()
            if state != pull.checks_state:
                pull.checks_state = state

    @api.model
    def _checks_moved(self, repository: str, head_sha: str) -> None:
        pulls = self.search(
            [("repository", "=", repository), ("head_sha", "=", head_sha)]
        )
        for pull in pulls:
            before = pull.checks_state
            pull._refresh_checks_state()
            if pull.checks_state != before:
                pull._github_updated()

    def _github_updated(self) -> None:
        pass

    def action_refresh(self) -> None:
        Check = self.env["integration.github.check"]
        for pull in self:
            client = get_github_client(self.env)
            owner, name = _split_repository(pull.repository)
            pull._upsert_from_github(
                pull.repository,
                client.get_pull_request(owner, name, pull.number),
                authoritative=True,
            )
            for run in client.list_check_runs(owner, name, pull.head_sha):
                Check._record(
                    pull.repository, f"check_run:{run['id']}", _check_run_vals(run)
                )
            status = client.get_combined_status(owner, name, pull.head_sha)
            for item in status.get("statuses", []):
                Check._record(
                    pull.repository,
                    f"status:{pull.head_sha}:{item['context']}",
                    _status_vals(pull.head_sha, item),
                )
            pull._refresh_checks_state()
            pull._github_updated()


def _github_datetime(value: str | None) -> Any:
    if not value:
        return False
    return fields.Datetime.to_datetime(value.replace("T", " ").removesuffix("Z"))


def _latest(payload: dict[str, Any], *keys: str) -> Any:
    stamps = [_github_datetime(payload.get(key)) for key in keys]
    return max((stamp for stamp in stamps if stamp), default=False)


def _check_run_vals(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "date_github": _latest(
            run, "completed_at", "updated_at", "started_at", "created_at"
        ),
        "name": run.get("name") or "check",
        "head_sha": run["head_sha"],
        "source": "check_run",
        "check_status": run.get("status") or "queued",
        "conclusion": run.get("conclusion") or False,
        "url": run.get("html_url"),
    }


def _workflow_run_vals(run: dict[str, Any]) -> dict[str, Any]:
    return {**_check_run_vals(run), "source": "workflow_run"}


def _status_vals(sha: str, status: dict[str, Any]) -> dict[str, Any]:
    state = status.get("state")
    return {
        "date_github": _latest(status, "updated_at", "created_at"),
        "name": status.get("context") or "status",
        "head_sha": sha,
        "source": "status",
        "check_status": "in_progress" if state == "pending" else "completed",
        "conclusion": False if state == "pending" else state,
        "url": status.get("target_url"),
    }
