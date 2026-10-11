from odoo import exceptions
from odoo.tests.common import tagged, users
from odoo.tools import mute_logger

from odoo.addons.knowledge.tests.common import KnowledgeArticlePermissionsCase


@tagged("knowledge_acl")
class TestKnowledgeArticlePermissions(KnowledgeArticlePermissionsCase):
    @users("employee")
    def test_article_main_parent(self):
        article_roots = self.article_roots.with_env(self.env)

        articles_write = (
            self.article_write_contents + self.article_write_contents_children
        ).with_env(self.env)
        self.assertEqual(articles_write.root_article_id, article_roots[0])

        articles_write = self.article_read_contents.with_env(self.env)
        self.assertEqual(articles_write.root_article_id, article_roots[1])

        self.assertEqual(self.article_write_desync.root_article_id, article_roots[0])
        self.assertEqual(self.article_read_desync.root_article_id, article_roots[1])

    def test_article_permissions_desync(self):
        for (
            exp_inherited_permission,
            exp_inherited_permission_parent_id,
            exp_internal_permission,
        ), article in zip(
            [
                ("read", self.env["knowledge.article"], "read"),
                ("read", self.article_write_desync[0], False),
                ("none", self.env["knowledge.article"], "none"),
                ("none", self.article_read_desync[0], False),
                ("write", self.env["knowledge.article"], "write"),
                ("read", self.env["knowledge.article"], "read"),
            ],
            self.article_write_desync + self.article_read_desync + self.article_roots,
            strict=False,
        ):
            self.assertEqual(
                article.inherited_permission,
                exp_inherited_permission,
                f"Permission: wrong inherit computation for {article.name}: {article.inherited_permission} instead of {exp_inherited_permission}",
            )
            self.assertEqual(
                article.inherited_permission_parent_id,
                exp_inherited_permission_parent_id,
                f"Permission: wrong inherit computation for {article.name}: {article.inherited_permission_parent_id.name} instead of {exp_inherited_permission_parent_id.name}",
            )
            self.assertEqual(
                article.internal_permission,
                exp_internal_permission,
                f"Permission: wrong inherit computation for {article.name}: {article.internal_permission} instead of {exp_internal_permission}",
            )

    @mute_logger("odoo.addons.base.models.ir_access")
    def test_article_permissions_inheritance_desync(self):
        article_desync = self.article_write_desync[0]
        self.assertMembers(
            article_desync, "read", {self.partner_employee_manager: "write"}
        )

        article_desync = article_desync.with_user(self.user_employee_manager)
        self.assertTrue(article_desync.user_has_write_access)
        self.assertTrue(article_desync.user_has_access)

        article_desync = article_desync.with_user(self.user_employee)
        self.assertFalse(article_desync.user_has_write_access)
        self.assertTrue(article_desync.user_has_access)

        article_desync = article_desync.with_user(self.user_portal)
        self.assertFalse(article_desync.user_has_write_access)
        self.assertFalse(
            article_desync.user_has_access,
            "Permissions: member rights should not be fetch on parents",
        )

    @mute_logger("odoo.addons.base.models.ir_access")
    @users("employee")
    def test_article_permissions_inheritance_employee(self):
        article_roots = self.article_roots.with_env(self.env)

        self.assertEqual(
            article_roots.mapped("user_has_write_access"), [True, False, False, True]
        )
        self.assertEqual(
            article_roots.mapped("user_has_access"), [True, True, True, True]
        )
        self.assertEqual(
            article_roots.mapped("user_permission"), ["write", "read", "read", "write"]
        )

        article_write_ancestor = self.article_write_contents[2].with_env(self.env)
        self.assertEqual(article_write_ancestor.inherited_permission, "write")
        self.assertEqual(
            article_write_ancestor.inherited_permission_parent_id, self.article_roots[0]
        )
        self.assertFalse(article_write_ancestor.internal_permission)
        self.assertEqual(article_write_ancestor.user_permission, "write")

        article_read_forced = self.article_write_contents[1].with_env(self.env)
        self.assertEqual(article_read_forced.inherited_permission, "read")
        self.assertFalse(article_read_forced.inherited_permission_parent_id)
        self.assertEqual(article_read_forced.internal_permission, "read")
        self.assertEqual(article_read_forced.user_permission, "read")

        article_read_member = self.article_write_contents[0].with_env(self.env)
        self.assertEqual(article_read_member.inherited_permission, "write")
        self.assertEqual(
            article_read_member.inherited_permission_parent_id, self.article_roots[0]
        )
        self.assertFalse(article_read_member.internal_permission)
        self.assertEqual(article_read_member.user_permission, "write")

        article_lower = self.article_read_contents[1].with_env(self.env)
        self.assertEqual(article_lower.inherited_permission, "read")
        self.assertFalse(article_lower.inherited_permission_parent_id)
        self.assertEqual(article_lower.internal_permission, "read")
        self.assertEqual(article_lower.user_permission, "read")

        article_read_ancestor = self.article_read_contents[2].with_env(self.env)
        self.assertEqual(article_read_ancestor.inherited_permission, "read")
        self.assertEqual(
            article_read_ancestor.inherited_permission_parent_id, self.article_roots[1]
        )
        self.assertFalse(article_read_ancestor.internal_permission)
        self.assertEqual(article_read_ancestor.user_permission, "read")

        article_none = self.article_read_contents[3].with_env(self.env)
        with self.assertRaises(exceptions.AccessError):
            article_none.name

    @mute_logger("odoo.addons.base.models.ir_access")
    @users("portal_test")
    def test_article_permissions_inheritance_portal(self):
        article_roots = self.article_roots.with_env(self.env)

        with self.assertRaises(exceptions.AccessError):
            article_roots.read(["internal_permission"])

        article_members = self.article_read_contents[0:2].with_env(self.env)
        self.assertEqual(
            article_members.mapped("inherited_permission"), ["write", "read"]
        )
        self.assertEqual(
            article_members.mapped("internal_permission"), ["write", "read"]
        )
        self.assertEqual(
            article_members.mapped("user_has_write_access"),
            [False, False],
            "Portal: can never write",
        )
        self.assertEqual(
            article_members.mapped("user_has_access"),
            [True, True],
            "Portal: access through membership",
        )
        self.assertEqual(article_members.mapped("user_permission"), ["read", "read"])

    @users("employee")
    def test_article_permissions_employee_new_mode(self):
        article = self.env["knowledge.article"].new({"name": "Transient"})
        self.assertFalse(article.inherited_permission)
        self.assertFalse(article.internal_permission)
        self.assertTrue(article.user_has_write_access)
        self.assertTrue(article.user_has_access)
        self.assertEqual(article.user_permission, "write")


