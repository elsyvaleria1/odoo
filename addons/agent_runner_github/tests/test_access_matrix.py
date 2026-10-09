from odoo.libs.json import dumps as json_dumps
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

LINKED = (
    "a run's lease and completion reach it through "
    "agent_runner_github.privilege_link_runs, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestAgentRunnerGithubAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "vault_a": Persona("credential.group_credential_user"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "credential.credential",
            "app",
            note=LINKED + "; its secrets stay behind the credential's own use",
            vault_a="rwc",
        ),
        Cell(
            "credential.category",
            "app_category",
            note=LINKED,
            vault_a="r",
        ),
        Cell(
            "integration.github.pull",
            "pull",
            note=LINKED,
            admin_a="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        category = cls.env.ref("integration_github.credential_category_github_app")
        return {
            "app": cls.env["credential.credential"].create(
                {
                    "name": "Matrix GitHub App",
                    "category_id": category.id,
                    "company_id": cls.companies["a"].id,
                    "credential_data": json_dumps(
                        {"app_id": "1", "private_key": "pem", "installation_id": "9"}
                    ),
                }
            ),
            "app_category": category,
            "pull": cls.env["integration.github.pull"].create(
                {"name": "matrix", "repository": "o/r", "number": 1}
            ),
        }
