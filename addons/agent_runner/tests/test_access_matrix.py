from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestAgentRunnerAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "agent.runner",
            "runner",
            note="a runner is a credential holder: administrators only",
            admin_a="rwcd",
        ),
        Cell("agent.run", "run", admin_a="rwcd"),
        Cell(
            "agent.run.event",
            "event",
            note="append-only: written by the protocol, read by administrators",
            admin_a="r",
        ),
        Cell("agent.capability", "capability", admin_a="rwcd"),
    )

    @classmethod
    def create_matrix_records(cls):
        capability = cls.env.ref("agent_runner.capability_sandbox")
        run = cls.env["agent.run"].create(
            {"name": "matrix", "kind": "probe", "capability_id": capability.id}
        )
        run._log_event("system", "matrix")
        return {
            "runner": cls.env["agent.runner"].create({"name": "matrix"}),
            "run": run,
            "event": run.event_ids,
            "capability": capability,
        }
