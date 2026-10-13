from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestMixinReportSqlAccessMatrix(AccessMatrixCase):
    personas = {
        "internal_a": Persona("base.group_user"),
        "admin_a": Persona("base.group_system"),
        "admin_b": Persona("base.group_system", company="b"),
    }
    cells = (
        Cell(
            "report.rolling.state",
            "state",
            note="written by the reports themselves under sudo; an administrator "
            "of any company may read whether a report waits for a full rebuild",
            admin_a="r",
            admin_b="r",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        state = cls.env["report.rolling.state"].create(
            {"model": "mixin.report.sql.matrix", "stale": True}
        )
        return {"state": state}
