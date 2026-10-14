from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestRunnerAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "runner.machine",
            "runner",
            note="a runner is a credential holder: administrators only",
            admin_a="rwcd",
        ),
        Cell("runner.job", "run", admin_a="rwcd"),
        Cell(
            "runner.job.event",
            "event",
            note="append-only: written by the protocol, read by administrators",
            admin_a="r",
        ),
        Cell("runner.capability", "capability", admin_a="rwcd"),
    )

    @classmethod
    def create_matrix_records(cls):
        capability = cls.env.ref("runner.capability_sandbox")
        run = cls.env["runner.job"].create(
            {"name": "matrix", "kind": "probe", "capability_id": capability.id}
        )
        run._log_event("system", "matrix")
        return {
            "runner": cls.env["runner.machine"].create({"name": "matrix"}),
            "run": run,
            "event": run.event_ids,
            "capability": capability,
        }
