from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestMailInboxAccessMatrix(AccessMatrixCase):
    personas = {
        "reader_a": Persona("base.group_user"),
        "outsider_a": Persona("base.group_user"),
        "admin_a": Persona("base.group_system"),
    }
    cells = (
        Cell(
            "mail.inbox",
            "inbox_shared",
            note="an inbox is read by its users and managed by administrators",
            reader_a="r",
            admin_a="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        domain = cls.env["mail.alias.domain"].create(
            {"name": "matrix-inbox.example.com"}
        )
        inbox = cls.env["mail.inbox"].create(
            {
                "name": "Matrix",
                "kind": "shared",
                "alias_name": "matrix",
                "alias_domain_id": domain.id,
                "company_id": cls.companies["a"].id,
                "user_ids": [Command.set(cls.users["reader_a"].ids)],
            }
        )
        return {"inbox_shared": inbox}
