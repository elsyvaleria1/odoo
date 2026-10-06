from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class IntegrationGithubPull(models.Model):
    _inherit = "integration.github.pull"

    agent_run_id = fields.Many2one(
        comodel_name="agent.run",
        string="Run",
        readonly=True,
        ondelete="set null",
        help="The run that pushed this branch.",
    )
    incident_id = fields.Many2one(
        comodel_name="error.incident",
        string="Incident",
        index=True,
        readonly=True,
        ondelete="set null",
    )
    incident_notice = fields.Char(
        copy=False,
        readonly=True,
        help="The state the incident was last told of, so it hears each change once.",
    )

    def _github_updated(self) -> None:
        super()._github_updated()
        runs = self._runs_of_branches()
        for pull in self:
            run = runs.get((pull.repository, pull.head_ref))
            if run and not pull.agent_run_id:
                pull._attach_run(run)
            pull._tell_incident()

    def _runs_of_branches(self) -> dict[tuple[str, str], models.BaseModel]:
        """The latest run that pushed each unlinked pull request's branch."""
        unlinked = self.filtered(lambda pull: not pull.agent_run_id and pull.head_ref)
        if not unlinked:
            return {}
        runs = self.env["agent.run"].search(
            [
                ("github_repository", "in", list(set(unlinked.mapped("repository")))),
                ("github_branch", "in", list(set(unlinked.mapped("head_ref")))),
            ],
            order="id",
        )
        return {(run.github_repository, run.github_branch): run for run in runs}

    def _attach_run(self, run: models.BaseModel) -> None:
        self.check_singleton()
        incident = (
            self.env["error.incident"].browse(run.res_id).exists()
            if run.res_model == "error.incident"
            else self.env["error.incident"]
        )
        self.write({"agent_run_id": run.id, "incident_id": incident.id})
        run.github_pull_id = self
        _debug.logic("pull.linked", pull=self.id, run=run.id, incident=incident.id)
        self._tell_incident()

    def _tell_incident(self) -> None:
        self.check_singleton()
        notice = f"{self.pull_state}/{self.checks_state}"
        if not self.incident_id or notice == self.incident_notice:
            return
        self.incident_notice = notice
        self.incident_id.message_post(body=self._incident_message())

    def _incident_message(self) -> str:
        reference = f"{self.repository}#{self.number}"
        if self.pull_state == "merged":
            return self.env._("Pull request %(pull)s was merged.", pull=reference)
        if self.pull_state == "closed":
            return self.env._(
                "Pull request %(pull)s was closed without merging.", pull=reference
            )
        match self.checks_state:
            case "failure":
                return self.env._("The checks of %(pull)s fail.", pull=reference)
            case "success":
                return self.env._("The checks of %(pull)s pass.", pull=reference)
            case "pending":
                return self.env._("The checks of %(pull)s are running.", pull=reference)
        return self.env._("Pull request %(pull)s is open.", pull=reference)
