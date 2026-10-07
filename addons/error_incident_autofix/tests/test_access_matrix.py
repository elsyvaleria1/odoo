from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestAutofixAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
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
    )

    @classmethod
    def build(cls):
        return {
            "policy": cls.env.ref("error_incident_autofix.policy_default"),
            "repository": cls.env.ref("error_incident_autofix.repository_odoo"),
            "prompt": cls.env.ref("error_incident_autofix.prompt_diagnose_v1"),
        }
