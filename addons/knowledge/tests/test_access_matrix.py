from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestKnowledgeAccessMatrix(AccessMatrixCase):
    personas = {
        "writer_a": Persona(),
        "reader_a": Persona(),
        "employee_a": Persona(),
        "admin_a": Persona("base.group_system"),
        "employee_b": Persona(company="b"),
        "portal_c": Persona(portal="customer_c"),
        "portal_d": Persona(portal="customer_d"),
    }
    cells = (
        Cell(
            "knowledge.article",
            "workspace",
            writer_a="rwc",
            reader_a="rwc",
            employee_a="rwc",
            admin_a="rwcd",
            employee_b="rwc",
        ),
        Cell(
            "knowledge.article",
            "workspace_read",
            writer_a="rwc",
            reader_a="r",
            employee_a="r",
            admin_a="rwcd",
            employee_b="r",
        ),
        Cell(
            "knowledge.article",
            "private",
            writer_a="rwc",
            admin_a="rwcd",
        ),
        Cell(
            "knowledge.article",
            "shared",
            writer_a="rwc",
            reader_a="r",
            admin_a="rwcd",
            portal_c="r",
        ),
        Cell(
            "knowledge.article",
            "child",
            writer_a="rwc",
            reader_a="r",
            admin_a="rwcd",
            portal_c="r",
        ),
        Cell(
            "knowledge.article.member",
            "member_reader",
            writer_a="r",
            reader_a="r",
            admin_a="rwcd",
            portal_c="r",
        ),
        Cell(
            "knowledge.article.favorite",
            "favorite",
            reader_a="rwcd",
            admin_a="rwcd",
        ),
        Cell(
            "knowledge.article.stage",
            "stage",
            writer_a="rwcd",
            reader_a="r",
            admin_a="rwcd",
            portal_c="r",
        ),
        Cell(
            "knowledge.article.thread",
            "thread",
            writer_a="rwc",
            reader_a="r",
            portal_c="r",
        ),
        Cell(
            "knowledge.article.template.category",
            "template_category",
            writer_a="r",
            reader_a="r",
            employee_a="r",
            admin_a="rwcd",
            employee_b="r",
        ),
        Cell(
            "knowledge.cover",
            "cover",
            writer_a="rwcd",
            reader_a="rwcd",
            employee_a="rwcd",
            admin_a="rwcd",
            employee_b="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        users = cls.users
        articles = env["knowledge.article"]

        def member(persona, permission):
            return (
                0,
                0,
                {"partner_id": users[persona].partner_id.id, "permission": permission},
            )

        workspace = articles.create(
            {"name": "matrix workspace", "internal_permission": "write"}
        )
        workspace_read = articles.create(
            {
                "name": "matrix read workspace",
                "internal_permission": "read",
                "article_member_ids": [member("writer_a", "write")],
            }
        )
        private = articles.create(
            {
                "name": "matrix private",
                "internal_permission": "none",
                "article_member_ids": [member("writer_a", "write")],
            }
        )
        shared = articles.create(
            {
                "name": "matrix shared",
                "internal_permission": "none",
                "article_member_ids": [
                    member("writer_a", "write"),
                    member("reader_a", "read"),
                    member("portal_c", "read"),
                ],
            }
        )
        child = articles.create({"name": "matrix child", "parent_id": shared.id})
        stage = env["knowledge.article.stage"].create(
            {"name": "matrix stage", "parent_id": shared.id}
        )
        return {
            "workspace": workspace,
            "workspace_read": workspace_read,
            "private": private,
            "shared": shared,
            "child": child,
            "member_reader": shared.article_member_ids.filtered(
                lambda m: m.partner_id == users["reader_a"].partner_id
            ),
            "favorite": env["knowledge.article.favorite"].create(
                {"article_id": shared.id, "user_id": users["reader_a"].id}
            ),
            "stage": stage,
            "thread": env["knowledge.article.thread"].create({"article_id": shared.id}),
            "template_category": env["knowledge.article.template.category"].create(
                {"name": "matrix category"}
            ),
            "cover": env["knowledge.cover"].create(
                {
                    "attachment_id": env["ir.attachment"]
                    .create({"name": "matrix.png", "raw": b"matrix"})
                    .id
                }
            ),
        }
