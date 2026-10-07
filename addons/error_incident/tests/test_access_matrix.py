from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona
from odoo.addons.error_incident.models.error_incident import capture_payload


@tagged("post_install", "-at_install", "access_matrix")
class TestErrorIncidentAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "error.incident",
            "incident",
            note="tracebacks and the engineering trail are the administrators'",
            admin_a="rwcd",
            installed={"error_incident_autofix": {"admin_a": "merge hotfix"}},
        ),
        Cell("error.occurrence", "occurrence", admin_a="rwcd"),
        Cell("error.incident.rule", "rule", admin_a="rwcd"),
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
            "occurrence": incident.occurrence_ids,
            "rule": cls.env["error.incident.rule"].create({"name": "matrix"}),
        }
