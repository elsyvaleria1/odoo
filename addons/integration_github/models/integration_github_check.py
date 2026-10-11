from typing import Any

from odoo import api, fields, models
from odoo.tools import frozendict

from ..tools import create_once, repository_domain

PASSING = frozenset({"success", "neutral", "skipped"})
_STATUS_RANK = {"queued": 0, "in_progress": 1, "completed": 2}
FAILING = frozenset(
    {"failure", "timed_out", "action_required", "startup_failure", "cancelled", "error"}
)


class IntegrationGithubCheck(models.Model):
    """One verdict GitHub holds on a commit: a check run, a workflow run or a
    commit status. A check suite is not one: a suite GitHub requests for every
    installed app stays queued forever for an app that never runs."""

    _name = "integration.github.check"
    _description = "GitHub Check"
    _order = "date_updated desc, id desc"
    _access_anchors = frozendict({"company": ""})

    name = fields.Char(
        required=True,
    )
    repository = fields.Char(
        index=True,
        required=True,
        help="owner/name",
    )
    head_sha = fields.Char(
        string="Commit",
        index=True,
        required=True,
    )
    source = fields.Selection(
        selection=[
            ("check_run", "Check Run"),
            ("workflow_run", "Workflow Run"),
            ("status", "Commit Status"),
        ],
        required=True,
    )
    external_ref = fields.Char(
        string="Reference",
        required=True,
        help="What GitHub names it by, unique in the repository.",
    )
    check_status = fields.Selection(
        selection=[
            ("queued", "Queued"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
        ],
        string="Status",
        required=True,
    )
    conclusion = fields.Char()
    url = fields.Char(
        string="URL",
    )
    date_updated = fields.Datetime(
        string="Updated",
    )
    date_github = fields.Datetime(
        string="Updated on GitHub",
        help="When GitHub last changed the check, as the newest delivery said: an "
        "older delivery, redelivered or reordered, changes nothing.",
    )

    _external_ref_uniq = models.Constraint(
        "UNIQUE(repository, external_ref)",
        "GitHub reports a check once per repository.",
    )

    @api.model
    def _record(
        self, repository: str, external_ref: str, vals: dict[str, Any]
    ) -> IntegrationGithubCheck:
        vals = {**vals, "date_updated": fields.Datetime.now()}
        domain = [
            *repository_domain("repository", repository),
            ("external_ref", "=", external_ref),
        ]
        check = self.search(domain, limit=1)
        if not check:
            return create_once(
                self,
                domain,
                {**vals, "repository": repository, "external_ref": external_ref},
            )
        stamp = fields.Datetime.to_datetime(vals.get("date_github"))
        if (
            stamp
            and check.date_github
            and (
                stamp < check.date_github
                or (
                    stamp == check.date_github
                    and _STATUS_RANK.get(vals.get("check_status"), 0)
                    < _STATUS_RANK.get(check.check_status, 0)
                )
            )
        ):
            return check
        check.write(vals)
        return check

    def _aggregate_state(self) -> str:
        if not self:
            return "none"
        if any(check.conclusion in FAILING for check in self):
            return "failure"
        if all(
            check.check_status == "completed" and check.conclusion in PASSING
            for check in self
        ):
            return "success"
        return "pending"
