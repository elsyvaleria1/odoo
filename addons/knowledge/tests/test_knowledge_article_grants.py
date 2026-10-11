from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import KnowledgeCommon


@tagged("post_install", "-at_install", "knowledge_grants")
class TestKnowledgeArticleGrants(KnowledgeCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_employee = cls.env.ref("base.group_user")
        cls.workspace = cls.env["knowledge.article"].create(
            {
                "name": "Workspace",
                "internal_permission": "write",
                "article_member_ids": [
                    Command.create(
                        {
                            "partner_id": cls.partner_employee_manager.id,
                            "permission": "write",
                        }
                    )
                ],
            }
        )
        cls.child = cls.env["knowledge.article"].create(
            {"name": "Child", "parent_id": cls.workspace.id}
        )

    def test_the_employees_permission_is_a_grant_that_reaches_down(self):
        grant = self.workspace.access_grant_ids.filtered("group_id")
        self.assertEqual(
            grant.mapped(lambda g: (g.group_id, g.partner_id, g.permission)),
            [(self.group_employee, self.env["res.partner"], "write")],
        )
        self.assertEqual(
            self.workspace.article_member_ids.partner_id,
            self.partner_employee_manager,
            "a grant to the employees is not a member",
        )
        self.assertFalse(self.child.access_grant_ids, "nothing is copied down")
        self.assertFalse(self.child.internal_permission)
        self.assertEqual(self.child.inherited_permission, "write")
        self.assertEqual(self.child.inherited_permission_parent_id, self.workspace)
        self.assertEqual(
            self.child.with_user(self.user_employee2).user_permission, "write"
        )
        self.assertEqual(
            self.child.with_user(self.user_portal).user_permission,
            "none",
            "the employees' grant does not reach a portal user",
        )

        self.workspace.internal_permission = "read"
        self.assertEqual(self.child.inherited_permission, "read")
        self.assertEqual(
            self.child.with_user(self.user_employee2).user_permission, "read"
        )

    def test_the_rows_reach_articles_through_the_access_graph(self):
        Access = self.env["ir.access"].with_user(self.user_employee2)
        reason = "a grant on it or on the records above it"
        for model, operation in (
            ("knowledge.article", "read"),
            ("knowledge.article", "write"),
            ("knowledge.article.thread", "read"),
        ):
            with self.subTest(model=model, operation=operation):
                lines = Access._explain(model, operation)
                self.assertTrue(any(reason in line for line in lines), lines)

    def test_a_group_grant_reaches_the_articles_below(self):
        team = self.env["res.groups"].create({"name": "Knowledge team"})
        self.user_employee2.group_ids = [Command.link(team.id)]
        private = self.env["knowledge.article"].create(
            {
                "name": "Members only",
                "internal_permission": "none",
                "article_member_ids": [
                    Command.create(
                        {
                            "partner_id": self.partner_employee_manager.id,
                            "permission": "write",
                        }
                    )
                ],
            }
        )
        below = self.env["knowledge.article"].create(
            {"name": "Below", "parent_id": private.id}
        )
        Article = self.env["knowledge.article"].with_user(self.user_employee2)
        self.assertFalse(Article.search([("id", "in", (private | below).ids)]))
        self.env["knowledge.article.member"].create(
            {"article_id": private.id, "group_id": team.id, "permission": "read"}
        )
        self.assertEqual(
            Article.search([("id", "in", (private | below).ids)]), private | below
        )
        self.assertEqual(below.with_user(self.user_employee2).user_permission, "read")

    def test_no_access_is_no_grant_and_stops_what_comes_from_above(self):
        shared = self.env["knowledge.article"].create(
            {
                "name": "Shared",
                "internal_permission": "none",
                "article_member_ids": [
                    Command.create(
                        {
                            "partner_id": self.partner_employee_manager.id,
                            "permission": "write",
                        }
                    ),
                    Command.create(
                        {"partner_id": self.partner_employee2.id, "permission": "read"}
                    ),
                ],
            }
        )
        below = self.env["knowledge.article"].create(
            {"name": "Below", "parent_id": shared.id}
        )
        below.invite_members(self.partner_employee2, "none")
        self.assertTrue(below.is_desynchronized)
        self.assertEqual(
            {m.partner_id: m.permission for m in below.article_member_ids},
            {self.partner_employee_manager: "write"},
            "the other members are kept, and no row takes access away",
        )
        self.assertEqual(below.with_user(self.user_employee2).user_permission, "none")
        self.assertEqual(shared.with_user(self.user_employee2).user_permission, "read")


@tagged("post_install", "-at_install", "knowledge_grants")
class TestKnowledgeArticleLabels(KnowledgeCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.confidential = cls.env["ir.access.class"].create(
            {"name": "knowledge.test_confidential"}
        )
        readers = cls.env["res.groups"].create({"name": "Confidential readers"})
        writers = cls.env["res.groups"].create({"name": "Confidential writers"})
        cls.env["ir.access"].create(
            [
                {
                    "name": "confidential: readers read",
                    "class_id": cls.confidential.id,
                    "group_id": readers.id,
                    "kind": "permission",
                    "operation": "r",
                },
                {
                    "name": "confidential: writers write",
                    "class_id": cls.confidential.id,
                    "group_id": writers.id,
                    "kind": "permission",
                    "operation": "ru",
                },
            ]
        )
        cls.user_employee.group_ids = [Command.link(readers.id)]
        cls.user_employee_manager.group_ids = [Command.link(writers.id)]
        cls.workspace = cls.env["knowledge.article"].create(
            {
                "name": "Workspace",
                "internal_permission": "write",
                "article_member_ids": [
                    Command.create(
                        {
                            "partner_id": cls.partner_employee_manager.id,
                            "permission": "write",
                        }
                    )
                ],
            }
        )
        cls.board = cls.env["knowledge.article"].create(
            {"name": "Board", "parent_id": cls.workspace.id}
        )
        cls.minutes = cls.env["knowledge.article"].create(
            {"name": "Minutes", "parent_id": cls.board.id}
        )
        cls.board.access_label_id = cls.confidential

    def permissions(self, user):
        articles = (self.workspace | self.board | self.minutes).with_user(user)
        articles.sudo().invalidate_recordset(["user_permission"])
        return [article.sudo().user_permission for article in articles]

    def visible(self, user):
        return (
            self.env["knowledge.article"]
            .with_user(user)
            .search([("id", "in", (self.workspace | self.board | self.minutes).ids)])
        )

    def test_an_article_s_label_reaches_the_articles_below_live(self):
        self.assertEqual(self.minutes.access_inherited_label_id, self.confidential)
        self.assertEqual(self.visible(self.user_employee2), self.workspace)
        self.assertEqual(
            self.permissions(self.user_employee2), ["write", "none", "none"]
        )
        self.assertEqual(
            self.visible(self.user_employee),
            self.workspace | self.board | self.minutes,
        )
        self.assertEqual(
            self.permissions(self.user_employee), ["write", "read", "read"]
        )
        self.assertEqual(
            self.permissions(self.user_employee_manager), ["write", "write", "write"]
        )
        self.assertFalse(
            self.minutes.with_user(self.user_employee).sudo().user_has_write_access
        )
        self.assertEqual(
            self.env["knowledge.article"]
            .with_user(self.user_employee)
            .search(
                [
                    ("id", "in", (self.board | self.minutes).ids),
                    ("user_has_write_access", "=", True),
                ]
            ),
            self.env["knowledge.article"],
        )
        with self.assertRaises(AccessError):
            self.minutes.with_user(self.user_employee).write({"name": "Leaked"})

        self.minutes.parent_id = self.workspace
        self.assertIn(self.minutes, self.visible(self.user_employee2))

    def test_only_a_writer_labels_an_article(self):
        self.workspace.internal_permission = "read"
        with self.assertRaises(AccessError):
            self.workspace.with_user(self.user_employee2).write(
                {"access_label_id": self.confidential.id}
            )
        self.workspace.with_user(self.user_employee_manager).write(
            {"access_label_id": self.confidential.id}
        )
        self.assertFalse(self.visible(self.user_employee2))
