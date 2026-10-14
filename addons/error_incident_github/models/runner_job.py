from odoo import models


class RunnerJob(models.Model):
    _inherit = "runner.job"

    def _notify_owner(self) -> None:
        run = self
        if self.res_model == "error.incident":
            run = self.with_privilege(
                "error_incident_github.privilege_follow_pulls",
                reason="the incident a run works for hears how it ended",
            )
        super(RunnerJob, run)._notify_owner()
