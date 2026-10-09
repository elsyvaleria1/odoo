from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona
from odoo.addons.error_incident.models.error_incident import capture_payload

FOLLOWED = (
    "an incident's run reaches it through "
    "error_incident_github.privilege_follow_pulls, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestErrorIncidentGithubAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell("error.incident", "incident", note=FOLLOWED, admin_a="rwcd"),
        Cell("integration.github.pull", "pull", note=FOLLOWED, admin_a="rwcd"),
    )

    @classmethod
    def build(cls):
        try:
            raise ValueError("matrix")
        except ValueError as exc:
            payload = capture_payload(exc, "request")
        Incident = cls.env["error.incident"]
        return {
            "incident": Incident.browse(Incident._capture(payload)),
            "pull": cls.env["integration.github.pull"].create(
                {"name": "matrix", "repository": "o/r", "number": 1}
            ),
        }