@tagged("knowledge_internals", "knowledge_management")
class KnowledgeArticlePermissionsInitialValues(KnowledgeArticlePermissionsCase):
    """Test initial values or our test data once so that other tests do not have
    to do it."""

    def test_initial_values(self):
        article_roots = self.article_roots.with_env(self.env)
        article_headers = self.article_headers.with_env(self.env)

        self.assertEqual(
            article_roots.mapped("inherited_permission"),
            ["write", "read", "none", "none"],
        )
        self.assertFalse(article_roots.inherited_permission_parent_id)
        self.assertEqual(
            article_roots.mapped("internal_permission"),
            ["write", "read", "none", "none"],
        )

        self.assertEqual(
            article_headers.mapped("inherited_permission"), ["write", "read", "read"]
        )
        self.assertEqual(
            [p.inherited_permission_parent_id for p in article_headers],
            [article_roots[0], article_roots[1], article_roots[1]],
        )
        self.assertEqual(
            article_headers.mapped("internal_permission"), [False, False, False]
        )

    @users("employee")
    def test_initial_values_as_employee(self):
        article_write_inherit = self.article_write_contents[2].with_env(self.env)

        self.assertMembers(article_write_inherit, False, {self.partner_portal: "read"})
        self.assertFalse(article_write_inherit.internal_permission)
        self.assertFalse(article_write_inherit.is_desynchronized)
        self.assertTrue(article_write_inherit.user_has_write_access)
        self.assertTrue(article_write_inherit.user_has_access)

        article_write_inherit_as2 = article_write_inherit.with_user(self.user_employee2)
        self.assertTrue(article_write_inherit_as2.user_has_write_access)
        self.assertTrue(article_write_inherit_as2.user_has_access)


