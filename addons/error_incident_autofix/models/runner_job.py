from odoo import fields, models

DIAGNOSE_PERMISSIONS = {"contents": "read", "metadata": "read"}


class RunnerJob(models.Model):
    _inherit = "runner.job"

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

    def _notify_owner(self) -> None:
        run = self
        if self.res_model == "error.incident":
            run = self.with_privilege(
                "error_incident_autofix.privilege_report_runner_job",
                reason="a runner job's end moves the incident it works for",
            )
        super(RunnerJob, run)._notify_owner()
