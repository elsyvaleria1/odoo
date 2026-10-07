from odoo import fields, models

# Diagnosis reads the code; only a fix writes a branch and opens its pull request.
DIAGNOSE_PERMISSIONS = {"contents": "read", "metadata": "read"}


class AgentRun(models.Model):
    _inherit = "agent.run"

    kind = fields.Selection(
        selection_add=[
            ("error_incident.diagnose", "Diagnose an Incident"),
            ("error_incident.fix", "Fix an Incident"),
            ("error_incident.revision", "Report the Production Revision"),
            ("error_incident.hotfix", "Hotfix Production"),
        ],
        ondelete={
            "error_incident.diagnose": "cascade",
            "error_incident.fix": "cascade",
            "error_incident.revision": "cascade",
            "error_incident.hotfix": "cascade",
        },
    )

    def _github_permissions(self) -> dict[str, str]:
        if self.kind == "error_incident.diagnose":
            return dict(DIAGNOSE_PERMISSIONS)
        return super()._github_permissions()
