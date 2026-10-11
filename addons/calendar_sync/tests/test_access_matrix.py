from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

THROUGH_THE_ENGINE = (
    "a user reaches their own account and its links only through the engine, "
    "which elevates to read and write them; nobody but an administrator "
    "touches one directly"
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
        Cell(
            "calendar.sync.link",
            "own_link",
            note=THROUGH_THE_ENGINE,
            admin_a="rwcd",
        ),
        Cell(
            "calendar.sync.link",
            "other_link",
            note=THROUGH_THE_ENGINE,
            admin_a="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        Account = cls.env["calendar.sync.account"]
        cls.startClassPatcher(
            patch.object(
                type(Account)._fields["provider"], "_selection", {"fake": "Fake"}
            )
        )
        other = cls.env["res.users"].create({"name": "Other", "login": "matrix_other"})
        own = Account.create(
            {"user_id": cls.users["employee_a"].id, "provider": "fake"}
        )
        others = Account.create({"user_id": other.id, "provider": "fake"})
        Link = cls.env["calendar.sync.link"]
        return {
            "own_account": own,
            "other_account": others,
            "own_link": Link.create({"account_id": own.id, "remote_id": "own"}),
            "other_link": Link.create({"account_id": others.id, "remote_id": "other"}),
        }
