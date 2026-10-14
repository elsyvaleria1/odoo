from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class IntegrationGithubPull(models.Model):
    _inherit = "integration.github.pull"

    runner_job_id = fields.Many2one(
        comodel_name="runner.job",
        string="Job",
        readonly=True,
        ondelete="set null",
        help="The job that pushed this branch.",
    )

    def _github_updated(self) -> None:
        super()._github_updated()
        runs = self._runs_of_branches()
        for pull in self:
            run = runs.get((pull.repository.lower(), pull.head_ref))
            if run and not pull.runner_job_id:
                pull._attach_run(run)

    def _runs_of_branches(self) -> dict[tuple[str, str], models.BaseModel]:
        unlinked = self.filtered(
            lambda pull: (
                not pull.runner_job_id and pull.head_ref and pull._from_its_repository()
            )
        )
        if not unlinked:
            return {}
        runs = self.env["runner.job"].search(
            [("github_branch", "in", list(set(unlinked.mapped("head_ref"))))],
            order="id",
        )
        return {
            (run.github_repository.lower(), run.github_branch): run
            for run in runs
            if run.github_repository
        }

    def _attach_run(self, run: models.BaseModel) -> None:
        self.check_singleton()
        self.runner_job_id = run
        run.github_pull_id = self
        _debug.logic("pull.linked", pull=self.id, run=run.id)
        self._run_attached(run)

    def _run_attached(self, run: models.BaseModel) -> None:
        pass
