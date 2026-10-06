from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

THROUGH_THE_ENGINE = (
    "a user reaches their own account only through the engine, which elevates "
    "to read and write it; nobody but an administrator touches one directly"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestCalendarSyncAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "calendar.sync.account",
            "own_account",
            note=THROUGH_THE_ENGINE,
            admin_a="rwcd",
        ),
        Cell(
            "calendar.sync.account",
            "other_account",
            note=THROUGH_THE_ENGINE,
            admin_a="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        # no provider is installed with the engine alone: a fake one, for the
        # class, as what a test creates is flushed after its own patches
        Account = cls.env["calendar.sync.account"]
        cls.startClassPatcher(
            patch.object(
                type(Account)._fields["provider"], "_selection", {"fake": "Fake"}
            )
        )
        other = cls.env["res.users"].create({"name": "Other", "login": "matrix_other"})
        return {
            "own_account": Account.create(
                {"user_id": cls.users["employee_a"].id, "provider": "fake"}
            ),
            "other_account": Account.create({"user_id": other.id, "provider": "fake"}),
        }
