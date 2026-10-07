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
            note="an approver reads the incident it decides on; asking to merge or "
            "hotfix is an administrator's",
            admin_a="rwcd merge hotfix",
            approver_a="r",
        ),
        Cell(
            "integration.github.pull",
            "pull",
            note="an approver reads the fix it decides on",
            admin_a="rwcd",
            approver_a="r",
        ),
    )

    @classmethod
    def build(cls):
        try:
            raise ValueError("matrix")
        except ValueError as exc:
            payload = capture_payload(exc, "request")
        incident = cls.env["error.incident"].browse(
            cls.env["error.incident"]._capture(payload)
        )
        return {
            "incident": incident,
            "pull": cls.env["integration.github.pull"].create(
                {"name": "matrix", "repository": "o/r", "number": 1}
            ),
            "policy": cls.env.ref("error_incident_autofix.policy_default"),
            "repository": cls.env.ref("error_incident_autofix.repository_odoo"),
            "prompt": cls.env.ref("error_incident_autofix.prompt_diagnose_v1"),
        }