@tagged("knowledge_acl")
class TestKnowledgeArticlePermissionsTools(KnowledgeArticlePermissionsCase):
    @mute_logger("odoo.addons.base.models.ir_access")
    @users("employee")
    def test_downgrade_internal_permission_none(self):
        writable_as1 = self.article_write_contents[2].with_env(self.env)
        writable_as2 = writable_as1.with_user(self.user_employee2)
        self.assertEqual(writable_as2.user_has_access, True)
        writable_root = self.article_roots[0].with_env(self.env)
        writable_children = self.article_write_contents_children.with_env(self.env)
        for child in writable_children:
            self.assertEqual(child.inherited_permission_parent_id, writable_root)

        writable_as1.set_internal_permission("none")
        writable_as1.flush_model()
        self.assertMembers(
            writable_as1,
            "none",
            {
                self.partner_portal: "read",
                self.env.user.partner_id: "write",
            },
            "Permission: lowering permission adds current user in members to have write access",
        )
        self.assertTrue(writable_as1.is_desynchronized)
        self.assertTrue(writable_as1.user_has_write_access)
        self.assertTrue(writable_as1.user_has_access)

        with self.assertRaises(exceptions.AccessError):
            writable_as2.body

        for child in writable_children:
            self.assertEqual(
                child.inherited_permission,
                "none",
                "Permission: lowering permission should lower the permission of the children",
            )
            self.assertEqual(
                child.inherited_permission_parent_id,
                writable_as1,
                "Permission: lowering permission should make the children inherit the permission from this article",
            )

    @users("employee")
    def test_downgrade_internal_permission_read(self):
        writable_as1 = self.article_write_contents[2].with_env(self.env)
        writable_as2 = writable_as1.with_user(self.user_employee2)
        self.assertEqual(writable_as2.user_has_access, True)
        writable_root = self.article_roots[0].with_env(self.env)
        writable_children = self.article_write_contents_children.with_env(self.env)
        for child in writable_children:
            self.assertEqual(child.inherited_permission_parent_id, writable_root)

        writable_as1.set_internal_permission("read")
        writable_as1.flush_model()
        self.assertMembers(
            writable_as1,
            "read",
            {self.partner_portal: "read", self.env.user.partner_id: "write"},
            "Permission: lowering permission adds current user in members to have write access",
        )
        self.assertTrue(writable_as1.is_desynchronized)
        self.assertTrue(writable_as1.user_has_write_access)
        self.assertTrue(writable_as1.user_has_access)
        self.assertFalse(writable_as2.user_has_write_access)
        self.assertTrue(writable_as2.user_has_access)

        for child in writable_children:
            self.assertEqual(
                child.inherited_permission,
                "read",
                "Permission: lowering permission should lower the permission of the children",
            )
            self.assertEqual(
                child.inherited_permission_parent_id,
                writable_as1,
                "Permission: lowering permission should make the children inherit the permission from this article",
            )

    @mute_logger("odoo.addons.base.models.ir_access", "odoo.models.unlink")
    @users("employee")
    def test_remove_member_inherited_rights(self):
        writable = self.article_write_contents[2].with_env(self.env)
        self.assertTrue(writable.user_has_access)
        self.assertTrue(writable.user_has_write_access)
        self.assertMembers(writable, False, {self.partner_portal: "read"})

        writable_root = writable.root_article_id
        writable_root._add_members(self.partner_employee_manager, "write")
        self.assertMembers(
            writable_root, "write", {self.partner_employee_manager: "write"}
        )

        writable_children = self.article_write_contents_children.with_env(self.env)
        for child in writable_children:
            self.assertIn(
                self.partner_employee_manager.id,
                child._get_article_member_permissions()[child.id],
                "Share Panel: if an article inherits a permission, its children should inherit that permission too",
            )
        manager_member = writable_root.article_member_ids.filtered(
            lambda m: m.partner_id == self.partner_employee_manager
        )
        writable.remove_member(manager_member.id)
        self.assertTrue(
            writable.is_desynchronized,
            "Permission: when removing a member having inherited rights it has be be desynchronized",
        )
        self.assertMembers(writable, "write", {self.partner_portal: "read"})
        for child in writable_children:
            self.assertNotIn(
                self.partner_employee_manager.id,
                child._get_article_member_permissions()[child.id],
                "Share Panel: when removing a member having inherited rights, the member should be removed from the children that inherited that right",
            )

        writable.restore_article_access()
        self.assertFalse(writable.is_desynchronized)
        self.assertMembers(writable, False, {self.partner_portal: "read"})

        portal_member = writable.article_member_ids.filtered(
            lambda m: m.partner_id == self.partner_portal
        )
        writable.remove_member(portal_member.id)
        self.assertFalse(writable.is_desynchronized)
        self.assertMembers(writable, False, {})

    @mute_logger("odoo.addons.base.models.ir_access", "odoo.models.unlink")
    @users("employee")
    def test_remove_member_leave_article(self):
        readable_root = self.article_roots[1].with_env(self.env)
        readable_root.action_join()
        self.assertMembers(
            readable_root,
            "read",
            {self.env.user.partner_id: "read", self.partner_employee_manager: "write"},
        )
        user_member_id = readable_root.article_member_ids.filtered(
            lambda m: m.partner_id == self.env.user.partner_id
        )
        readable_root.remove_member(user_member_id.id)
        self.assertMembers(
            readable_root, "read", {self.partner_employee_manager: "write"}
        )

    @mute_logger("odoo.addons.base.models.ir_access", "odoo.models.unlink")
    @users("employee")
    def test_remove_member_leave_shared_article(self):
        shared_article = self.article_roots[2]
        self.assertMembers(
            shared_article,
            "none",
            {self.env.user.partner_id: "read", self.partner_employee_manager: "write"},
        )

        my_member = shared_article.article_member_ids.filtered(
            lambda m: m.partner_id == self.env.user.partner_id
        )
        shared_article.remove_member(my_member.id)

        self.assertMembers(
            shared_article, "none", {self.partner_employee_manager: "write"}
        )

    @mute_logger("odoo.models.unlink")
    @users("employee")
    def test_set_member_permission(self):
        writable = self.article_write_contents[2].with_env(self.env)
        self.assertTrue(writable.user_has_access)
        self.assertTrue(writable.user_has_write_access)

        writable_root = writable.root_article_id
        writable_root._add_members(self.partner_employee_manager, "read")
        self.assertMembers(
            writable_root, "write", {self.partner_employee_manager: "read"}
        )

        portal_member = writable.article_member_ids.filtered(
            lambda m: m.partner_id == self.partner_portal
        )
        writable.set_member_permission(portal_member.id, "none")
        self.assertMembers(writable, False, {})

        manager_member_root = writable_root.article_member_ids.filtered(
            lambda m: m.partner_id == self.partner_employee_manager
        )
        writable.set_member_permission(manager_member_root.id, "write")
        self.assertFalse(writable.is_desynchronized)
        self.assertMembers(
            writable,
            False,
            {self.partner_employee_manager: "write"},
        )

        manager_member = writable.article_member_ids.filtered(
            lambda m: m.partner_id == self.partner_employee_manager
        )
        writable_root.set_member_permission(manager_member_root.id, "write")
        writable.remove_member(manager_member.id)
        self.assertMembers(
            writable_root, "write", {self.partner_employee_manager: "write"}
        )
        self.assertMembers(writable, False, {})

        writable_children = self.article_write_contents_children.with_env(self.env)
        for child in writable_children:
            self.assertEqual(
                child._get_article_member_permissions()[child.id][
                    self.partner_employee_manager.id
                ]["permission"],
                "write",
                "Share Panel: if an article inherits a permission, its children should inherit that permission too",
            )
        writable_root.set_member_permission(manager_member_root.id, "write")
        writable.set_member_permission(manager_member_root.id, "read")
        self.assertTrue(
            writable.is_desynchronized,
            "Permission: when removing a member having inherited rights it has be be desynchronized",
        )
        self.assertMembers(
            writable,
            "write",
            {self.partner_employee_manager: "read"},
        )
        for child in writable_children:
            self.assertEqual(
                child._get_article_member_permissions()[child.id][
                    self.partner_employee_manager.id
                ]["permission"],
                "read",
                "Share Panel: when downgrading a member having inherited rights, the member should be downgraded from the children that inherited that right",
            )

        writable_root._add_members(self.partner_employee2, "read")
        self.assertNotIn(
            self.partner_employee2.id,
            writable._get_article_member_permissions()[writable.id],
            "Share Panel: when adding a member on a parent of a desynced article, the member should not be added on the desynced article",
        )
        for child in writable_children:
            self.assertNotIn(
                self.partner_employee2.id,
                child._get_article_member_permissions()[child.id],
                "Share Panel: when adding a member on a parent of a desynced article, the member should not be added on the children of the desynced article",
            )

    @mute_logger("odoo.addons.base.models.ir_access")
    @users("employee")
    def test_update_internal_permission_escalation(self):
        readonly = self.article_read_contents[1].with_env(self.env)
        self.assertTrue(readonly.user_has_access)
        self.assertFalse(readonly.user_has_write_access)
        writable = self.article_write_contents[2].with_env(self.env)
        self.assertTrue(writable.user_has_access)
        self.assertTrue(writable.user_has_write_access)

        with self.assertRaises(
            exceptions.AccessError,
            msg="Permission: that is plain stupid trying to do this",
        ):
            readonly.write({"internal_permission": "write"})
        with self.assertRaises(
            exceptions.AccessError, msg="Permission: do not allow privilege escalation"
        ):
            readonly.set_internal_permission("write")

    @mute_logger("odoo.addons.base.models.ir_access", "odoo.models.unlink")
    @users("employee")
    def test_update_permissions_rights(self):
        readonly = self.article_read_contents[1].with_env(self.env)
        self.assertTrue(readonly.user_has_access)
        self.assertFalse(readonly.user_has_write_access)
        with self.assertRaises(
            exceptions.AccessError,
            msg="Permission: that is plain stupid trying to do this",
        ):
            readonly.write({"internal_permission": "write"})
        with self.assertRaises(
            exceptions.AccessError, msg="Permission: do not allow privilege escalation"
        ):
            readonly.set_internal_permission("write")

        other_member = readonly.article_member_ids.filtered(
            lambda m: m.partner_id == self.partner_portal
        )
        with self.assertRaises(
            exceptions.AccessError,
            msg="Permission: do not allow to remove other members when having only read access",
        ):
            readonly.remove_member(other_member.id)
        self.assertMembers(
            readonly,
            "read",
            {self.env.user.partner_id: "read", self.partner_portal: "read"},
        )

        my_member = readonly.article_member_ids.filtered(
            lambda m: m.partner_id == self.env.user.partner_id
        )
        readonly.remove_member(my_member.id)
        self.assertMembers(readonly, "read", {self.partner_portal: "read"})


