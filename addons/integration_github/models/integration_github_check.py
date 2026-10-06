from typing import Any

from odoo import api, fields, models
from odoo.tools import frozendict

# What a check concludes, as GitHub spells it across check runs, workflow runs and
# commit statuses.
PASSING = frozenset({"success", "neutral", "skipped"})
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

    _external_ref_uniq = models.Constraint(
        "UNIQUE(repository, external_ref)",
        "GitHub reports a check once per repository.",
    )

    @api.model
    def _record(
        self, repository: str, external_ref: str, vals: dict[str, Any]
    ) -> IntegrationGithubCheck:
        """Create the check, or move it on: GitHub redelivers and reorders, and a
        re-run reuses a check run's id."""
        vals = {**vals, "date_updated": fields.Datetime.now()}
        check = self.search(
            [("repository", "=", repository), ("external_ref", "=", external_ref)],
            limit=1,
        )
        if check:
            check.write(vals)
            return check
        return self.create(
            {**vals, "repository": repository, "external_ref": external_ref}
        )

    def _aggregate_state(self) -> str:
        """``none``, ``pending``, ``failure`` or ``success`` for these checks of
        one commit: any failure fails it, anything unfinished keeps it pending."""
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
