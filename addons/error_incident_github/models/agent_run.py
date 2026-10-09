from odoo import models


class AgentRun(models.Model):
    _inherit = "agent.run"

    def _notify_owner(self) -> None:
        run = self
        if self.res_model == "error.incident":
            run = self.with_privilege(
                "error_incident_github.privilege_follow_pulls",
                reason="the incident a run works for hears how it ended",
            )
        super(AgentRun, run)._notify_owner()
