from typing import Any

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.integration_github.tools import mint_installation_token
from odoo.addons.integration_github.tools.app import APP_CATEGORY

_debug = DebugLog(__name__)

# What a change needs of its repository: push a branch, open a pull request,
# read what checks say about it. Nothing else of the installation; a kind that
# only reads narrows it.
RUN_PERMISSIONS = {
    "contents": "write",
    "pull_requests": "write",
    "checks": "read",
    "metadata": "read",
}


class AgentRun(models.Model):
    _inherit = "agent.run"

    kind = fields.Selection(
        selection_add=[("github.change", "Change a Repository")],
        ondelete={"github.change": "cascade"},
    )
    github_repository = fields.Char(
        string="Repository",
        help="owner/name: the run is handed a token for this repository alone.",
    )
    github_branch = fields.Char(
        string="Branch",
        copy=False,
        readonly=True,
        help="The branch the run pushed, as it reported it on completion.",
    )
    github_pull_id = fields.Many2one(
        comodel_name="integration.github.pull",
        string="Pull Request",
        copy=False,
        readonly=True,
        ondelete="set null",
    )

    def _prepare_credentials(self) -> dict[str, Any]:
        credentials = super()._prepare_credentials()
        if not self.github_repository:
            return credentials
        app = self.env["credential.credential"].search(
            [
                ("category_id.code", "=", APP_CATEGORY),
                ("company_id", "in", (self.company_id.id, False)),
            ],
            order="company_id, write_date desc",
            limit=1,
        )
        if not app:
            self._log_event(
                "warning",
                self.env._(
                    "No GitHub App is configured: the run gets no repository token."
                ),
            )
            return credentials
        _owner, _, name = self.github_repository.partition("/")
        minted = mint_installation_token(
            self.env, app, [name], self._github_permissions()
        )
        _debug.logic("run.github_token", run=self.id, repository=self.github_repository)
        return credentials | {
            "github": {
                "token": minted.token,
                "expires_at": minted.expires_at,
                "repository": self.github_repository,
            }
        }

    def _github_permissions(self) -> dict[str, str]:
        """What this run's token may do in its repository; a kind that only
        reads narrows it."""
        return dict(RUN_PERMISSIONS)

    def _complete(self, token: object, result: object, usage: dict[str, Any]) -> bool:
        first = super()._complete(token, result, usage)
        branch = result.get("branch") if isinstance(result, dict) else None
        if first and self.github_repository and isinstance(branch, str) and branch:
            self.github_branch = branch[:250]
            self._link_github_pull()
        return first

    def _link_github_pull(self) -> None:
        """The pull request of the branch this run pushed, once both exist --
        whichever GitHub or the runner reports first."""
        self.check_singleton()
        pull = self.env["integration.github.pull"].search(
            [
                ("repository", "=", self.github_repository),
                ("head_ref", "=", self.github_branch),
            ],
            order="id desc",
            limit=1,
        )
        if pull:
            pull._attach_run(self)
