from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestDocumentAccessMatrix(AccessMatrixCase):
    personas = {
        "owner_a": Persona("document.group_documents_user"),
        "member_a": Persona("document.group_documents_user"),
        "editor_a": Persona("document.group_documents_user"),
        "stranger_a": Persona("document.group_documents_user"),
        "manager_a": Persona("document.group_documents_manager"),
        "employee_a": Persona(),
        "user_b": Persona("document.group_documents_user", company="b"),
        "portal_c": Persona(portal="customer_c"),
    }
    cells = (
        Cell(
            "document.document",
            "folder_team",
            owner_a="rwcd",
            member_a="rc",
            editor_a="rwcd",
            stranger_a="c",
            manager_a="c",
            employee_a="c",
            user_b="c",
            portal_c="rc",
        ),
        Cell(
            "document.document",
            "doc_team",
            owner_a="rwcd",
            member_a="r",
            editor_a="rwcd",
            portal_c="r",
        ),
        Cell(
            "document.document",
            "folder_internal",
            owner_a="rwcd",
            member_a="rc",
            editor_a="rc",
            stranger_a="rc",
            manager_a="rwcd",
            employee_a="rc",
            user_b="c",
            portal_c="c",
        ),
        Cell(
            "document.document",
            "doc_private",
            owner_a="rwcd",
            member_a="c",
            editor_a="c",
            stranger_a="c",
            manager_a="c",
            employee_a="c",
            user_b="c",
            portal_c="c",
        ),
        Cell(
            "document.document",
            "doc_b",
            owner_a="c",
            member_a="c",
            editor_a="c",
            stranger_a="c",
            manager_a="c",
            employee_a="c",
            user_b="rwcd",
            portal_c="c",
        ),
        Cell(
            "document.access",
            "access_member",
            owner_a="rwcd",
            member_a="r",
            editor_a="r",
            portal_c="r",
        ),
        Cell(
            "document.access.log",
            "access_log",
        ),
        Cell(
            "document.access.tracking",
            "tracking",
        ),
        # reached only through a document, by code holding the privilege:
        # not even the document's owner reads the row
        Cell(
            "document.thumbnail",
            "thumbnail",
        ),
        Cell(
            "document.tag",
            "tag",
            owner_a="r",
            member_a="r",
            editor_a="r",
            stranger_a="r",
            manager_a="rwcd",
            employee_a="r",
            user_b="r",
        ),
        Cell(
            "document.type",
            "doc_type",
            owner_a="r",
            member_a="r",
            editor_a="r",
            stranger_a="r",
            manager_a="rwcd",
            employee_a="r",
        ),
        Cell(
            "mail.activity.plan",
            "activity_plan",
            owner_a="r",
            member_a="r",
            editor_a="r",
            stranger_a="r",
            manager_a="rwcd",
            employee_a="r",
            user_b="r",
        ),
        Cell(
            "mail.activity.plan",
            "activity_plan_other",
            owner_a="r",
            member_a="r",
            editor_a="r",
            stranger_a="r",
            manager_a="r",
            employee_a="r",
            user_b="r",
        ),
        Cell(
            "mail.activity.plan.template",
            "activity_plan_template",
            owner_a="r",
            member_a="r",
            editor_a="r",
            stranger_a="r",
            manager_a="rwcd",
            employee_a="r",
            user_b="r",
        ),
    )

    @classmethod
    def build(cls):
        env = cls.env
        a, b = cls.companies["a"], cls.companies["b"]
        users = cls.users
        documents = env["document.document"]

        def grant(persona, role):
            return Command.create(
                {"partner_id": users[persona].partner_id.id, "role": role}
            )

        folder_team = documents.create(
            {
                "type": "folder",
                "name": "matrix team",
                "owner_id": users["owner_a"].id,
                "company_id": a.id,
                "access_internal": "none",
                "access_ids": [
                    grant("member_a", "view"),
                    grant("editor_a", "edit"),
                    grant("portal_c", "view"),
                ],
            }
        )
        doc_team = documents.create(
            {
                "type": "binary",
                "name": "matrix team file",
                "folder_id": folder_team.id,
                "owner_id": users["owner_a"].id,
                "company_id": a.id,
            }
        )
        folder_internal = documents.create(
            {
                "type": "folder",
                "name": "matrix internal",
                "owner_id": users["owner_a"].id,
                "company_id": a.id,
                "access_internal": "view",
            }
        )
        doc_private = documents.create(
            {
                "type": "binary",
                "name": "matrix private",
                "owner_id": users["owner_a"].id,
                "company_id": a.id,
                "access_internal": "none",
            }
        )
        doc_b = documents.create(
            {
                "type": "binary",
                "name": "matrix b",
                "owner_id": users["user_b"].id,
                "company_id": b.id,
                "access_internal": "view",
            }
        )
        plan = env["mail.activity.plan"].create(
            {"name": "matrix document plan", "res_model": "document.document"}
        )
        activity_type = env["mail.activity.type"].search([], limit=1)
        return {
            "folder_team": folder_team,
            "doc_team": doc_team,
            "folder_internal": folder_internal,
            "doc_private": doc_private,
            "doc_b": doc_b,
            "access_member": folder_team.access_ids.filtered(
                lambda access: access.partner_id == users["member_a"].partner_id
            ),
            "access_log": env["document.access.log"].create(
                {
                    "document_id": doc_team.id,
                    "partner_id": users["member_a"].partner_id.id,
                    "action": "view",
                    "access_date": "2026-09-01 10:00:00",
                }
            ),
            "tracking": env["document.access.tracking"].create(
                {
                    "user_id": users["owner_a"].id,
                    "changes": {"matrix": 1},
                    "documents": {"matrix": 1},
                }
            ),
            "thumbnail": env["document.thumbnail"].create(
                {"document_id": doc_team.id, "state": "error"}
            ),
            "tag": env["document.tag"].create({"name": "matrix tag"}),
            "doc_type": env["document.type"].create(
                {"name": "matrix type", "code": "MATRIX", "company_id": a.id}
            ),
            "activity_plan": plan,
            "activity_plan_other": env["mail.activity.plan"].create(
                {"name": "matrix partner plan", "res_model": "res.partner"}
            ),
            "activity_plan_template": env["mail.activity.plan.template"].create(
                {
                    "plan_id": plan.id,
                    "activity_type_id": activity_type.id,
                    "summary": "matrix",
                }
            ),
        }
