from typing import Any

from odoo import fields, models

from .error_incident_autofix_policy import AUTOFIX_KINDS

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

    def _prepare_credentials(self) -> dict[str, Any]:
        credentials = super()._prepare_credentials()
        if self.kind not in AUTOFIX_KINDS:
            return credentials
        service = self.env.ref("integration_machine_learning.service_anthropic")
        connection = self.env["integration.connection"]._resolve(
            service, company=self.company_id
        )
        key = (
            connection.credential_id._use_secret(
                "error_incident_autofix:agent", prefer="api_key"
            )
            if connection.credential_id
            else None
        )
        if not key:
            self._log_event(
                "warning",
                self.env._(
                    "No Anthropic credential: the runner's own model login is used."
                ),
            )
            return credentials
        return credentials | {"anthropic": {"api_key": key.reveal()}}
