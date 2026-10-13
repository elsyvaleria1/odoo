from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona
from odoo.addons.error_incident.models.error_incident import capture_payload


@tagged("post_install", "-at_install", "access_matrix")
class TestAutofixAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "approver_a": Persona("error_incident_autofix.group_autofix_approver"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "error.incident.autofix.policy",
            "policy",
            note="what the agents may do to the code: administrators only",
            admin_a="rwcd",
        ),
        Cell("error.incident.autofix.repository", "repository", admin_a="rwcd"),
        Cell("error.incident.autofix.prompt", "prompt", admin_a="rwcd"),
        Cell(
            "error.incident",
            "incident",
            note="an approver reads an incident only while it is put to a decision "
            "(test_delivery), not this one; asking to merge or hotfix is an "
            "administrator's",
            admin_a="rwcd merge hotfix",
        ),
        Cell(
            "error.occurrence",
            "occurrence",
            note="a fix run is told of it through "
            "error_incident_autofix.privilege_report_agent_run, which no user holds",
            admin_a="rwcd",
        ),
        Cell(
            "agent.run",
            "run",
            note="a diagnosis hands a defect to a fix run through "
            "error_incident_autofix.privilege_report_agent_run, which no user holds",
            admin_a="rwcd",
        ),
        Cell(
            "integration.github.pull",
            "pull",
            note="an approver reads the pull request of an incident put to a "
            "decision, not this one",
            admin_a="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        try:
            raise ValueError("matrix")
        except ValueError as exc:
            payload = capture_payload(exc, "request")
        incident = cls.env["error.incident"].browse(
            cls.env["error.incident"]._capture(payload)
        )
        return {
            "incident": incident,
            "occurrence": incident.occurrence_ids[:1],
            "run": cls.env["agent.run"].create(
                {
                    "name": "matrix",
                    "kind": "error_incident.diagnose",
                    "capability_id": cls.env.ref("agent_runner.capability_sandbox").id,
                    "res_model": "error.incident",
                    "res_id": incident.id,
                }
            ),
            "pull": cls.env["integration.github.pull"].create(
                {"name": "matrix", "repository": "o/r", "number": 1}
            ),
            "policy": cls.env.ref("error_incident_autofix.policy_default"),
            "repository": cls.env.ref("error_incident_autofix.repository_odoo"),
            "prompt": cls.env.ref("error_incident_autofix.prompt_diagnose_v1"),
        }
