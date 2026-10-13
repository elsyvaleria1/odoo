from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestGithubAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "integration.github.webhook",
            "hook",
            note="a webhook holds a signing secret: administrators only",
            admin_a="rwcd",
        ),
        Cell("integration.github.pull", "pull", admin_a="rwcd"),
        Cell("integration.github.check", "check", admin_a="rwcd"),
    )

    @classmethod
    def create_matrix_records(cls):
        return {
            "hook": cls.env["integration.github.webhook"].create({"name": "matrix"}),
            "pull": cls.env["integration.github.pull"].create(
                {"name": "matrix", "repository": "o/r", "number": 1}
            ),
            "check": cls.env["integration.github.check"].create(
                {
                    "name": "matrix",
                    "repository": "o/r",
                    "head_sha": "a" * 40,
                    "source": "status",
                    "external_ref": "status:matrix",
                    "check_status": "completed",
                }
            ),
        }
