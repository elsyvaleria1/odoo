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
            "integration.github.pull",
            "pull",
            note="an approver reads the pull request of an incident put to a "
            "decision, not this one",
            admin_a="rwcd",
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