@tagged("knowledge_acl", "knowledge_portal")
class TestKnowledgeArticlePortal(KnowledgeArticlePermissionsCase):
    """Portal users should have limited usage, they can read/write depending on permissions but can't:
    - Modify the article hierarchy (move an article from a parent to another)
    - Modify the article internal_permission
    - Modify the article visibility ('is_article_visible_by_everyone')
    - Create root articles (can only create UNDER articles to which they have write access)"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.article_roots[0].write(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.user_portal.partner_id.id,
                            "permission": "write",
                        },
                    )
                ]
            }
        )

        cls.article_roots[2].write(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.user_portal.partner_id.id,
                            "permission": "read",
                        },
                    )
                ]
            }
        )

        cls.portal_user_2 = cls.env["res.partner"].create({"name": "Portal User 2"})

    @users("portal_test")
    def test_article_create(self):
        KnowledgeArticle = self.env["knowledge.article"]
        article_root = KnowledgeArticle.browse(self.article_roots[0].id)

        KnowledgeArticle.create(
            {
                "name": "Test Child Portal Article",
                "parent_id": article_root.id,
            }
        )

        KnowledgeArticle.create(
            {
                "name": "Test Root Portal Article",
                "internal_permission": "none",
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": self.user_portal.partner_id.id,
                            "permission": "write",
                        },
                    )
                ],
            }
        )

        with self.assertRaises(exceptions.AccessError):
            KnowledgeArticle.create(
                {
                    "name": "Test Root Portal Article",
                }
            )

    @users("portal_test")
    def test_article_leave(self):
        article_root = self.env["knowledge.article"].browse(self.article_roots[0].id)

        with self.assertRaises(exceptions.AccessError):
            portal_member = (
                article_root.sudo()
                .article_member_ids.filtered(
                    lambda m: m.partner_id == self.user_portal.partner_id
                )
                .id
            )
            article_root.remove_member(portal_member)

    @users("portal_test")
    def test_article_membership_access(self):

        article_root = self.env["knowledge.article"].browse(self.article_roots[0].id)

        article_root.read(["name"])
        article_root.write({"name": "Updated Name"})

        shared_root = self.env["knowledge.article"].browse(self.article_roots[2].id)
        shared_root.read(["name"])
        with self.assertRaises(exceptions.AccessError):
            shared_root.write({"name": "Updated Name"})

        readable_workspace_root = self.env["knowledge.article"].browse(
            self.article_roots[1].id
        )
        with self.assertRaises(exceptions.AccessError):
            readable_workspace_root.read(["name"])

    @users("portal_test")
    def test_article_membership_management(self):
        article_root = self.env["knowledge.article"].browse(self.article_roots[0].id)

        self.env["knowledge.article.member"].sudo().create(
            {
                "partner_id": self.user_employee.partner_id.id,
                "article_id": article_root.id,
                "permission": "write",
            }
        )

        employee_member = article_root.article_member_ids.filtered(
            lambda member: member.partner_id == self.user_employee.partner_id
        )

        with self.assertRaises(exceptions.AccessError):
            article_root.set_member_permission(employee_member.id, "read")

        with self.assertRaises(exceptions.AccessError):
            article_root.invite_members(self.portal_user_2, "read")

        with self.assertRaises(exceptions.AccessError):
            article_root._add_members(self.portal_user_2, "read")

        with self.assertRaises(exceptions.AccessError):
            article_root.remove_member(employee_member.id)

    @users("portal_test")
    def test_article_reorganize_private(self):

        [private_1, private_2] = self.env["knowledge.article"].create(
            [
                {
                    "name": "Private 1",
                    "internal_permission": "none",
                    "sequence": 1,
                    "article_member_ids": [
                        (
                            0,
                            0,
                            {
                                "partner_id": self.user_portal.partner_id.id,
                                "permission": "write",
                            },
                        )
                    ],
                },
                {
                    "name": "Private 2",
                    "internal_permission": "none",
                    "sequence": 2,
                    "article_member_ids": [
                        (
                            0,
                            0,
                            {
                                "partner_id": self.user_portal.partner_id.id,
                                "permission": "write",
                            },
                        )
                    ],
                },
            ]
        )

        private_1.write({"sequence": 2})
        private_2.write({"sequence": 1})

        private_2.write({"parent_id": private_1.id})

        private_1.write(
            {
                "active": False,
                "to_delete": True,
            }
        )

    @users("portal_test")
    def test_article_write(self):
        article_root = self.env["knowledge.article"].browse(self.article_roots[0].id)

        article_root.write({"name": "New Name"})

        with self.assertRaises(exceptions.AccessError):
            article_root.write({"parent_id": self.article_roots[1].id})

        with self.assertRaises(exceptions.AccessError):
            article_root.write({"internal_permission": "read"})

        with self.assertRaises(exceptions.AccessError):
            article_root.set_internal_permission({"internal_permission": "read"})

        with self.assertRaises(exceptions.AccessError):
            article_root.write({"is_article_visible_by_everyone": True})

        with self.assertRaises(exceptions.AccessError):
            article_root.write({"active": False})

        with self.assertRaises(exceptions.AccessError):
            article_root.write({"to_delete": True})

        article_root.write({"body": "updated body"})
        self.assertEqual(article_root.last_edition_uid, self.user_portal)

        with self.assertRaises(exceptions.AccessError):
            article_root.write({"last_edition_uid": self.user_employee.id})

    @users("portal_test")
    def test_article_stage(self):
        article_stage = self.env["knowledge.article.stage"].create(
            {"name": "Article Stage", "parent_id": self.article_roots[0].id}
        )

        article_stage.write({"name": "Updated Name"})
        article_stage.unlink()

        with self.assertRaises(exceptions.AccessError):
            self.env["knowledge.article.stage"].create(
                {"name": "Article Stage", "parent_id": self.article_roots[1].id}
            )


@tagged("knowledge_acl")
class TestKnowledgeArticleSearch(KnowledgeArticlePermissionsCase):
    @users("admin")
    def test_article_business_flow_search_admin(self):

        Article = self.env["knowledge.article"]
        private_employee_root = self.article_roots[-1]
        article_header = self.article_headers[0]
        explicit_no_access = Article.create(
            {
                "name": "Explicit No Access Article",
                "body": "<p>Content</p>",
                "internal_permission": "none",
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": self.partner_employee.id,
                            "permission": "write",
                        },
                    )
                ],
            }
        )
        self.assertFalse(private_employee_root.user_has_access)
        self.assertFalse(explicit_no_access.user_has_access)

        accessible_articles = Article.search([])
        self.assertTrue(article_header in accessible_articles)
        self.assertTrue(private_employee_root in accessible_articles)
        self.assertTrue(explicit_no_access in accessible_articles)

        move_to_candidates = (
            self.article_write_contents_children[1]
            .with_env(self.env)
            .get_valid_parent_options()
        )
        move_to_candidate_ids = [article["id"] for article in move_to_candidates]
        self.assertTrue(article_header.id in move_to_candidate_ids)
        self.assertFalse(private_employee_root.id in move_to_candidate_ids)
        self.assertFalse(private_employee_root.id in move_to_candidate_ids)
        self.assertFalse(explicit_no_access.id in move_to_candidate_ids)

    @users("admin")
    def test_article_search_admin(self):
        self.assertTrue(self.env.user.has_group("base.group_system"))
        articles = self.env["knowledge.article"].search([])
        expected = self.articles_all
        self.assertEqual(
            articles,
            expected,
            "Search on user_has_write_access: aka write access (additional: %s, missing: %s)"
            % (
                (articles - expected).mapped("name"),
                (expected - articles).mapped("name"),
            ),
        )

        articles = self.env["knowledge.article"].search(
            [("user_has_write_access", "=", True)]
        )
        expected = (
            self.article_roots[0]
            + self.article_headers[0]
            + self.article_write_contents[0]
            + self.article_write_contents[2]
            + self.article_write_contents_children
            + self.article_read_contents[0]
        )
        self.assertEqual(
            articles,
            expected,
            "Search on user_has_write_access: aka write access (additional: %s, missing: %s)"
            % (
                (articles - expected).mapped("name"),
                (expected - articles).mapped("name"),
            ),
        )

    @users("employee")
    def test_article_search_employee(self):
        self.article_write_desync[0].sudo().internal_permission = "none"
        articles = self.env["knowledge.article"].search([])
        expected = (
            self.articles_all
            - self.article_read_contents[3]
            - self.article_write_desync
            - self.article_read_contents[3].child_ids
        )
        self.assertEqual(
            articles,
            expected,
            'Search on main article: aka everything except "none"-based articles (additional: %s, missing: %s)'
            % (
                (articles - expected).mapped("name"),
                (expected - articles).mapped("name"),
            ),
        )

        self.article_write_desync[1].write(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": self.user_employee.partner_id.id,
                            "permission": "read",
                        },
                    )
                ]
            }
        )

        articles = self.env["knowledge.article"].search(
            [("root_article_id", "=", self.article_roots[0].id)]
        )
        expected = (
            self.article_roots[0]
            + self.article_headers[0]
            + self.article_write_contents
            + self.article_write_contents_children
            + self.article_write_desync[1]
        )
        self.assertEqual(
            articles,
            expected,
            "Search on main article: aka read access on read root + its children (additional: %s, missing: %s)"
            % (
                (articles - expected).mapped("name"),
                (expected - articles).mapped("name"),
            ),
        )

    @users("employee")
    def test_article_search_employee_method_based(self):
        articles = self.env["knowledge.article"].search(
            [("user_has_write_access", "=", True)]
        )
        expected = (
            self.article_roots[0]
            + self.article_roots[3]
            + self.article_headers[0]
            + self.article_write_contents[0]
            + self.article_write_contents[2]
            + self.article_write_contents_children
            + self.article_read_contents[0]
            + self.article_read_desync
        )
        self.assertEqual(
            articles,
            expected,
            "Search on user_has_write_access: aka write access (additional: %s, missing: %s)"
            % (
                (articles - expected).mapped("name"),
                (expected - articles).mapped("name"),
            ),
        )
