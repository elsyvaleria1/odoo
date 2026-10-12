from psycopg import IntegrityError

from odoo import Command, exceptions
from odoo.tests.common import tagged, users
from odoo.tools import mute_logger

from odoo.addons.knowledge.tests.common import KnowledgeCommon


@tagged("knowledge_internals")
class TestKnowledgeArticleConstraints(KnowledgeCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.article_private_employee = cls.env["knowledge.article"].create(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.partner_employee.id,
                            "permission": "write",
                        },
                    ),
                ],
                "internal_permission": "none",
                "name": "Employee Priv.",
                "sequence": 19,
            }
        )
        cls.article_workspace = cls.env["knowledge.article"].create(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.user_admin.partner_id.id,
                            "permission": "write",
                        },
                    )
                ],
                "internal_permission": "write",
                "favorite_ids": [
                    (
                        0,
                        0,
                        {
                            "sequence": 1,
                            "user_id": cls.user_admin.id,
                        },
                    ),
                ],
                "name": "Playground",
                "sequence": 20,
            }
        )
        cls.article_shared = cls.env["knowledge.article"].create(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.partner_admin.id,
                            "permission": "write",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.partner_employee.id,
                            "permission": "read",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.partner_employee_manager.id,
                            "permission": "read",
                        },
                    ),
                ],
                "internal_permission": "none",
                "name": "Shared",
                "sequence": 21,
            }
        )
        cls.shared_child = cls.env["knowledge.article"].create(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.partner_employee.id,
                            "permission": "write",
                        },
                    ),
                ],
                "internal_permission": False,
                "name": "Shared Child1",
                "parent_id": cls.article_shared.id,
            },
        )
        cls.items_parent = cls.env["knowledge.article"].create(
            [
                {
                    "internal_permission": "write",
                    "name": "Parent of items",
                    "parent_id": False,
                    "sequence": 22,
                }
            ]
        )
        cls.item_child = cls.env["knowledge.article"].create(
            [
                {
                    "internal_permission": False,
                    "name": "Child Item",
                    "parent_id": cls.items_parent.id,
                    "is_article_item": True,
                }
            ]
        )

    @users("employee")
    def test_article_acyclic_graph_move_to(self):
        article = self.article_workspace.with_env(self.env)
        article_children = self.env["knowledge.article"].create(
            [
                {
                    "name": "ChildNew1",
                    "parent_id": article.id,
                    "sequence": 3,
                },
                {
                    "name": "ChildNew2",
                    "parent_id": article.id,
                    "sequence": 4,
                },
            ]
        )

        with self.assertRaises(exceptions.UserError) as caught:
            article.move_to(parent_id=article_children[1].id)
        self.assertEqual(
            str(caught.exception),
            "An article cannot be moved under itself or one of its sub-articles.",
        )

    @users("employee")
    def test_article_acyclic_graph_write_parent(self):
        article = self.article_workspace.with_env(self.env)
        article_children = self.env["knowledge.article"].create(
            [
                {
                    "name": "ChildNew1",
                    "parent_id": article.id,
                    "sequence": 3,
                },
                {
                    "name": "ChildNew2",
                    "parent_id": article.id,
                    "sequence": 4,
                },
            ]
        )

        with self.assertRaises(exceptions.UserError) as caught:
            article.write({"parent_id": article_children[1].id})
        self.assertEqual(
            str(caught.exception),
            "An article cannot be moved under itself or one of its sub-articles.",
        )

    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    @users("employee")
    def test_article_create(self):
        article = self.article_workspace.with_env(self.env)
        readonly_article = self.article_shared.with_env(self.env)

        _title = "Fthagn, private"
        next_sequence = (
            1
            + self.env["knowledge.article"]
            .sudo()
            .search_read(
                domain=[("parent_id", "=", False)],
                fields=["sequence"],
                order="sequence desc",
                limit=1,
            )[0]["sequence"]
        )
        private = self.env["knowledge.article"].create(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": self.env.user.partner_id.id,
                            "permission": "write",
                        },
                    )
                ],
                "body": f"<p>{_title}</p>",
                "internal_permission": "none",
                "name": _title,
            }
        )
        self.assertMembers(private, "none", {self.env.user.partner_id: "write"})
        self.assertEqual(private.category, "private")
        self.assertFalse(private.parent_id)
        self.assertEqual(private.sequence, next_sequence)

        _title = "Fthagn, with parent (workspace)"
        children = self.env["knowledge.article"].create(
            [
                {
                    "body": f"<p>{_title}</p>",
                    "name": _title,
                    "parent_id": article.id,
                }
                for idx in range(3)
            ]
        )
        for idx, child in enumerate(children):
            self.assertMembers(child, False, {})
            self.assertEqual(child.category, "workspace")
            self.assertEqual(child.parent_id, article)
            self.assertEqual(
                child.sequence, idx, "Batch create should correctly set sequence"
            )

        _title = "Fthagn, with parent (private)"
        child_private = self.env["knowledge.article"].create(
            {
                "body": f"<p>{_title}</p>",
                "internal_permission": False,
                "name": _title,
                "parent_id": private.id,
            }
        )
        self.assertMembers(child, False, {})
        self.assertEqual(child_private.category, "private")
        self.assertEqual(child_private.parent_id, private)
        self.assertEqual(child_private.sequence, 0)

        _title = "Fthagn, but private under non private: cracboum"
        with self.assertRaises(exceptions.AccessError):
            _unwanted_child = self.env["knowledge.article"].create(
                {
                    "article_member_ids": [
                        (
                            0,
                            0,
                            {
                                "partner_id": self.env.user.partner_id.id,
                                "permission": "write",
                            },
                        )
                    ],
                    "body": f"<p>{_title}</p>",
                    "internal_permission": "none",
                    "name": _title,
                    "parent_id": article.id,
                }
            )

        _title = "Fthagn, but with parent read only: cracboum"
        with self.assertRaises(exceptions.AccessError):
            _unallowed_child = self.env["knowledge.article"].create(
                {
                    "body": f"<p>{_title}</p>",
                    "internal_permission": "write",
                    "name": _title,
                    "parent_id": readonly_article.id,
                }
            )

    @users("employee")
    def test_article_move_to_shared_root(self):

        workspace_article = (
            self.env["knowledge.article"]
            .sudo()
            .create(
                {
                    "article_member_ids": [
                        (
                            0,
                            0,
                            {
                                "partner_id": self.env.user.partner_id.id,
                                "permission": "write",
                            },
                        ),
                    ],
                    "internal_permission": "write",
                    "name": "Workspace Article without other read members",
                }
            )
        )
        private_article = self.article_private_employee.with_env(self.env)
        no_member_article = self.items_parent.with_env(self.env)

        with self.assertRaises(
            exceptions.ValidationError,
            msg="Cannot move an article that is not shared with another member as a shared root",
        ):
            workspace_article.move_to(category="shared")
        with self.assertRaises(
            exceptions.ValidationError,
            msg="Cannot move a private article as a shared root",
        ):
            private_article.move_to(category="shared")

        with self.assertRaises(
            exceptions.ValidationError,
            msg="Cannot move an article that has no member on it",
        ):
            no_member_article.move_to(category="shared")

    def _create_article_read_by_employee2(self):
        return (
            self.env["knowledge.article"]
            .sudo()
            .create(
                {
                    "name": "Read by employee2",
                    "internal_permission": "none",
                    "article_member_ids": [
                        Command.create(
                            {
                                "partner_id": self.env.user.partner_id.id,
                                "permission": "write",
                            }
                        ),
                        Command.create(
                            {
                                "partner_id": self.partner_employee2.id,
                                "permission": "read",
                            }
                        ),
                    ],
                }
            )
            .with_env(self.env)
        )

    @mute_logger("odoo.addons.base.models.ir_access")
    @users("employee")
    def test_article_parent_constraints_create(self):
        article = self._create_article_read_by_employee2()

        article_as2 = article.with_user(self.user_employee2)
        self.assertFalse(article_as2.user_has_write_access)
        self.assertTrue(article_as2.user_has_access)

        with self.assertRaises(exceptions.AccessError):
            self.env["knowledge.article"].with_user(self.user_employee2).create(
                {
                    "internal_permission": "write",
                    "name": "My Own",
                    "parent_id": article_as2.id,
                }
            )

        article_private = self._create_private_article("MyPrivate")
        self.assertMembers(article_private, "none", {self.partner_employee: "write"})
        self.assertTrue(article_private.category, "private")
        self.assertTrue(article_private.user_has_write_access)
        with self.assertRaises(exceptions.AccessError):
            self.env["knowledge.article"].with_user(self.user_employee2).create(
                {
                    "name": "My Own Private",
                    "parent_id": article_as2.id,
                }
            )

    @mute_logger("odoo.addons.base.models.ir_access")
    @users("employee")
    def test_article_parent_constraints_write(self):
        article = self._create_article_read_by_employee2()

        article_as2 = article.with_user(self.user_employee2)
        self.assertFalse(article_as2.user_has_write_access)
        self.assertTrue(article_as2.user_has_access)

        article_user2 = (
            self.env["knowledge.article"]
            .with_user(self.user_employee2)
            .create(
                {
                    "internal_permission": "write",
                    "name": "My Own",
                }
            )
        )
        with self.assertRaises(exceptions.AccessError):
            article_user2.write({"parent_id": article_as2.id})
        with self.assertRaises(exceptions.AccessError):
            article_user2.move_to(parent_id=article_as2.id)

        article_child1 = self.env["knowledge.article"].create(
            {
                "internal_permission": "write",
                "name": "Ze Name",
                "parent_id": article.id,
                "sequence": 1,
            }
        )
        article_child2 = self.env["knowledge.article"].create(
            {
                "internal_permission": "write",
                "name": "Ze Name",
                "parent_id": article.id,
                "sequence": 2,
            }
        )
        article_child2.invite_members(self.partner_employee2, "write")
        article_child2_as2 = article_child2.with_user(self.user_employee2)
        article_child2_as2.move_to(
            parent_id=article.id, before_article_id=article_child1.id
        )
        self.assertEqual(article_child2_as2.sequence, 1)
        self.assertEqual(article_child1.sequence, 2)

    @mute_logger("odoo.addons.base.models.ir_access")
    @users("employee")
    def test_article_private_management(self):
        article_workspace = self.article_workspace.with_env(self.env)

        article_private_u2 = (
            self.env["knowledge.article"]
            .sudo()
            .create(
                {
                    "article_member_ids": [
                        (
                            0,
                            0,
                            {
                                "partner_id": self.partner_employee2.id,
                                "permission": "write",
                            },
                        )
                    ],
                    "internal_permission": "none",
                    "name": "Private Child",
                    "parent_id": article_workspace.id,
                }
            )
            .with_user(self.user_employee2)
        )
        self.assertEqual(article_private_u2.category, "workspace")
        self.assertTrue(article_private_u2.user_has_write_access)

        article_private_u2_asuser = article_private_u2.with_user(self.env.user)
        with self.assertRaises(exceptions.AccessError):
            article_private_u2_asuser.body

        article_private = self._create_private_article("MyPrivate").with_user(
            self.env.user
        )
        self.assertTrue(article_private.category, "private")
        self.assertTrue(article_private.user_has_write_access)

        article_private_asu2 = article_private.with_user(self.user_employee2)
        with self.assertRaises(exceptions.AccessError):
            article_private_asu2.body

        article_private.move_to(parent_id=article_workspace.id)
        self.assertEqual(article_private.category, "workspace")

        article_private_asu2 = article_private.with_user(self.user_employee2)
        article_private_asu2.body
        self.assertFalse(article_private.internal_permission)
        self.assertEqual(article_private.inherited_permission, "write")

    @mute_logger("odoo.db.cursor")
    @users("employee")
    def test_article_root_internal_permission(self):
        article = self.env["knowledge.article"].create(
            {
                "name": "Article",
                "parent_id": False,
            }
        )
        self.assertEqual(article.category, "workspace")
        self.assertEqual(article.internal_permission, "write")

        article.sudo().write(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": self.env.user.partner_id.id,
                            "permission": "write",
                        },
                    )
                ],
            }
        )

        article_child = self.env["knowledge.article"].create(
            {
                "name": "Article",
                "parent_id": article.id,
            }
        )
        self.assertMembers(article_child, False, {})
        self.assertEqual(article_child.category, "workspace")
        self.assertEqual(article_child.root_article_id, article)
        with self.assertRaises(
            exceptions.ValidationError,
            msg="A root that grants no one gets no writer",
        ):
            article_child.sudo().write({"parent_id": False})

        article.write({"internal_permission": False})
        self.assertEqual(article.internal_permission, "none")

    @users("employee")
    def test_article_should_have_at_least_one_writer(self):
        with self.assertRaises(
            exceptions.ValidationError, msg="Article should have at least one writer"
        ):
            self.env["knowledge.article"].create(
                {
                    "internal_permission": "none",
                    "name": "Article",
                }
            )
        with self.assertRaises(
            exceptions.ValidationError, msg="Article should have at least one writer"
        ):
            self.env["knowledge.article"].create(
                {
                    "internal_permission": "read",
                    "name": "Article",
                }
            )

        article_private = self._create_private_article("MyPrivate")
        self.assertMembers(article_private, "none", {self.partner_employee: "write"})
        self.assertEqual(article_private.category, "private")

        membership_sudo = article_private.sudo().article_member_ids
        with self.assertRaises(
            exceptions.ValidationError,
            msg="Cannot remove the last writer on an article",
        ):
            article_private.sudo().write(
                {
                    "article_member_ids": [
                        (1, membership_sudo.id, {"permission": "read"})
                    ]
                }
            )
        with self.assertRaises(
            exceptions.ValidationError,
            msg="Cannot remove the last writer on an article",
        ):
            article_private._add_members(membership_sudo.partner_id, "none")
        with self.assertRaises(
            exceptions.ValidationError,
            msg="Cannot remove the last writer on an article",
        ):
            membership_sudo.unlink()
        with self.assertRaises(
            exceptions.ValidationError,
            msg="Cannot remove the last writer on an article",
        ):
            article_private.sudo().write(
                {"article_member_ids": self.env["knowledge.article.member"]}
            )
        with self.assertRaises(
            exceptions.ValidationError,
            msg="Cannot remove the last writer on an article",
        ):
            article_private.sudo().write(
                {"article_member_ids": [(2, membership_sudo.id)]}
            )
        article_private.sudo().remove_member(membership_sudo.id)
        self.assertFalse(article_private.active)
        self.assertMembers(article_private, "none", {self.env.user.partner_id: "write"})

        article_workspace = self.article_workspace.with_env(self.env)
        article_workspace.move_to(category="private")
        self.assertEqual(article_workspace.category, "private")
        self.assertTrue(article_workspace._has_write_member())

    @mute_logger("odoo.db.cursor")
    @users("employee")
    def test_article_trashed_should_be_archived(self):
        article = self.env["knowledge.article"].create(
            {
                "name": "Article",
                "parent_id": False,
            }
        )

        with self.assertRaises(
            IntegrityError, msg="Trashed articles must be archived."
        ):
            article.write({"to_delete": True})

        article.write(
            {
                "to_delete": True,
                "active": False,
            }
        )
        self.assertTrue(article.to_delete)
        self.assertFalse(article.active)

        with self.assertRaises(
            IntegrityError, msg="Trashed articles must be archived."
        ):
            article.write({"active": True})

        article.write(
            {
                "to_delete": False,
                "active": True,
            }
        )
        self.assertTrue(article.active)
        self.assertFalse(article.to_delete)

    @mute_logger("odoo.db.cursor")
    @users("employee")
    def test_favourite_uniqueness(self):
        article = self.env["knowledge.article"].create(
            {"internal_permission": "write", "name": "Article"}
        )
        self.assertFalse(article.is_user_favorite)
        article.action_toggle_user_favorite()
        self.assertTrue(article.is_user_favorite)
        with self.assertRaises(
            IntegrityError, msg="Multiple favorite entries are not accepted"
        ):
            article.write({"favorite_ids": [(0, 0, {"user_id": self.env.user.id})]})
        self.assertTrue(article.is_user_favorite)

    @mute_logger("odoo.db.cursor")
    @users("employee")
    def test_member_uniqueness(self):
        article = self.env["knowledge.article"].create(
            {
                "internal_permission": "write",
                "name": "Article",
            }
        )
        article.sudo().write(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": self.env.user.partner_id.id,
                            "permission": "write",
                        },
                    )
                ]
            }
        )
        self.assertEqual(
            len(
                self.env["knowledge.article.member"]
                .sudo()
                .search([("article_id", "=", article.id), ("partner_id", "!=", False)])
            ),
            1,
        )

        with self.assertRaises(
            IntegrityError, msg="Members should be unique (article_id/partner_id)"
        ):
            article.sudo().write(
                {
                    "article_member_ids": [
                        (
                            0,
                            0,
                            {
                                "partner_id": self.env.user.partner_id.id,
                                "permission": "write",
                            },
                        )
                    ]
                }
            )
        self.assertEqual(
            len(
                self.env["knowledge.article.member"]
                .sudo()
                .search([("article_id", "=", article.id), ("partner_id", "!=", False)])
            ),
            1,
        )

        article.invite_members(self.env.user.partner_id, "write")
        self.assertEqual(
            len(
                self.env["knowledge.article.member"]
                .sudo()
                .search([("article_id", "=", article.id), ("partner_id", "!=", False)])
            ),
            1,
        )

        with self.assertRaises(
            IntegrityError, msg="Members should be unique (article_id/partner_id)"
        ):
            article.invite_members(
                self.partner_employee2 + self.partner_employee2, "write"
            )
        self.assertEqual(
            len(
                self.env["knowledge.article.member"]
                .sudo()
                .search([("article_id", "=", article.id), ("partner_id", "!=", False)])
            ),
            1,
        )

        with self.assertRaises(
            IntegrityError, msg="Members should be unique (article_id/partner_id)"
        ):
            article.sudo().write(
                {
                    "article_member_ids": [
                        (
                            0,
                            0,
                            {
                                "partner_id": self.partner_admin.id,
                                "permission": "write",
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "partner_id": self.partner_admin.id,
                                "permission": "write",
                            },
                        ),
                    ],
                }
            )
        self.assertEqual(
            len(
                self.env["knowledge.article.member"]
                .sudo()
                .search([("article_id", "=", article.id), ("partner_id", "!=", False)])
            ),
            1,
        )

    @mute_logger("odoo.db.cursor")
    @users("employee")
    def test_article_item_create(self):
        with self.assertRaises(
            IntegrityError, msg="Cannot create an article item without parent"
        ):
            self.env["knowledge.article"].create(
                [
                    {
                        "internal_permission": False,
                        "name": "Orphan Item",
                        "parent_id": False,
                        "is_article_item": True,
                    }
                ]
            )

        self.assertEqual(len(self.items_parent.child_ids), 1)
        self.assertTrue(self.items_parent.has_item_children)

        self.env["knowledge.article"].create(
            [
                {
                    "internal_permission": False,
                    "name": "Child Item 2",
                    "parent_id": self.items_parent.id,
                    "is_article_item": True,
                }
            ]
        )
        self.assertEqual(len(self.items_parent.child_ids), 2)
        self.assertTrue(self.items_parent.has_item_children)

        self.env["knowledge.article"].create(
            [
                {
                    "internal_permission": False,
                    "name": "Child Item 3",
                    "parent_id": self.items_parent.id,
                    "is_article_item": False,
                }
            ]
        )

        self.assertTrue(len(self.item_child.child_ids) == 0)
        self.env["knowledge.article"].create(
            [
                {
                    "internal_permission": False,
                    "name": "grand child item",
                    "parent_id": self.item_child.id,
                    "is_article_item": True,
                }
            ]
        )
        self.assertEqual(len(self.item_child.child_ids), 1)
        self.assertTrue(self.item_child.has_item_children)

    @mute_logger("odoo.db.cursor")
    @users("employee")
    def test_article_item_write(self):
        items_parent_2 = self.env["knowledge.article"].create(
            [
                {
                    "internal_permission": "write",
                    "name": "item parent 2",
                    "parent_id": False,
                }
            ]
        )
        self.env["knowledge.article"].create(
            [
                {
                    "internal_permission": False,
                    "name": "item child 2",
                    "parent_id": items_parent_2.id,
                    "is_article_item": True,
                }
            ]
        )
        self.item_child.move_to(items_parent_2.id)
        self.assertTrue(self.item_child.is_article_item)

        self.assertTrue(len(self.shared_child.child_ids) == 0)
        self.item_child.move_to(self.shared_child.id)
        self.assertTrue(self.item_child.is_article_item)
        self.assertEqual(len(self.shared_child.child_ids), 1)
        self.assertTrue(self.shared_child.has_item_children)

        self.env["knowledge.article"].create(
            [
                {
                    "internal_permission": False,
                    "name": "workspace child",
                    "parent_id": self.article_workspace.id,
                    "is_article_item": False,
                }
            ]
        )
        self.assertEqual(len(self.article_workspace.child_ids), 1)
        self.assertTrue(self.article_workspace.has_article_children)

        self.item_child.move_to(self.article_workspace.id)

        self.assertTrue(self.item_child.is_article_item)
        self.assertEqual(len(self.article_workspace.child_ids), 2)
        self.assertTrue(self.article_workspace.has_article_children)

        with self.assertRaises(
            IntegrityError, msg="An article item must have a parent"
        ):
            self.item_child.write({"parent_id": False})

        self.item_child.write({"is_article_item": False})
        self.assertFalse(self.item_child.is_article_item)
        self.item_child.move_to(items_parent_2.id)
        self.assertFalse(self.item_child.is_article_item)
