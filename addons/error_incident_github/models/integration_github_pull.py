from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class IntegrationGithubPull(models.Model):
    _inherit = "integration.github.pull"

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
        for pull in self:
            pull._tell_incident()

    def _run_attached(self, run: models.BaseModel) -> None:
        super()._run_attached(run)
        pull = self.with_privilege(
            "error_incident_github.privilege_follow_pulls",
            reason="the pull request of an incident's run is followed on the incident",
        )
        if run.res_model == "error.incident":
            pull.incident_id = pull.env["error.incident"].browse(run.res_id).exists()
            _debug.logic(
                "pull.incident_linked", pull=pull.id, incident=pull.incident_id.id
            )
        pull._tell_incident()

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
